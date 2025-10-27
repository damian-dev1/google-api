from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
import requests
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
try:
    import google.auth
    from google.auth.transport.requests import Request as GAuthRequest
    from google.oauth2 import service_account
    _HAS_GOOGLE_AUTH = True
except Exception:
    _HAS_GOOGLE_AUTH = False
PRODUCT_INFO_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ProductStudio product_info",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "product_attributes": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string", "minLength": 1},
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "description": {"type": "string", "minLength": 1},
                "brand": {"type": "string", "minLength": 1},
                "model": {"type": "string", "minLength": 1},
                "color": {"type": "string", "minLength": 1},
                "size": {"type": "string", "minLength": 1},
                "material": {"type": "string", "minLength": 1},
                "product": {"type": "string", "minLength": 1}
            }
        },
        "product_image": {
            "type": "object",
            "additionalProperties": False,
            "required": ["uri"],
            "properties": {
                "uri": {"type": "string", "format": "uri"}
            }
        }
    },
    "anyOf": [
        {"required": ["product_attributes"]},
        {"required": ["product_image"]}
    ]
}
_FORMAT_CHECKER = FormatChecker()
_VALIDATOR = Draft202012Validator(PRODUCT_INFO_SCHEMA, format_checker=_FORMAT_CHECKER)
def validate_product_info(payload: Dict[str, Any]) -> None:
    _VALIDATOR.validate(payload)
