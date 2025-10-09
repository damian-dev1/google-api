import os
import csv
import json
import time
import base64
import copy
import random
import threading
import logging
import queue
from typing import Optional, List, Dict, Any
import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
LOG = logging.getLogger("api_router")
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    LOG.addHandler(_handler)
SETTINGS_FILE = "settings.json"
DEFAULT_PROFILE = {
    "name": "default-router",
    "url": "https://api.example.com/restapi/v4/orders/", "method": "GET",
    "timeout": 20, "batch_size": 200, "max_retries": 5, "allow_redirects": True, "verify": True,
    "params": {"limit": 200, "offset": 0}, "headers": {"Content-Type": "application/json", "Accept": "application/json"},
    "sort_enabled": False, "sort": "desc", "status_enabled": False, "status": "",
    "rate_limit_enabled": True, "requests_per_minute": 150,
    "body_mode": "json", "body": {},
    "auth_type": "basic", "username": "your-username", "password": "your-password",
    "bearer_token": "", "api_key_name": "X-API-Key", "api_key_value": "",
}
DEFAULT_SETTINGS = {"current_profile": "default-router", "profiles": {"default-router": DEFAULT_PROFILE}}
class SettingsManager:
    """Handles loading, saving, and managing all connection profiles."""
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.settings = self._load()
    def _deep_merge(self, a: dict, b: dict) -> dict:
        out = copy.deepcopy(a)
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = self._deep_merge(out[k], v)
            else:
                out[k] = v
        return out
    def _load(self) -> dict:
        if not os.path.exists(self.file_path):
            return copy.deepcopy(DEFAULT_SETTINGS)
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = self._deep_merge(copy.deepcopy(DEFAULT_SETTINGS), data)
            cp = merged.get("current_profile") or "default-router"
            if cp not in merged["profiles"]:
                merged["profiles"][cp] = copy.deepcopy(DEFAULT_PROFILE)
            return merged
        except Exception as e:
            LOG.exception("Failed to load settings")
            messagebox.showerror("Error", f"Failed to load settings:\n{e}")
            return copy.deepcopy(DEFAULT_SETTINGS)
    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            LOG.exception("Failed to save settings")
            messagebox.showerror("Error", f"Failed to save settings:\n{e}")
    def get_current_profile_name(self) -> str:
        return self.settings.get("current_profile", "default-router")

    def get_current_profile(self) -> Dict[str, Any]:
        name = self.get_current_profile_name()
        return copy.deepcopy(self.settings["profiles"].get(name, DEFAULT_PROFILE))
    
    def update_current_profile(self, profile_data: dict):
        name = self.get_current_profile_name()
        self.settings["profiles"][name] = profile_data

    def get_profile_names(self) -> List[str]:
        return list(self.settings["profiles"].keys())

    def set_current_profile_name(self, name: str):
        if name in self.settings["profiles"]:
            self.settings["current_profile"] = name
            self.save()

    def save_profile(self, name: str, profile_data: dict):
        self.settings["profiles"][name] = profile_data
        self.save()

