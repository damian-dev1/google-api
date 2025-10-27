import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import os
import threading
import queue
import time
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Date, DateTime, event
)
from sqlalchemy.orm import sessionmaker, declarative_base
try:
    from theme_subdir import ThemeManager
except Exception:
    class ThemeManager:
        def __init__(self, root): pass
CONFIG_FILE = "app_config.json"
DB_FILE = "sku_results.db"
DEFAULT_CONFIG = {
    "endpoint": "https://api.virtualstock.com/restapi/v4/orders/",
    "method": "GET",
    "headers": "Content-Type:application/json",
    "limit": "1",
    "offset": "0",
    "sort_enabled": True,
    "sort": "desc",
    "status_enabled": False,
    "status": "ORDER_ACK",
    "username": "",
    "password": "",
    "timeout": "10",
    "rate_limit_enabled": True,
    "requests_per_minute": "150",
    "max_workers": "8",
    "csv_chunksize": "200000"
}
TREEVIEW_BATCH_UPDATE_SIZE = 200          # insert rows in UI per batch
TREEVIEW_MAX_ROWS_DISPLAY = 5000          # soft cap to keep UI snappy
TASK_QUEUE_MAX = 5000                      # SKU task buffer (bounded)
RESULT_QUEUE_MAX = 5000                    # result buffer (bounded)
DB_COMMIT_BATCH_SIZE = 500                 # commit in batches
STATUS_UPDATE_MS = 200                     # UI timer
Base = declarative_base()
class SkuResult(Base):
    __tablename__ = 'sku_results'
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, index=True)
    last_order_date = Column(Date, nullable=True)
    days_since = Column(Integer, nullable=True)
    order_reference = Column(String)
    result_count = Column(Integer)
    response_code = Column(String)
    processed_at = Column(DateTime, default=datetime.utcnow)
engine = create_engine(
    f"sqlite:///{DB_FILE}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    future=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cur = dbapi_connection.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA foreign_keys=ON;")
    finally:
        cur.close()
class RateLimiter:
    """Token bucket limiter for global RPM across N workers."""
    def __init__(self, per_minute: int):
        self.capacity = max(per_minute, 1)
        self.tokens = float(self.capacity)
        self.fill_rate = self.capacity / 60.0
        self.timestamp = time.monotonic()
        self.lock = threading.Lock()
    def acquire(self):
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.timestamp
                self.timestamp = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            time.sleep(0.02)