def to_camel_product_info(product_info_snake: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "product_attributes" in product_info_snake:
        out["productAttributes"] = dict(product_info_snake["product_attributes"])
    if "product_image" in product_info_snake:
        out["productImage"] = {"uri": product_info_snake["product_image"]["uri"]}
    return out
def to_camel_output_spec(output_spec_snake: Dict[str, Any]) -> Dict[str, Any]:
    m = {}
    if "workflow_id" in output_spec_snake: m["workflowId"] = output_spec_snake["workflow_id"]
    if output_spec_snake.get("tone"): m["tone"] = output_spec_snake["tone"]
    if output_spec_snake.get("target_language"): m["targetLanguage"] = output_spec_snake["target_language"]
    if output_spec_snake.get("attribute_separator"): m["attributeSeparator"] = output_spec_snake["attribute_separator"]
    if output_spec_snake.get("attribute_order"): m["attributeOrder"] = list(output_spec_snake["attribute_order"])
    return m
GOOGLE_CONTENT_SCOPE = "https://www.googleapis.com/auth/content"
@dataclass
class AuthConfig:
    api_key: Optional[str] = None
    use_adc: bool = False
    service_account_file: Optional[str] = None
    scopes: Tuple[str, ...] = (GOOGLE_CONTENT_SCOPE,)
def get_bearer_token(auth: AuthConfig) -> Optional[str]:
    if auth.api_key:
        return None
    if not _HAS_GOOGLE_AUTH:
        raise RuntimeError("google-auth not installed; install google-auth or provide --api-key.")
    if auth.service_account_file:
        creds = service_account.Credentials.from_service_account_file(
            auth.service_account_file, scopes=list(auth.scopes)
        )
    else:
        creds, _ = google.auth.default(scopes=list(auth.scopes))
    if not creds.valid:
        creds.refresh(GAuthRequest())
    return creds.token
class TextSuggestionsClient:
    BASE = "https://merchantapi.googleapis.com/productstudio/v1alpha"
    def __init__(self, account_id: Union[str, int], auth: AuthConfig, timeout_s: float = 30.0):
        self.account_id = str(account_id)
        self.auth = auth
        self.timeout_s = timeout_s
    def _endpoint(self) -> str:
        return f"{self.BASE}/accounts/{self.account_id}:generateProductTextSuggestions"
    def post_suggestions(
        self,
        product_info_snake: Dict[str, Any],
        output_spec_snake: Dict[str, Any],
        title_examples_camel: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 3,
        backoff_base: float = 0.7,
    ) -> Dict[str, Any]:
        validate_product_info(product_info_snake)
        body = {
            "productInfo": to_camel_product_info(product_info_snake),
            "outputSpec": to_camel_output_spec(output_spec_snake or {}),
        }
        if title_examples_camel:
            body["titleExamples"] = title_examples_camel
        headers = {"Content-Type": "application/json"}
        params = {}
        token = get_bearer_token(self.auth)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.auth.api_key:
            params["key"] = self.auth.api_key
        else:
            raise RuntimeError("No auth configured. Provide --api-key or OAuth (--use-adc / --service-account-file).")
        url = self._endpoint()
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(url, headers=headers, params=params, json=body, timeout=self.timeout_s)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Transient HTTP {resp.status_code}: {resp.text[:512]}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt == max_retries:
                    break
                time.sleep(backoff_base * (2 ** (attempt - 1)))
        raise RuntimeError(f"POST failed after {max_retries} attempts: {last_err}")
def _conn(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30, isolation_level=None)  # autocommit
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA busy_timeout = 5000;")
    return con
def ensure_product_exists(db_path: str, *, part_number: str, brand_name: str = "CLI Demo Brand") -> None:
    con = _conn(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM products WHERE part_number = ?", (part_number,))
        if cur.fetchone():
            return
        cur.execute("SELECT brand_id FROM brands WHERE brand_name = ?", (brand_name,))
        row = cur.fetchone()
        if row:
            brand_id = row[0]
        else:
            cur.execute("INSERT INTO brands (brand_name) VALUES (?)", (brand_name,))
            brand_id = cur.lastrowid
        cur.execute(
            """INSERT INTO products
               (part_number, brand_id, model_code, short_description, full_description, created_at, updated_at)
               VALUES (?, ?, 'CLI-MODEL', 'CLI seeded product', 'Seeded for text suggestions.',
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (part_number, brand_id),
        )
    finally:
        con.close()
def log_request_pre(
    db_path: str,
    *,
    part_number: str,
    product_info_snake: Dict[str, Any],
    output_spec_snake: Dict[str, Any]
) -> int:
    con = _conn(db_path)
    try:
        request_product_info = json.dumps(product_info_snake, ensure_ascii=False)
        request_raw_json = json.dumps(
            {"productInfo": to_camel_product_info(product_info_snake),
             "outputSpec": to_camel_output_spec(output_spec_snake or {})},
            ensure_ascii=False
        )
        workflow_id = (output_spec_snake or {}).get("workflow_id") or "title"
        tone = (output_spec_snake or {}).get("tone")
        target_language = (output_spec_snake or {}).get("target_language", "en")
        attribute_separator = (output_spec_snake or {}).get("attribute_separator", " - ")
        attribute_order_json = json.dumps((output_spec_snake or {}).get("attribute_order") or [], ensure_ascii=False)
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO ai_text_suggestions (
              part_number, workflow_id, tone, target_language, attribute_separator, attribute_order_json,
              request_product_info, request_raw_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok')
            """,
            (part_number, workflow_id, tone, target_language, attribute_separator, attribute_order_json,
             request_product_info, request_raw_json),
        )
        return int(cur.lastrowid)
    finally:
        con.close()
def log_response_post(db_path: str, *, row_id: int, response_json: Dict[str, Any]) -> None:
    con = _conn(db_path)
    try:
        title = response_json.get("title") or {}
        desc = response_json.get("description") or {}
        attributes = response_json.get("attributes")
        metadata = response_json.get("metadata")
        cur = con.cursor()
        cur.execute(
            """
            UPDATE ai_text_suggestions
               SET response_title_text = ?,
                   response_title_score = ?,
                   response_title_change_summary = ?,
                   response_desc_text = ?,
                   response_desc_score = ?,
                   response_desc_change_summary = ?,
                   response_attributes_json = ?,
                   response_metadata_json = ?,
                   status = 'ok',
                   error_message = NULL
             WHERE id = ?
            """,
            (
                title.get("text"),
                title.get("score"),
                title.get("changeSummary"),
                desc.get("text"),
                desc.get("score"),
                desc.get("changeSummary"),
                json.dumps(attributes, ensure_ascii=False) if attributes is not None else None,
                json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                row_id,
            ),
        )
    finally:
        con.close()
def log_error_post(db_path: str, *, row_id: int, error_message: str) -> None:
    con = _conn(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE ai_text_suggestions SET status='error', error_message=? WHERE id=?",
            (error_message[:2000], row_id),
        )
    finally:
        con.close()
def build_product_info_from_view_row(row: Tuple[Any, ...],
                                     require_attributes: bool = False,
                                     require_image: bool = False) -> Optional[Dict[str, Any]]:
    """
    row layout (vw_ps_product_info):
      (part_number, brand, model, title, description, category_code, color, size, material, image_uri)
    """
    pa: Dict[str, str] = {}
    if row[3]: pa["title"] = str(row[3]).strip()
    if row[4]: pa["description"] = str(row[4]).strip()
    if row[1]: pa["brand"] = str(row[1]).strip()
    if row[2]: pa["model"] = str(row[2]).strip()
    if row[6]: pa["color"] = str(row[6]).strip()
    if row[7]: pa["size"] = str(row[7]).strip()
    if row[8]: pa["material"] = str(row[8]).strip()
    payload: Dict[str, Any] = {}
    if pa:
        payload["product_attributes"] = {k: v for k, v in pa.items() if v}
    img_uri = row[9]
    if img_uri:
        payload["product_image"] = {"uri": str(img_uri).strip()}
    if require_attributes and "product_attributes" not in payload:
        return None
    if require_image and "product_image" not in payload:
        return None
    if not payload:
        return None
    return payload
def fetch_rows_for_skus(db_path: str, skus: Sequence[str]) -> Dict[str, Tuple[Any, ...]]:
    con = _conn(db_path)
    try:
        q = """
            SELECT part_number, brand, model, title, description, category_code, color, size, material, image_uri
            FROM vw_ps_product_info
            WHERE part_number IN ({})
        """.format(",".join("?" for _ in skus))
        cur = con.cursor()
        cur.execute(q, tuple(skus))
        return {r[0]: r for r in cur.fetchall()}
    finally:
        con.close()
def fetch_rows_batch(db_path: str, limit: int, where_sql: Optional[str]=None, params: Sequence[Any]=()) -> List[Tuple[Any, ...]]:
    con = _conn(db_path)
    try:
        base = """
            SELECT part_number, brand, model, title, description, category_code, color, size, material, image_uri
            FROM vw_ps_product_info
        """
        if where_sql:
            base += f" WHERE {where_sql} "
        base += " LIMIT ?"
        cur = con.cursor()
        cur.execute(base, tuple(params) + (limit,))
        return cur.fetchall()
    finally:
        con.close()
def process_one(
    *,
    db_path: str,
    account_id: str,
    auth: AuthConfig,
    part_number: str,
    row: Tuple[Any, ...],
    output_spec_snake: Dict[str, Any],
    client_timeout: float,
    client_retries: int,
    backoff_base: float,
    dry_run: bool,
    require_attributes: bool,
    require_image: bool,
) -> Tuple[str, str, Optional[str]]:
    """
    Returns: (part_number, status, message_or_title)
      status: "ok" | "skip" | "error"
    """
    payload = build_product_info_from_view_row(row, require_attributes=require_attributes, require_image=require_image)
    if not payload:
        return (part_number, "skip", "insufficient data (attrs/image)")
    try:
        validate_product_info(payload)
    except ValidationError as ve:
        loc = " → ".join(str(p) for p in ve.path) or "(root)"
        return (part_number, "skip", f"schema invalid at {loc}: {ve.message}")
    if dry_run:
        return (part_number, "ok", "dry-run")
    ensure_product_exists(db_path, part_number=part_number)
    row_id = log_request_pre(
        db_path,
        part_number=part_number,
        product_info_snake=payload,
        output_spec_snake=output_spec_snake,
    )
    try:
        client = TextSuggestionsClient(account_id=account_id, auth=auth, timeout_s=client_timeout)
        resp = client.post_suggestions(
            product_info_snake=payload,
            output_spec_snake=output_spec_snake,
            title_examples_camel=None,
            max_retries=client_retries,
            backoff_base=backoff_base,
        )
        log_response_post(db_path, row_id=row_id, response_json=resp)
        title_text = (resp.get("title") or {}).get("text")
        return (part_number, "ok", title_text or "generated")
    except Exception as e:
        log_error_post(db_path, row_id=row_id, error_message=str(e))
        return (part_number, "error", str(e))
def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="suggest-text",
        description="Generate Google Product Studio text suggestions (title/description) for products."
    )
    p.add_argument("--db", required=True, help="Path to SQLite DB (with schema + views).")
    p.add_argument("--account", required=True, help="Merchant Center ACCOUNT_ID.")
    g_auth = p.add_argument_group("auth")
    g_auth.add_argument("--api-key", help="Product Studio API key (alternative to OAuth).")
    g_auth.add_argument("--use-adc", action="store_true", help="Use Application Default Credentials for OAuth.")
    g_auth.add_argument("--service-account-file", help="Path to service-account JSON for OAuth.")
    g_sel = p.add_argument_group("selection")
    g_sel.add_argument("--sku", action="append", help="SKU/part_number to process. Repeat for multiple.")
    g_sel.add_argument("--sku-file", help="File with one SKU per line.")
    g_sel.add_argument("--limit", type=int, default=50, help="When no SKUs are provided, take first N from view (default 50).")
    g_sel.add_argument("--where", help="Optional SQL WHERE for vw_ps_product_info (e.g., \"brand='Nike' AND color IS NOT NULL\").")
    g_out = p.add_argument_group("output")
    g_out.add_argument("--workflow-id", default="tide", choices=["title", "description", "tide"])
    g_out.add_argument("--tone", choices=["default","playful","formal","persuasive","conversational"])
    g_out.add_argument("--target-language", default="en")
    g_out.add_argument("--attribute-separator", default=" - ")
    g_out.add_argument("--attribute-order", help="Comma-separated keys, e.g., brand,product,color,size")
    g_beh = p.add_argument_group("behavior")
    g_beh.add_argument("--dry-run", action="store_true", help="Validate & simulate only. No POST, no DB writes.")
    g_beh.add_argument("--concurrency", type=int, default=4, help="Parallel workers (default 4).")
    g_beh.add_argument("--timeout-s", type=float, default=30.0, help="HTTP timeout per call.")
    g_beh.add_argument("--max-retries", type=int, default=3, help="Retry attempts on 429/5xx.")
    g_beh.add_argument("--backoff-base", type=float, default=0.7, help="Exponential backoff base seconds.")
    g_beh.add_argument("--require-attributes", action="store_true", help="Skip products without product_attributes.")
    g_beh.add_argument("--require-image", action="store_true", help="Skip products without product_image.")
    g_beh.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)