class RateLimiter:
    """A thread-safe token bucket rate limiter."""
    def __init__(self, rpm: int):
        self.capacity = max(1, int(rpm))
        self.tokens = float(self.capacity)
        self.fill_rate = self.capacity / 60.0
        self.ts = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.ts
            self.ts = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            if self.tokens < 1.0:
                sleep_for = (1.0 - self.tokens) / self.fill_rate
                time.sleep(sleep_for)
                self.ts = time.monotonic()
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class APIClient:
    """Handles making robust, rate-limited, and retrying API requests."""
    def __init__(self, profile: dict, cancel_evt: threading.Event):
        self.p = profile
        self.cancel_evt = cancel_evt
        self.sess = requests.Session()
        self._configure_session()
        self.limiter = RateLimiter(self.p["requests_per_minute"]) if self.p.get("rate_limit_enabled", True) else None

    def _configure_session(self):
        headers = copy.deepcopy(self.p.get("headers", {})) or {}
        auth_type = (self.p.get("auth_type") or "none").lower()
        if auth_type == "basic":
            u, pw = self.p.get("username", ""), self.p.get("password", "")
            auth = base64.b64encode(f"{u}:{pw}".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"
        elif auth_type == "bearer":
            token = self.p.get("bearer_token", "")
            if token: headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            key_name = self.p.get("api_key_name", "X-API-Key")
            key_value = self.p.get("api_key_value", "")
            if key_name and key_value: headers[key_name] = key_value
        self.sess.headers.clear()
        self.sess.headers.update(headers)

    def _sleep_with_cancel(self, secs: float):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if self.cancel_evt.is_set(): return
            time.sleep(min(0.2, end - time.monotonic()))

    def _make_request(self, url: str, params: dict, body: Any, attempt: int = 0) -> (int, Any):
        if self.cancel_evt.is_set(): return 0, None

        method = self.p.get("method", "GET").upper()
        max_retries = int(self.p.get("max_retries", 5))
        
        if self.limiter: self.limiter.acquire()

        try:
            req_kwargs = {
                "method": method, "url": url, "params": params,
                "timeout": int(self.p.get("timeout", 20)),
                "allow_redirects": bool(self.p.get("allow_redirects", True)),
                "verify": bool(self.p.get("verify", True))
            }
            if method in ("POST", "PUT", "PATCH"):
                if self.p.get("body_mode", "json").lower() == "json":
                    req_kwargs["json"] = body
                else:
                    req_kwargs["data"] = body

            resp = self.sess.request(**req_kwargs)

            if resp.status_code == 429 and attempt < max_retries:
                ra = resp.headers.get("Retry-After")
                sleep_for = float(ra) if ra and ra.isdigit() else 2 ** attempt + random.random()
                LOG.warning(f"429 Too Many Requests. Sleeping {sleep_for:.2f}s...")
                self._sleep_with_cancel(sleep_for)
                return self._make_request(url, params, body, attempt + 1)
            
            if resp.ok:
                try: return resp.status_code, resp.json()
                except json.JSONDecodeError: return resp.status_code, resp.text
            
            if attempt < max_retries:
                backoff = 2 ** attempt + random.random()
                LOG.warning(f"HTTP {resp.status_code}. Retrying in {backoff:.2f}s...")
                self._sleep_with_cancel(backoff)
                return self._make_request(url, params, body, attempt + 1)

            LOG.error(f"Request failed after {max_retries} retries. Status {resp.status_code}.")
            return resp.status_code, resp.text

        except requests.RequestException as e:
            if attempt < max_retries:
                backoff = 2 ** attempt + random.random()
                LOG.warning(f"Exception: {e}. Retrying in {backoff:.2f}s...")
                self._sleep_with_cancel(backoff)
                return self._make_request(url, params, body, attempt + 1)
            LOG.exception("Unrecoverable error during request")
            return 0, str(e)

    def fetch_all_paginated(self, part_number: Optional[str], progress_cb=None) -> List[dict]:
        url, body = self.p["url"], self.p.get("body", {})
        base_params = copy.deepcopy(self.p.get("params", {})) or {}
        if self.p.get("sort_enabled"): base_params["sort"] = self.p.get("sort", "desc")
        if self.p.get("status_enabled") and self.p.get("status", "").strip():
            base_params["status"] = self.p.get("status", "").strip()
        if part_number: base_params["part_number"] = part_number
        
        limit = int(self.p.get("batch_size", base_params.get("limit", 200)))
        base_params["limit"] = limit
        offset = int(base_params.get("offset", 0))
        results, total_count = [], None

        while not self.cancel_evt.is_set():
            params = {**base_params, "offset": offset, "limit": limit}
            if progress_cb: progress_cb(f"Fetching offset {offset} (limit {limit})...")
            
            status, payload = self._make_request(url, params, body)
            if status not in range(200, 300) or not isinstance(payload, dict): break
            
            if total_count is None: total_count = int(payload.get("count", 0))
            
            batch = payload.get("results") or []
            results.extend(batch)

            if progress_cb:
                msg = f"Fetched {len(results)}/{total_count}..." if total_count else f"Fetched {len(results)}..."
                progress_cb(msg)
            
            if not payload.get("next") or len(batch) < limit: break
            offset += limit
            
        return results

# --- GUI Tab Classes ---

class ProfileTab(ttk.Frame):
    PAD = 4
    AUTH_TYPES = ["none", "basic", "bearer", "api_key"]
    def __init__(self, parent, settings_manager: SettingsManager, on_profile_change_callback):
        super().__init__(parent, padding=self.PAD)
        self.sm = settings_manager
        self.on_profile_change = on_profile_change_callback
        self._build_widgets()
        self.load_profile_into_ui()
    def _build_widgets(self):
        row = 0
        ttk.Label(self, text="Profile").grid(row=row, column=0, sticky="e", padx=self.PAD, pady=self.PAD)
        self.cmb_profile = ttk.Combobox(self, values=self.sm.get_profile_names(), state="readonly", width=28)
        self.cmb_profile.set(self.sm.get_current_profile_name())
        self.cmb_profile.grid(row=row, column=1, sticky="w", padx=self.PAD, pady=self.PAD)
        ttk.Button(self, text="Load", command=self.on_profile_load).grid(row=row, column=2, padx=self.PAD, pady=self.PAD)
        ttk.Button(self, text="Save", command=self.on_profile_save).grid(row=row, column=3, padx=self.PAD, pady=self.PAD)
        row += 1
        ttk.Button(self, text="Save As…", command=self.on_profile_save_as).grid(row=row, column=3, padx=self.PAD, pady=self.PAD)
        ttk.Label(self, text="Base URL").grid(row=row, column=0, sticky="e", padx=self.PAD, pady=self.PAD)
        self.ent_url = ttk.Entry(self, width=64)
        self.ent_url.grid(row=row, column=1, columnspan=3, sticky="we", padx=self.PAD, pady=self.PAD)
        row += 1
        ttk.Label(self, text="Auth Type").grid(row=row, column=0, sticky="e", padx=self.PAD, pady=self.PAD)
        self.cmb_auth = ttk.Combobox(self, values=self.AUTH_TYPES, state="readonly", width=12)
        self.cmb_auth.grid(row=row, column=1, sticky="w", padx=self.PAD, pady=self.PAD)
        self.cmb_auth.bind("<<ComboboxSelected>>", lambda e: self._build_auth_fields())
        row += 1
        self.auth_frame = ttk.Frame(self)
        self.auth_frame.grid(row=row, column=0, columnspan=4, sticky="we", padx=self.PAD, pady=self.PAD)
        self.auth_frame.grid_columnconfigure(1, weight=1)
        self.auth_frame.grid_columnconfigure(3, weight=1)
        self.columnconfigure(1, weight=1)
    def _build_auth_fields(self):
        for w in self.auth_frame.winfo_children(): w.destroy()
        auth_type = self.cmb_auth.get()
        profile = self.sm.get_current_profile()
        if auth_type == "basic":
            ttk.Label(self.auth_frame, text="Username").grid(row=0, column=0, sticky="e", padx=self.PAD)
            self.ent_user = ttk.Entry(self.auth_frame, width=20)
            self.ent_user.insert(0, profile.get("username", ""))
            self.ent_user.grid(row=0, column=1, sticky="w", padx=self.PAD)
            ttk.Label(self.auth_frame, text="Password").grid(row=0, column=2, sticky="e", padx=self.PAD)
            self.ent_pass = ttk.Entry(self.auth_frame, width=20, show="*")
            self.ent_pass.insert(0, profile.get("password", ""))
            self.ent_pass.grid(row=0, column=3, sticky="w", padx=self.PAD)
        elif auth_type == "bearer":
            ttk.Label(self.auth_frame, text="Bearer Token").grid(row=0, column=0, sticky="e", padx=self.PAD)
            self.ent_token = ttk.Entry(self.auth_frame, width=40, show="*")
            self.ent_token.insert(0, profile.get("bearer_token", ""))
            self.ent_token.grid(row=0, column=1, columnspan=3, sticky="we", padx=self.PAD)
        elif auth_type == "api_key":
            ttk.Label(self.auth_frame, text="Key Header").grid(row=0, column=0, sticky="e", padx=self.PAD)
            self.ent_keyname = ttk.Entry(self.auth_frame, width=20)
            self.ent_keyname.insert(0, profile.get("api_key_name", "X-API-Key"))
            self.ent_keyname.grid(row=0, column=1, sticky="w", padx=self.PAD)
            ttk.Label(self.auth_frame, text="Key Value").grid(row=0, column=2, sticky="e", padx=self.PAD)
            self.ent_keyvalue = ttk.Entry(self.auth_frame, width=20, show="*")
            self.ent_keyvalue.insert(0, profile.get("api_key_value", ""))
            self.ent_keyvalue.grid(row=0, column=3, sticky="w", padx=self.PAD)
    def load_profile_into_ui(self):
        profile = self.sm.get_current_profile()
        self.ent_url.delete(0, "end"); self.ent_url.insert(0, profile["url"])
        self.cmb_auth.set(profile.get("auth_type", "none"))
        self._build_auth_fields()
        LOG.info(f"[Profile] Loaded '{self.sm.get_current_profile_name()}' into UI.")
    def collect_ui_into_profile(self) -> Optional[dict]:
        profile = self.sm.get_current_profile()
        try:
            profile["url"] = self.ent_url.get().strip()
            profile["auth_type"] = self.cmb_auth.get().strip().lower()
            auth_type = profile["auth_type"]
            if auth_type == "basic":
                profile["username"] = self.ent_user.get(); profile["password"] = self.ent_pass.get()
            elif auth_type == "bearer":
                profile["bearer_token"] = self.ent_token.get()
            elif auth_type == "api_key":
                profile["api_key_name"] = self.ent_keyname.get().strip() or "X-API-Key"; profile["api_key_value"] = self.ent_keyvalue.get()
            return profile
        except Exception as e:
            messagebox.showerror("Error", f"Could not read profile from UI: {e}"); return None
    def on_profile_load(self):
        sel = self.cmb_profile.get();
        if not sel: return
        self.sm.set_current_profile_name(sel); self.load_profile_into_ui(); self.on_profile_change()
    def on_profile_save(self):
        profile_data = self.collect_ui_into_profile();
        if not profile_data: return
        self.sm.save_profile(self.sm.get_current_profile_name(), profile_data)
        LOG.info(f"[Profile] Saved '{self.sm.get_current_profile_name()}'.")
        messagebox.showinfo("Success", "Profile saved.")
    def on_profile_save_as(self):
        new_name = simpledialog.askstring("Save Profile As", "Enter new profile name:");
        if not new_name: return
        profile_data = self.collect_ui_into_profile();
        if not profile_data: return
        profile_data["name"] = new_name
        self.sm.save_profile(new_name, profile_data); self.sm.set_current_profile_name(new_name)
        self.cmb_profile["values"] = self.sm.get_profile_names(); self.cmb_profile.set(new_name)
        LOG.info(f"[Profile] Saved as '{new_name}'.")

class RequestSettingsTab(ttk.Frame):
    PAD = 4; METHODS = ["GET", "POST", "PUT", "PATCH"]; SORT_OPTIONS = ["desc", "asc"]; STATUS_OPTIONS = ["", "ORDER_ACK", "DISPATCHED", "CANCELLED", "BACKORDER"]; PAGE_SIZES = [50, 100, 200, 500, 1000]; RPM_PRESETS = [60, 120, 150, 300, 600]
    def __init__(self, parent, settings_manager: SettingsManager):
        super().__init__(parent, padding=self.PAD)
        self.sm = settings_manager
        self._build_widgets()
        self.load_profile_into_ui()
    def _build_widgets(self):
        f = self; row = 0
        ttk.Label(f, text="Method").grid(row=row, column=0); self.cmb_method = ttk.Combobox(f, values=self.METHODS, state="readonly", width=8); self.cmb_method.grid(row=row, column=1)
        ttk.Label(f, text="Timeout").grid(row=row, column=2); self.spn_timeout = ttk.Spinbox(f, from_=1, to=600, width=5); self.spn_timeout.grid(row=row, column=3)
        ttk.Label(f, text="Page Size").grid(row=row, column=4); self.cmb_pagesize = ttk.Combobox(f, values=[str(x) for x in self.PAGE_SIZES], state="readonly", width=5); self.cmb_pagesize.grid(row=row, column=5)
        row += 1
        self.var_sort = tk.BooleanVar(); ttk.Checkbutton(f, text="Sort", variable=self.var_sort).grid(row=row, column=0)
        self.cmb_sort = ttk.Combobox(f, values=self.SORT_OPTIONS, state="readonly", width=8); self.cmb_sort.grid(row=row, column=1)
        self.var_status = tk.BooleanVar(); ttk.Checkbutton(f, text="Status", variable=self.var_status).grid(row=row, column=2)
        self.cmb_status = ttk.Combobox(f, values=self.STATUS_OPTIONS, width=12); self.cmb_status.grid(row=row, column=3, columnspan=3, sticky='w')
        row += 1
        self.var_rl = tk.BooleanVar(); ttk.Checkbutton(f, text="Rate Limit", variable=self.var_rl).grid(row=row, column=0)
        self.cmb_rpm = ttk.Combobox(f, values=[str(x) for x in self.RPM_PRESETS], state="readonly", width=8); self.cmb_rpm.grid(row=row, column=1)
        self.var_redirects = tk.BooleanVar(); ttk.Checkbutton(f, text="Redirects", variable=self.var_redirects).grid(row=row, column=2)
        self.var_verify = tk.BooleanVar(); ttk.Checkbutton(f, text="Verify SSL", variable=self.var_verify).grid(row=row, column=3)
        row += 1
        ttk.Button(f, text="Save Settings", command=self.on_save_settings).grid(row=row, column=0, columnspan=2, pady=self.PAD)
    def load_profile_into_ui(self):
        p = self.sm.get_current_profile()
        self.cmb_method.set(p["method"].upper()); self.spn_timeout.delete(0, "end"); self.spn_timeout.insert(0, str(p["timeout"])); self.cmb_pagesize.set(str(p["batch_size"]))
        self.var_sort.set(p["sort_enabled"]); self.cmb_sort.set(p["sort"]); self.var_status.set(p["status_enabled"]); self.cmb_status.set(p["status"])
        self.var_rl.set(p["rate_limit_enabled"]); self.cmb_rpm.set(str(p["requests_per_minute"])); self.var_redirects.set(p["allow_redirects"]); self.var_verify.set(p["verify"])
        LOG.info("[RequestSettings] UI loaded from current profile.")
    def on_save_settings(self):
        try:
            p = self.sm.get_current_profile()
            p["method"] = self.cmb_method.get(); p["timeout"] = int(self.spn_timeout.get()); p["batch_size"] = int(self.cmb_pagesize.get())
            p["sort_enabled"] = self.var_sort.get(); p["sort"] = self.cmb_sort.get(); p["status_enabled"] = self.var_status.get(); p["status"] = self.cmb_status.get()
            p["rate_limit_enabled"] = self.var_rl.get(); p["requests_per_minute"] = int(self.cmb_rpm.get()); p["allow_redirects"] = self.var_redirects.get(); p["verify"] = self.var_verify.get()
            self.sm.update_current_profile(p); self.sm.save()
            LOG.info("[RequestSettings] Settings saved to current profile.")
            messagebox.showinfo("Success", "Request settings saved.")
        except Exception as e: messagebox.showerror("Error", f"Invalid settings: {e}")

class PostmanTab(ttk.Frame):
    PAD = 4; METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
    def __init__(self, parent):
        super().__init__(parent, padding=self.PAD)
        self.request_queue = queue.Queue(); self._build_widgets(); self.after(100, self._process_queue)
    def _build_widgets(self):
        req_bar = ttk.Frame(self); req_bar.pack(fill=tk.X, pady=(0, 5)); req_bar.columnconfigure(1, weight=1)
        self.cmb_method = ttk.Combobox(req_bar, values=self.METHODS, state="readonly", width=8); self.cmb_method.set("GET"); self.cmb_method.grid(row=0, column=0, padx=(0, self.PAD))
        self.ent_url = ttk.Entry(req_bar); self.ent_url.grid(row=0, column=1, sticky="ew")
        self.btn_send = ttk.Button(req_bar, text="Send", command=self._send_request); self.btn_send.grid(row=0, column=2, padx=(self.PAD, 0))
        paned_window = ttk.PanedWindow(self, orient=tk.VERTICAL); paned_window.pack(fill=tk.BOTH, expand=True)
        req_notebook = ttk.Notebook(paned_window)
        self.txt_params = self._create_scrolled_text(req_notebook); self.txt_headers = self._create_scrolled_text(req_notebook); self.txt_body = self._create_scrolled_text(req_notebook)
        req_notebook.add(self.txt_params, text="Params"); req_notebook.add(self.txt_headers, text="Headers"); req_notebook.add(self.txt_body, text="Body")
        paned_window.add(req_notebook, weight=1)
        res_frame = ttk.Frame(paned_window); res_frame.rowconfigure(1, weight=1); res_frame.columnconfigure(0, weight=1)
        self.lbl_status = ttk.Label(res_frame, text="Status: Idle"); self.lbl_status.grid(row=0, column=0, sticky="w", pady=(0, self.PAD))
        res_notebook = ttk.Notebook(res_frame)
        self.txt_res_body = self._create_scrolled_text(res_notebook); self.txt_res_headers = self._create_scrolled_text(res_notebook)
        res_notebook.add(self.txt_res_body, text="Body"); res_notebook.add(self.txt_res_headers, text="Headers"); res_notebook.grid(row=1, column=0, sticky="nsew")
        paned_window.add(res_frame, weight=2)
    def _create_scrolled_text(self, parent): return tk.Text(parent, wrap="none", height=3, font=("Consolas", 9), undo=True)
    def _send_request(self):
        url = self.ent_url.get().strip()
        if not url: messagebox.showerror("Error", "URL cannot be empty."); return
        self.btn_send.config(state="disabled"); self.lbl_status.config(text="Status: Sending...")
        threading.Thread(target=self._request_worker, daemon=True).start()
    def _request_worker(self):
        try:
            method, url = self.cmb_method.get(), self.ent_url.get().strip()
            params = dict(p.split('=', 1) for p in self.txt_params.get("1.0", "end-1c").strip().split('&') if '=' in p)
            headers_str = self.txt_headers.get("1.0", "end-1c").strip(); headers = json.loads(headers_str) if headers_str else {}
            body_str = self.txt_body.get("1.0", "end-1c").strip(); body = json.loads(body_str) if body_str else {}
            start_time = time.time()
            response = requests.request(method=method, url=url, params=params, headers=headers, json=body, timeout=20)
            duration = time.time() - start_time
            self.request_queue.put(('success', (response, duration)))
        except (json.JSONDecodeError, requests.RequestException) as e: self.request_queue.put(('error', str(e)))
    def _process_queue(self):
        try:
            msg_type, data = self.request_queue.get_nowait(); self.btn_send.config(state="normal")
            if msg_type == 'success':
                response, duration = data
                self.lbl_status.config(text=f"Status: {response.status_code} {response.reason} | Time: {duration:.2f}s | Size: {len(response.content)/1024:.2f} KB")
                self.txt_res_body.delete("1.0", tk.END)
                try: self.txt_res_body.insert("1.0", json.dumps(response.json(), indent=2))
                except json.JSONDecodeError: self.txt_res_body.insert("1.0", response.text)
                self.txt_res_headers.delete("1.0", tk.END); self.txt_res_headers.insert("1.0", json.dumps(dict(response.headers), indent=2))
            elif msg_type == 'error':
                self.lbl_status.config(text=f"Status: Error"); self.txt_res_body.delete("1.0", tk.END); self.txt_res_body.insert("1.0", data); self.txt_res_headers.delete("1.0", tk.END)
        except queue.Empty: pass
        finally: self.after(100, self._process_queue)

class BulkTab(ttk.Frame):
    PAD = 4; CSV_HEADERS = ["Order Reference", "Order Date", "Status", "Item Name", "Quantity", "Total", "Shipping Full Name", "Address Line 1", "City", "State", "Postal Code", "Country"]
    def __init__(self, parent, settings_manager: SettingsManager, cancel_event: threading.Event):
        super().__init__(parent, padding=self.PAD)
        self.sm = settings_manager; self.cancel_event = cancel_event
        self._bulk_rows = None; self.bulk_headers: List[str] = []
        self._build_widgets()
    def _build_widgets(self):
        f = self; row = 0; f.columnconfigure(1, weight=1)
        ttk.Button(f, text="Import CSV…", command=self.on_import_csv).grid(row=row, column=0, padx=self.PAD, pady=self.PAD, sticky="w")
        self.lbl_bulk_file = ttk.Label(f, text="No file loaded", foreground="#666"); self.lbl_bulk_file.grid(row=row, column=1, columnspan=3, sticky="w", padx=self.PAD, pady=self.PAD)        
        row += 1
        ttk.Label(f, text="Part # Column").grid(row=row, column=0, sticky="e", padx=self.PAD, pady=self.PAD)
        self.cmb_bulk_col = ttk.Combobox(f, values=[], state="disabled", width=28); self.cmb_bulk_col.grid(row=row, column=1, sticky="w", padx=self.PAD, pady=self.PAD)
        self.btn_run_bulk = ttk.Button(f, text="Run Bulk", command=self.on_run_bulk, state="disabled"); self.btn_run_bulk.grid(row=row, column=2, padx=self.PAD, pady=self.PAD, sticky="w")
        self.btn_cancel_bulk = ttk.Button(f, text="Cancel", command=self.on_cancel, state="disabled"); self.btn_cancel_bulk.grid(row=row, column=3, padx=self.PAD, pady=self.PAD, sticky="e")
        row += 1
        self.lbl_bulk_status = ttk.Label(f, text="Ready."); self.lbl_bulk_status.grid(row=row, column=0, columnspan=4, sticky="w", padx=self.PAD, pady=self.PAD)
        row += 1
        self.progress = ttk.Progressbar(f, orient="horizontal", mode="determinate"); self.progress.grid(row=row, column=0, columnspan=4, sticky="ew", padx=self.PAD, pady=self.PAD)
    def on_import_csv(self):
        path = filedialog.askopenfilename(title="Select CSV", filetypes=[("CSV Files", "*.csv")]);
        if not path: return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f); self.bulk_headers = next(reader); self._bulk_rows = list(reader)
            self.lbl_bulk_file.config(text=f"{os.path.basename(path)} ({len(self._bulk_rows)} rows)"); self.cmb_bulk_col["values"] = self.bulk_headers; self.cmb_bulk_col.config(state="readonly"); self.btn_run_bulk.config(state="normal")
            if self.bulk_headers: self.cmb_bulk_col.set(self.bulk_headers[0])
            LOG.info(f"Loaded CSV: {path}")
        except Exception as e: messagebox.showerror("Error", f"Failed to read CSV: {e}")
    def on_run_bulk(self):
        if not self._bulk_rows: messagebox.showerror("Error", "No CSV data loaded."); return
        col_name = self.cmb_bulk_col.get();
        if not col_name: messagebox.showerror("Error", "Please select a Part Number column."); return
        self.cancel_event.clear(); self.btn_run_bulk.config(state="disabled"); self.btn_cancel_bulk.config(state="normal"); self.progress["value"] = 0
        threading.Thread(target=self._bulk_worker, args=(col_name,), daemon=True).start()
    def _bulk_worker(self, col_name: str):
        try:
            col_idx = self.bulk_headers.index(col_name)
            all_results = []
            total_rows = len(self._bulk_rows)
            for i, row in enumerate(self._bulk_rows):
                if self.cancel_event.is_set(): LOG.warning("Bulk run cancelled."); break
                part_num = row[col_idx].strip()
                if not part_num: continue
                self.lbl_bulk_status.config(text=f"Processing {i+1}/{total_rows}: {part_num}...")
                client = APIClient(self.sm.get_current_profile(), self.cancel_event)
                results = client.fetch_all_paginated(part_num, progress_cb=lambda msg: self.lbl_bulk_status.config(text=f"Row {i+1}/{total_rows}: {msg}"))
                all_results.extend(results)
                self.progress["value"] = (i + 1) * 100 / total_rows
            if not self.cancel_event.is_set():
                self.lbl_bulk_status.config(text=f"Bulk run complete. Found {len(all_results)} total orders.")
                self._prompt_and_export(all_results)
        except Exception as e: LOG.exception("Bulk worker failed"); self.lbl_bulk_status.config(text=f"Error: {e}")
        finally: self.btn_run_bulk.config(state="normal"); self.btn_cancel_bulk.config(state="disabled")
    def _prompt_and_export(self, results: List[dict]):
        if not results: messagebox.showinfo("Export", "No results to export."); return
        path = filedialog.asksaveasfilename(title="Save Results", defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not path: return
        try:
            self._export_orders_atomic(results, path)
            LOG.info(f"Exported {len(results)} records to {path}")
            messagebox.showinfo("Success", "Export complete.")
        except Exception as e: LOG.exception("Export failed"); messagebox.showerror("Error", f"Failed to export: {e}")
    def _export_orders_atomic(self, orders: List[dict], path: str):
        tmp = path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(self.CSV_HEADERS)
            for order in orders:
                items = order.get("items") or []; item0 = items[0] if items else {}; ship = order.get("shipping_address") or {}
                w.writerow([order.get("order_reference", ""), order.get("order_date", ""), order.get("status", ""), item0.get("name", ""), item0.get("quantity", ""), order.get("total", ""), ship.get("full_name", ""), ship.get("line_1", ""), ship.get("city", ""), ship.get("state", ""), ship.get("postal_code", ""), ship.get("country", "")])
        os.replace(tmp, path)
    def on_cancel(self): self.cancel_event.set()

class LogsTab(ttk.Frame):
    LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    def __init__(self, parent):
        super().__init__(parent, padding=4); self._build_widgets(); self._configure_log_capture()
    def _build_widgets(self):
        controls = ttk.Frame(self); controls.pack(fill=tk.X, pady=4)
        ttk.Label(controls, text="Log Level").pack(side="left", padx=4)
        self.cmb_loglevel = ttk.Combobox(controls, values=self.LOG_LEVELS, state="readonly", width=10); self.cmb_loglevel.set("INFO"); self.cmb_loglevel.pack(side="left", padx=4)
        ttk.Button(controls, text="Apply", command=self.on_apply_log_level).pack(side="left", padx=4)
        self.txt_logs = tk.Text(self, wrap="word", font=("Consolas", 9)); self.txt_logs.pack(fill="both", expand=True)
    def _configure_log_capture(self):
        text_handler = TextHandler(self.txt_logs)
        text_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        LOG.addHandler(text_handler); LOG.setLevel(logging.INFO)
    def on_apply_log_level(self):
        level = getattr(logging, self.cmb_loglevel.get().upper(), logging.INFO)
        LOG.setLevel(level); LOG.info(f"Log level set to {self.cmb_loglevel.get()}")
class TextHandler(logging.Handler):
    def __init__(self, text_widget): super().__init__(); self.text_widget = text_widget
    def emit(self, record): self.text_widget.after(0, self._append_text, self.format(record) + "\n")
    def _append_text(self, msg): self.text_widget.insert(tk.END, msg); self.text_widget.see(tk.END)

# --- Main Application ---
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("API Router and Client")
        self.geometry("600x300")
        self.settings_manager = SettingsManager(SETTINGS_FILE)
        self.cancel_event = threading.Event()
        self._create_widgets()
    def _create_widgets(self):
        notebook = ttk.Notebook(self); notebook.pack(fill="both", expand=True, padx=5, pady=5)
        self.profile_tab = ProfileTab(notebook, self.settings_manager, self.on_profile_changed)
        self.req_settings_tab = RequestSettingsTab(notebook, self.settings_manager)
        self.postman_tab = PostmanTab(notebook)
        self.bulk_tab = BulkTab(notebook, self.settings_manager, self.cancel_event)
        self.logs_tab = LogsTab(notebook)
        notebook.add(self.profile_tab, text="Profile")
        notebook.add(self.req_settings_tab, text="Request Settings")
        notebook.add(self.postman_tab, text="Postman")
        notebook.add(self.bulk_tab, text="Bulk Fetch")
        notebook.add(self.logs_tab, text="Logs")
    def on_profile_changed(self):
        LOG.info("Profile changed, refreshing settings tab.")
        self.req_settings_tab.load_profile_into_ui()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
