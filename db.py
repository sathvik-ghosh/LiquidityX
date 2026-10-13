import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS companies(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL CHECK(type IN ('manufacturer','supplier','customer','distributor','service')),
  opening_cash INTEGER NOT NULL, min_cash INTEGER NOT NULL CHECK(min_cash>=0),
  is_demo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS relationships(
  id INTEGER PRIMARY KEY,
  payer_id INTEGER NOT NULL REFERENCES companies(id),
  payee_id INTEGER NOT NULL REFERENCES companies(id),
  kind TEXT NOT NULL, criticality INTEGER NOT NULL DEFAULT 3 CHECK(criticality BETWEEN 1 AND 5),
  alternative_available INTEGER NOT NULL DEFAULT 0,
  UNIQUE(payer_id,payee_id), CHECK(payer_id<>payee_id));
CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY, relationship_id INTEGER NOT NULL REFERENCES relationships(id),
  amount INTEGER NOT NULL CHECK(amount>0), due_date TEXT NOT NULL,
  expected_delay_days INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open'
  CHECK(status IN ('open','paid')));
CREATE TABLE IF NOT EXISTS cash_transactions(
  id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
  txn_date TEXT NOT NULL, amount INTEGER NOT NULL, category TEXT NOT NULL,
  confirmed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS scenarios(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, params_json TEXT NOT NULL,
  result_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, action TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS inventory_batches(
  id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
  sku TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK(qty>=0), unit_cost INTEGER NOT NULL CHECK(unit_cost>=0),
  selling_price INTEGER NOT NULL CHECK(selling_price>=0), location TEXT NOT NULL,
  purchase_date TEXT NOT NULL, last_move_date TEXT NOT NULL,
  monthly_demand REAL NOT NULL DEFAULT 0, lead_time_days INTEGER NOT NULL DEFAULT 14,
  critical INTEGER NOT NULL DEFAULT 0, hold_status TEXT NOT NULL DEFAULT 'none',
  hold_reason TEXT, hold_deadline TEXT, expiry_date TEXT, restricted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recovery_plans(
  id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
  label TEXT NOT NULL, plan_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed'
  CHECK(status IN ('proposed','approved','rejected')), created_at TEXT NOT NULL, approved_by TEXT);
CREATE INDEX IF NOT EXISTS ix_batch_co ON inventory_batches(company_id);
CREATE INDEX IF NOT EXISTS ix_inv_rel ON invoices(relationship_id);
CREATE INDEX IF NOT EXISTS ix_txn_co ON cash_transactions(company_id, txn_date);
"""


def connect(path=":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)   # Streamlit runs scripts on varying threads
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def audit(conn, action: str, detail: dict | str = ""):
    if not isinstance(detail, str):
        detail = json.dumps(detail, sort_keys=True)
    with conn:
        conn.execute("INSERT INTO audit_log(ts,action,detail) VALUES(?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), action, detail))


def get_setting(conn, key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(conn, key, value):
    with conn:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) "
                     "DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