def collect_skus(args: argparse.Namespace) -> List[str]:
    skus: List[str] = []
    if args.sku:
        skus.extend([s.strip() for s in args.sku if s and s.strip()])
    if args.sku_file:
        with open(args.sku_file, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    skus.append(s)
    return list(dict.fromkeys(skus))  # dedupe, keep order
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    auth = AuthConfig(
        api_key=args.api_key if args.api_key else None,
        use_adc=args.use_adc,
        service_account_file=args.service_account_file
    )
    out_spec: Dict[str, Any] = {
        "workflow_id": args.workflow_id,
        "target_language": args.target_language,
        "attribute_separator": args.attribute_separator
    }
    if args.tone:
        out_spec["tone"] = args.tone
    if args.attribute_order:
        out_spec["attribute_order"] = [s.strip() for s in args.attribute_order.split(",") if s.strip()]
    skus = collect_skus(args)
    rows_by_sku: Dict[str, Tuple[Any, ...]] = {}
    if skus:
        if args.verbose:
            print(f"[info] Loading {len(skus)} SKU(s) from vw_ps_product_info...")
        rows_by_sku = fetch_rows_for_skus(args.db, skus)
        missing = [s for s in skus if s not in rows_by_sku]
        if missing:
            print(f"[warn] {len(missing)} SKU(s) not found in vw_ps_product_info: {', '.join(missing[:10])}{'…' if len(missing)>10 else ''}")
    else:
        rows = fetch_rows_batch(args.db, limit=args.limit, where_sql=args.where, params=())
        rows_by_sku = {r[0]: r for r in rows}
        if args.verbose:
            print(f"[info] Pulled {len(rows_by_sku)} row(s) from vw_ps_product_info (limit={args.limit}).")
    if not rows_by_sku:
        print("[info] Nothing to do.")
        return 0
    successes = 0
    skips = 0
    errors = 0
    def _task(item):
        pn, row = item
        return process_one(
            db_path=args.db,
            account_id=str(args.account),
            auth=auth,
            part_number=pn,
            row=row,
            output_spec_snake=out_spec,
            client_timeout=args.timeout_s,
            client_retries=args.max_retries,
            backoff_base=args.backoff_base,
            dry_run=args.dry_run,
            require_attributes=args.require_attributes,
            require_image=args.require_image,
        )
    items = list(rows_by_sku.items())
    with cf.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        for pn, status, msg in ex.map(_task, items):
            if status == "ok":
                successes += 1
                if args.verbose:
                    print(f"[ok] {pn}: {msg}")
            elif status == "skip":
                skips += 1
                if args.verbose:
                    print(f"[skip] {pn}: {msg}")
            else:
                errors += 1
                print(f"[error] {pn}: {msg}")
    print(f"\nSummary: ok={successes} skip={skips} error={errors} total={len(items)}")
    return 0 if errors == 0 else 2
if __name__ == "__main__":
    sys.exit(main())