class SkuCheckerApp:
    """
    High-throughput Tkinter app for 100k+ SKUs:
    - Streams CSV in chunks (zero-stock filter, de-dupe)
    - Producer -> worker pool (HTTP) -> main-thread writer/UI
    - Global token bucket rate-limit (RPM)
    - SQLite WAL, batched commits
    """
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SKU Stock Checker (SQLAlchemy Edition)")
        self.root.geometry("1100x800")
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_exit)
        self.db = SessionLocal()
        self.theme = ThemeManager(root)
        self.csv_path: str | None = None
        self.task_queue: queue.Queue[str | None] = queue.Queue(maxsize=TASK_QUEUE_MAX)
        self.result_queue: queue.Queue[dict | None] = queue.Queue(maxsize=RESULT_QUEUE_MAX)
        self.is_processing = False
        self.pause_event = threading.Event(); self.pause_event.set()
        self.stop_event = threading.Event()
        self.total_to_process = 0
        self.total_enqueued = 0
        self.total_processed = 0
        self.total_ok = 0
        self.total_err = 0
        self.started_at: float | None = None
        self.tree_update_batch: list[SkuResult] = []
        self._pending_db_count = 0
        self.http = requests.Session()
        retry = Retry(
            total=3, backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64, max_retries=retry)
        self.http.mount("https://", adapter)
        self.http.mount("http://", adapter)
        self.http.headers.update({"Accept-Encoding": "gzip, deflate"})
        self._create_widgets()
        self._load_app_config()
        self._load_results_from_db()
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=(0, 10))
        self._create_import_tab(notebook)
        self._create_test_tab(notebook)
        self._create_config_tab(notebook)
        self.status_var = tk.StringVar(value="Ready. Load a CSV or view previous results.")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, anchor="w", relief="sunken", padding=5)
        status_bar.pack(fill="x", side="bottom")
    def _create_import_tab(self, notebook: ttk.Notebook):
        frame = ttk.Frame(notebook, padding="10")
        notebook.add(frame, text="📦 Process & View Results")
        proc = ttk.LabelFrame(frame, text="Processing", padding=10)
        proc.pack(fill="x", pady=5)
        self.import_btn = ttk.Button(proc, text="Load CSV File", command=self._load_csv)
        self.import_btn.pack(side="left", padx=(0, 10))
        self.process_stop_btn = ttk.Button(proc, text="Process SKUs", command=self._start_processing, state="disabled")
        self.process_stop_btn.pack(side="left", padx=(0, 10))
        self.pause_resume_btn = ttk.Button(proc, text="Pause", command=self._pause_processing, state="disabled")
        self.counters_var = tk.StringVar(value="Queued: 0 | Processed: 0 | OK: 0 | Err: 0 | ETA: —")
        ttk.Label(proc, textvariable=self.counters_var).pack(side="right")
        db_controls = ttk.LabelFrame(frame, text="Database", padding=10)
        db_controls.pack(fill="x", pady=5)
        self.load_db_btn = ttk.Button(db_controls, text="🔄 Reload from Database", command=self._load_results_from_db)
        self.load_db_btn.pack(side="left", padx=(0, 10))
        self.export_csv_btn = ttk.Button(db_controls, text="Export to CSV", command=self._export_to_csv)
        self.export_csv_btn.pack(side="left", padx=(0, 10))
        self.clear_db_btn = ttk.Button(db_controls, text="⚠️ Clear All Database Results", command=self._clear_database)
        self.clear_db_btn.pack(side="right", padx=(10, 0))
        self.progress_bar = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_bar.configure(maximum=1, value=0)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, pady=10)
        columns = ("SKU", "Last Order", "Days Since", "Order Ref", "Count", "Response Code", "Processed At")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("SKU", width=150, anchor="w")
        self.tree.column("Last Order", anchor="center")
        self.tree.column("Days Since", anchor="center")
        self.tree.column("Processed At", width=160, anchor="center")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
    def _create_test_tab(self, notebook: ttk.Notebook):
        test_frame = ttk.Frame(notebook, padding="20")
        notebook.add(test_frame, text="🧪 Test SKU")
        ttk.Label(test_frame, text="Test API Response for a Single SKU", font=("-weight bold")).pack(pady=5, anchor="w")
        lf = ttk.LabelFrame(test_frame, text="SKU Input", padding=15)
        lf.pack(fill="x", expand=True, pady=10)
        ttk.Label(lf, text="Select from loaded CSV:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.part_number_var = tk.StringVar()
        self.part_number_dropdown = ttk.Combobox(lf, textvariable=self.part_number_var, state="readonly")
        self.part_number_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(lf, text="Or enter a custom SKU:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.custom_sku_entry = ttk.Entry(lf, width=30)
        self.custom_sku_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        lf.columnconfigure(1, weight=1)
        self.test_btn = ttk.Button(test_frame, text="Test API Call", command=self._test_api_call)
        self.test_btn.pack(pady=20)
    def _create_config_tab(self, notebook: ttk.Notebook):
        self.config_vars = {}
        config_frame = ttk.Frame(notebook, padding="10")
        notebook.add(config_frame, text="⚙️ API Configuration")
        auth_frame = ttk.LabelFrame(config_frame, text="Endpoint & Authentication", padding=10)
        auth_frame.pack(fill="x", pady=5)
        fields = [("API Endpoint:", "endpoint", None), ("Username:", "username", None), ("Password:", "password", "*")]
        for i, (label, key, show_char) in enumerate(fields):
            ttk.Label(auth_frame, text=label).grid(row=i, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar()
            entry = ttk.Entry(auth_frame, textvariable=var, width=60, show=show_char)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            self.config_vars[key] = var
        auth_frame.columnconfigure(1, weight=1)
        params_frame = ttk.LabelFrame(config_frame, text="Request Parameters", padding=10)
        params_frame.pack(fill="x", pady=5)
        ttk.Label(params_frame, text="HTTP Method:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        method_var = tk.StringVar()
        ttk.Combobox(params_frame, textvariable=method_var, values=["GET", "POST"], state="readonly").grid(row=0, column=1, sticky="w", padx=5, pady=2)
        self.config_vars["method"] = method_var
        ttk.Label(params_frame, text="Headers (key:value, one per line):").grid(row=1, column=0, sticky="nw", padx=5, pady=2)
        self.headers_text = tk.Text(params_frame, height=3, width=50)
        self.headers_text.grid(row=1, column=1, columnspan=5, sticky="ew", padx=5, pady=2)
        p_fields = [("Limit:", "limit"), ("Offset:", "offset"), ("Timeout (s):", "timeout")]
        for i, (label, key) in enumerate(p_fields):
            ttk.Label(params_frame, text=label).grid(row=i+2, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar()
            ttk.Entry(params_frame, textvariable=var, width=10).grid(row=i+2, column=1, sticky="w", padx=5, pady=2)
            self.config_vars[key] = var
        sort_var = tk.BooleanVar()
        ttk.Checkbutton(params_frame, text="Enable 'sort'", variable=sort_var).grid(row=2, column=2, sticky="w", padx=10)
        self.config_vars["sort_enabled"] = sort_var
        sort_dir_var = tk.StringVar()
        ttk.Combobox(params_frame, textvariable=sort_dir_var, values=["asc", "desc"], state="readonly", width=8).grid(row=2, column=3, sticky="w")
        self.config_vars["sort"] = sort_dir_var
        status_var = tk.BooleanVar()
        ttk.Checkbutton(params_frame, text="Enable 'status'", variable=status_var).grid(row=3, column=2, sticky="w", padx=10)
        self.config_vars["status_enabled"] = status_var
        status_val_var = tk.StringVar()
        ttk.Combobox(params_frame, textvariable=status_val_var, values=["ORDER", "ORDER_ACK", "DISPATCH"], state="readonly").grid(row=3, column=3, sticky="w")
        self.config_vars["status"] = status_val_var
        perf_frame = ttk.LabelFrame(config_frame, text="Performance & Rate Limiting", padding=10)
        perf_frame.pack(fill="x", pady=5)
        rate_limit_var = tk.BooleanVar()
        ttk.Checkbutton(perf_frame, text="Enable Rate Limiting", variable=rate_limit_var).grid(row=0, column=0, sticky="w", padx=5)
        self.config_vars["rate_limit_enabled"] = rate_limit_var
        ttk.Label(perf_frame, text="Requests per Minute:").grid(row=0, column=1, sticky="w", padx=10)
        req_min_var = tk.StringVar()
        ttk.Entry(perf_frame, textvariable=req_min_var, width=10).grid(row=0, column=2, sticky="w")
        self.config_vars["requests_per_minute"] = req_min_var
        ttk.Label(perf_frame, text="Worker Threads:").grid(row=0, column=3, sticky="w", padx=10)
        workers_var = tk.StringVar()
        ttk.Entry(perf_frame, textvariable=workers_var, width=6).grid(row=0, column=4, sticky="w")
        self.config_vars["max_workers"] = workers_var
        ttk.Label(perf_frame, text="CSV Chunk Size:").grid(row=0, column=5, sticky="w", padx=10)
        chunks_var = tk.StringVar()
        ttk.Entry(perf_frame, textvariable=chunks_var, width=8).grid(row=0, column=6, sticky="w")
        self.config_vars["csv_chunksize"] = chunks_var
        action_frame = ttk.Frame(config_frame, padding=10)
        action_frame.pack(fill="x", pady=10)
        ttk.Button(action_frame, text="Save Configuration", command=self._save_app_config).pack(side="left", padx=5)
        ttk.Button(action_frame, text="Reset to Defaults", command=self._reset_config_to_defaults).pack(side="left", padx=5)
    def _load_results_from_db(self):
        self.status_var.set("Loading results from database...")
        self.root.update_idletasks()
        try:
            results = self.db.query(SkuResult).order_by(SkuResult.processed_at.desc()).limit(TREEVIEW_MAX_ROWS_DISPLAY).all()
            self.tree.delete(*self.tree.get_children())
            for res in results:
                self._insert_result_into_treeview(res)
            self.status_var.set(f"Loaded {len(results)} recent results from the database.")
        except Exception as e:
            messagebox.showerror("Database Error", f"Could not load from database: {e}")
            self.status_var.set("Error loading from database.")
    def _clear_database(self):
        if messagebox.askyesno("Confirm Deletion", "⚠️ Permanently delete ALL results from the database?"):
            try:
                num_deleted = self.db.query(SkuResult).delete()
                self.db.commit()
                self.tree.delete(*self.tree.get_children())
                self.status_var.set(f"Deleted {num_deleted} records.")
            except Exception as e:
                self.db.rollback()
                messagebox.showerror("Database Error", f"Could not clear database: {e}")
    def _insert_result_into_treeview(self, result: SkuResult):
        order_date_str = result.last_order_date.strftime("%Y-%m-%d") if result.last_order_date else "N/A"
        processed_at_str = result.processed_at.strftime("%Y-%m-%d %H:%M:%S") if result.processed_at else "N/A"
        values = (
            result.sku,
            order_date_str,
            result.days_since if result.days_since is not None else "N/A",
            result.order_reference,
            result.result_count,
            result.response_code,
            processed_at_str
        )
        if len(self.tree.get_children()) >= TREEVIEW_MAX_ROWS_DISPLAY:
            first = self.tree.get_children()[0]
            self.tree.delete(first)
        self.tree.insert("", "end", values=values)
    def _load_csv(self):
        path = filedialog.askopenfilename(title="Select a CSV file", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        self.csv_path = path
        try:
            samp = pd.read_csv(self.csv_path, usecols=['sku', 'stock_qty'], nrows=20000, dtype={'sku': str, 'stock_qty': 'Int64'})
            z = samp[samp['stock_qty'].fillna(0) == 0]['sku'].dropna().astype(str).unique().tolist()[:500]
            self.part_number_dropdown["values"] = z
            if z: self.part_number_dropdown.set(z[0])
        except Exception:
            self.part_number_dropdown["values"] = []
        self.status_var.set("CSV loaded (streaming mode). Click 'Process SKUs' to start.")
        self.process_stop_btn.config(state="normal")
    def _start_processing(self):
        if not self.csv_path:
            messagebox.showwarning("No CSV", "Please load a CSV first.")
            return
        self.is_processing = True
        self.stop_event.clear()
        self.pause_event.set()
        self.total_to_process = 0
        self.total_enqueued = 0
        self.total_processed = 0
        self.total_ok = 0
        self.total_err = 0
        self.started_at = time.time()
        self.progress_bar.configure(maximum=1, value=0)
        self.tree_update_batch.clear()
        self._pending_db_count = 0
        self._update_ui_for_processing_start()
        cfg = self._get_current_config()
        rpm = int(cfg.get("requests_per_minute", 150) or 150)
        self.rate_limiter = RateLimiter(rpm) if cfg.get("rate_limit_enabled", False) else None
        self.max_workers = max(1, int(cfg.get("max_workers", 8) or 8))
        self.csv_chunksize = max(10000, int(cfg.get("csv_chunksize", 200000) or 200000))
        self.producer_thread = threading.Thread(target=self._producer_from_csv, daemon=True)
        self.producer_thread.start()
        self.worker_threads: list[threading.Thread] = []
        for _ in range(self.max_workers):
            t = threading.Thread(target=self._worker_consume, daemon=True)
            t.start()
            self.worker_threads.append(t)
        self.root.after(STATUS_UPDATE_MS, self._check_queue)
    def _producer_from_csv(self):
        """Stream the CSV, filter zero-stock, de-dupe, enqueue SKUs."""
        seen: set[str] = set()
        try:
            for chunk in pd.read_csv(
                self.csv_path,
                usecols=['sku', 'stock_qty'],
                dtype={'sku': str, 'stock_qty': 'Int64'},
                chunksize=self.csv_chunksize
            ):
                if self.stop_event.is_set():
                    break
                zero = chunk[chunk['stock_qty'].fillna(0) == 0]['sku'].dropna().astype(str)
                for sku in zero:
                    if self.stop_event.is_set():
                        break
                    if sku not in seen:
                        seen.add(sku)
                        self.task_queue.put(sku)
                        self.total_enqueued += 1
                        if self.total_enqueued % 250 == 0:
                            enq = self.total_enqueued
                            self.root.after(0, lambda v=enq: self.progress_bar.configure(maximum=max(v, 1)))
                if len(seen) % 5000 == 0:
                    self.status_var.set(f"Scanning… unique zero-stock SKUs found: {len(seen)}")
        except Exception as e:
            self.status_var.set(f"CSV streaming error: {e}")
        for _ in range(self.max_workers):
            self.task_queue.put(None)
        self.total_to_process = self.total_enqueued
        self.root.after(0, lambda v=self.total_to_process: self.progress_bar.configure(maximum=max(v, 1)))
    def _worker_consume(self):
        """Worker: pulls SKUs, rate-limited HTTP, pushes results."""
        while not self.stop_event.is_set():
            item = self.task_queue.get()
            if item is None:
                self.task_queue.task_done()
                break
            sku = item
            self.pause_event.wait()
            if self.rate_limiter:
                self.rate_limiter.acquire()
            res = self._fetch_order_details(sku)
            self.result_queue.put(res)
            self.task_queue.task_done()
    def _check_queue(self):
        """Main-thread pump: write to DB in batches + update UI."""
        try:
            drained = 0
            while drained < 200 and not self.result_queue.empty():
                item = self.result_queue.get_nowait()
                if item is None:
                    continue
                db_result = SkuResult(
                    sku=item['sku'],
                    last_order_date=item['order_date_obj'],
                    days_since=item['days_since'],
                    order_reference=item['order_ref'],
                    result_count=item['count'],
                    response_code=item['status_code']
                )
                self.db.add(db_result)
                self._pending_db_count += 1
                self.total_processed += 1
                if str(item['status_code']) == "200":
                    self.total_ok += 1
                else:
                    self.total_err += 1
                self.tree_update_batch.append(db_result)
                if len(self.tree_update_batch) >= TREEVIEW_BATCH_UPDATE_SIZE:
                    for r in self.tree_update_batch:
                        self._insert_result_into_treeview(r)
                    self.tree_update_batch.clear()
                if self._pending_db_count >= DB_COMMIT_BATCH_SIZE:
                    try:
                        self.db.commit()
                        self._pending_db_count = 0
                    except Exception as e:
                        self.db.rollback()
                        self.status_var.set(f"DB commit error: {e}")
                drained += 1
            if self.tree_update_batch:
                for r in self.tree_update_batch:
                    self._insert_result_into_treeview(r)
                self.tree_update_batch.clear()
            if self.total_to_process > 0:
                self.progress_bar["value"] = self.total_processed
            self._update_counters_label()
            if self.is_processing:
                self.root.after(STATUS_UPDATE_MS, self._check_queue)
            else:
                return
            if (self.total_processed >= self.total_to_process > 0
                and self.task_queue.unfinished_tasks == 0
                and self.result_queue.empty()):
                self._finalize_processing()
        except queue.Empty:
            if self.is_processing:
                self.root.after(STATUS_UPDATE_MS, self._check_queue)
    def _update_counters_label(self):
        eta_txt = "—"
        if self.started_at and self.total_processed:
            elapsed = max(time.time() - self.started_at, 0.001)
            rps = self.total_processed / elapsed
            remaining = max(self.total_to_process - self.total_processed, 0)
            eta_sec = remaining / rps if rps > 0 else 0
            if eta_sec >= 3600:
                eta_txt = f"{int(eta_sec//3600)}h {int((eta_sec%3600)//60)}m"
            elif eta_sec >= 60:
                eta_txt = f"{int(eta_sec//60)}m {int(eta_sec%60)}s"
            else:
                eta_txt = f"{int(eta_sec)}s"
        self.counters_var.set(
            f"Queued: {self.total_to_process or self.total_enqueued} | "
            f"Processed: {self.total_processed} | OK: {self.total_ok} | Err: {self.total_err} | ETA: {eta_txt}"
        )
    def _flush_treeview_batch(self):
        if not self.tree_update_batch:
            return
        for res in self.tree_update_batch:
            self._insert_result_into_treeview(res)
        self.tree_update_batch.clear()
        self.root.update_idletasks()
    def _finalize_processing(self):
        self._flush_treeview_batch()
        try:
            if self._pending_db_count:
                self.db.commit()
                self._pending_db_count = 0
            final_status = "Cancelled" if self.stop_event.is_set() else "Complete"
            self.status_var.set(f"Processing {final_status}. Results saved to database.")
        except Exception as e:
            self.db.rollback()
            messagebox.showerror("Database Error", f"Could not commit results to database: {e}")
            self.status_var.set("Error: Failed to save results to database.")
        self.is_processing = False
        self._update_ui_for_processing_end()
    def _fetch_order_details(self, sku: str) -> dict:
        """HTTP with retries (429/5xx), keep-alive session, and robust parsing."""
        base_result = {'sku': sku, 'order_date_obj': None, 'days_since': None,
                       'order_ref': "N/A", 'count': 0, 'status_code': "N/A"}
        try:
            config = self._get_current_config()
            headers = {}
            raw = self.headers_text.get("1.0", tk.END).strip()
            if raw:
                for line in raw.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip()] = v.strip()
            auth = (config.get("username"), config.get("password")) if config.get("username") else None
            params = {
                'limit': config.get("limit", "1"),
                'offset': config.get("offset", "0"),
                'part_number': sku
            }
            if config.get("sort_enabled"): params['sort'] = config.get("sort", "desc")
            if config.get("status_enabled"): params['status'] = config.get("status")
            timeout = float(config.get("timeout", 10) or 10)
            for attempt in range(5):
                if self.stop_event.is_set():
                    break
                resp = self.http.request(config["method"], config["endpoint"],
                                         headers=headers, params=params, auth=auth, timeout=timeout)
                base_result['status_code'] = str(resp.status_code)
                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After")
                    try:
                        sleep_s = float(ra) if ra is not None else (1.5 * (attempt + 1))
                    except ValueError:
                        sleep_s = 1.5 * (attempt + 1)
                    time.sleep(sleep_s)
                    continue
                if 500 <= resp.status_code < 600:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    base_result['count'] = data.get("count", 0)
                    if results:
                        order = results[0]
                        base_result['order_ref'] = order.get("order_reference", "N/A")
                        order_date_raw = order.get("order_date", "")
                        try:
                            ts = order_date_raw.replace('Z', '+00:00')
                            dt_obj = datetime.fromisoformat(ts)
                            base_result['order_date_obj'] = dt_obj.date()
                            base_result['days_since'] = (datetime.now(dt_obj.tzinfo) - dt_obj).days
                        except Exception:
                            base_result['order_ref'] = f"Invalid Date: {order_date_raw}"
                    else:
                        base_result['order_ref'] = "No Orders Found"
                else:
                    base_result['order_ref'] = f"API Error: {resp.reason}"
                break
        except requests.exceptions.RequestException:
            base_result['order_ref'] = "Request Exception"
            base_result['status_code'] = "N/A"
        except Exception:
            base_result['order_ref'] = "General Exception"
            base_result['status_code'] = "N/A"
        return base_result
    def _export_to_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path: return
        self.status_var.set("Exporting to CSV...")
        self.root.update_idletasks()
        try:
            df = pd.read_sql(self.db.query(SkuResult).statement, self.db.bind)
            df.to_csv(path, index=False)
            messagebox.showinfo("Success", f"Exported {len(df)} records to:\n{path}")
            self.status_var.set("Export complete.")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export data: {e}")
            self.status_var.set("Export failed.")
    def _on_app_exit(self):
        if self.is_processing:
            if not messagebox.askyesno("Exit", "Processing is in progress. Are you sure you want to exit?"):
                return
        if messagebox.askyesno("Save Config", "Save current configuration before exiting?"):
            self._save_app_config()
        try:
            self.http.close()
        except Exception:
            pass
        self.db.close()
        self.root.destroy()
    def _pause_processing(self):
        self.pause_event.clear()
        self.status_var.set("Paused. Click 'Resume' to continue.")
        self.pause_resume_btn.config(text="Resume", command=self._resume_processing)
    def _resume_processing(self):
        self.pause_event.set()
        self.status_var.set("Resuming processing...")
        self.pause_resume_btn.config(text="Pause", command=self._pause_processing)
    def _stop_processing(self):
        self.stop_event.set()
        try:
            for _ in range(self.max_workers):
                self.task_queue.put_nowait(None)
        except Exception:
            pass
        self.status_var.set("Stopping… will finalize once queues drain.")
    def _update_ui_for_processing_start(self):
        self.import_btn.config(state="disabled")
        self.process_stop_btn.config(text="Stop", command=self._stop_processing)
        self.pause_resume_btn.config(text="Pause", command=self._pause_processing, state="normal")
        self.pause_resume_btn.pack(side="left", padx=(0, 10))
        self.status_var.set("Processing started… streaming CSV, filling queue, spawning workers.")
    def _update_ui_for_processing_end(self):
        self.import_btn.config(state="normal")
        self.process_stop_btn.config(text="Process SKUs", command=self._start_processing, state="normal")
        self.pause_resume_btn.pack_forget()
        self.pause_resume_btn.config(state="disabled")
    def _test_api_call(self):
        sku = self.custom_sku_entry.get().strip() or self.part_number_var.get()
        if not sku:
            messagebox.showwarning("Input Needed", "Please select or enter a SKU to test.")
            return
        self.status_var.set(f"Testing SKU: {sku}…")
        self.root.update_idletasks()
        threading.Thread(target=self._test_api_worker, args=(sku,), daemon=True).start()
    def _test_api_worker(self, sku: str):
        result = self._fetch_order_details(sku)
        order_date_str = result['order_date_obj'].strftime('%Y-%m-%d') if result['order_date_obj'] else "N/A"
        preview_text = (f"--- Test Result for SKU: {result['sku']} ---\n\n"
                        f"Last Order Date: {order_date_str}\n"
                        f"Days Since Last Order: {result['days_since']}\n"
                        f"Order Reference: {result['order_ref']}\n"
                        f"Result Count: {result['count']}\n"
                        f"Response Code: {result['status_code']}")
        self.root.after(0, lambda: messagebox.showinfo("API Test Result", preview_text))
        self.root.after(0, self.status_var.set, "Test complete.")
    def _get_current_config(self) -> dict:
        cfg = {key: var.get() for key, var in self.config_vars.items()}
        cfg["headers"] = self.headers_text.get("1.0", tk.END).strip()
        return cfg
    def _save_app_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self._get_current_config(), f, indent=4)
            self.status_var.set("Configuration saved successfully.")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save config: {e}")
    def _load_app_config(self):
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config.update(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                self.status_var.set(f"Config file error: {e}. Using defaults.")
        for key, value in config.items():
            if key == "headers":
                self.headers_text.delete("1.0", tk.END)
                if value: self.headers_text.insert("1.0", value)
            elif key in self.config_vars:
                self.config_vars[key].set(value)
        self.status_var.set("Configuration loaded.")
    def _reset_config_to_defaults(self):
        if messagebox.askyesno("Confirm Reset", "Reset all settings to defaults?"):
            if os.path.exists(CONFIG_FILE):
                try:
                    os.remove(CONFIG_FILE)
                except OSError as e:
                    messagebox.showwarning("Error", f"Could not remove config file: {e}")
            self._load_app_config()
            self.status_var.set("Configuration has been reset to defaults.")
if __name__ == "__main__":
    root = tk.Tk()
    app = SkuCheckerApp(root)
    root.mainloop()
