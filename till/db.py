"""SQLite storage. Every read and write is scoped to one business_id."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT,
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS businesses(
  id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, type TEXT, location TEXT, currency TEXT DEFAULT 'USD',
  description TEXT, target_customers TEXT, stage TEXT, staff INTEGER DEFAULT 0,
  opening_cash REAL DEFAULT 0, opening_cash_date TEXT, challenge TEXT, ambition TEXT);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name TEXT NOT NULL, kind TEXT DEFAULT 'Product', category TEXT, price REAL, unit_cost REAL,
  stock REAL, reorder_level REAL);
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name TEXT NOT NULL, segment TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  date TEXT NOT NULL, item TEXT NOT NULL, customer TEXT, qty REAL DEFAULT 1,
  unit_price REAL NOT NULL, unit_cost REAL, channel TEXT);
CREATE TABLE IF NOT EXISTS expenses(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  date TEXT NOT NULL, category TEXT NOT NULL, description TEXT, amount REAL NOT NULL,
  fixed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS competitors(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name TEXT NOT NULL, pricing TEXT, strengths TEXT, weaknesses TEXT);
CREATE TABLE IF NOT EXISTS goals(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  title TEXT NOT NULL, metric TEXT DEFAULT 'Custom', target REAL, progress REAL DEFAULT 0,
  start_date TEXT, due_date TEXT);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  title TEXT NOT NULL, priority TEXT DEFAULT 'Medium', due_date TEXT, done INTEGER DEFAULT 0,
  source TEXT DEFAULT 'You');
CREATE TABLE IF NOT EXISTS insights(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, fingerprint TEXT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_usage(
  business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  day TEXT NOT NULL, used INTEGER DEFAULT 0, PRIMARY KEY(business_id, day));
CREATE TABLE IF NOT EXISTS chat_messages(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
"""

EDITABLE = {
    "products": ["name", "kind", "category", "price", "unit_cost", "stock", "reorder_level"],
    "customers": ["name", "segment", "notes"],
    "sales": ["date", "item", "customer", "qty", "unit_price", "unit_cost", "channel"],
    "expenses": ["date", "category", "description", "amount", "fixed"],
    "competitors": ["name", "pricing", "strengths", "weaknesses"],
    "goals": ["title", "metric", "target", "progress", "start_date", "due_date"],
    "tasks": ["title", "priority", "due_date", "done", "source"],
}
REQUIRED = {
    "products": ["name"], "customers": ["name"], "sales": ["date", "item", "unit_price"],
    "expenses": ["date", "category", "amount"], "competitors": ["name"],
    "goals": ["title"], "tasks": ["title"],
}
ORDER = {"sales": "date DESC, id DESC", "expenses": "date DESC, id DESC", "tasks": "done, due_date IS NULL, due_date"}


def _path() -> Path:
    return Path(os.environ.get("TILL_DB", Path(__file__).resolve().parent.parent / "data" / "till.db"))


@contextmanager
def conn():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        with c:
            yield c
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Accounts ---------------------------------------------------------------
def _hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()


def create_user(email: str, name: str, password: str) -> int | None:
    salt = secrets.token_hex(16)
    try:
        with conn() as c:
            cur = c.execute(
                "INSERT INTO users(email,name,pw_hash,salt) VALUES(?,?,?,?)",
                (email.strip().lower(), name.strip(), _hash(password, salt), salt),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def verify_user(email: str, password: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if row and hmac.compare_digest(row["pw_hash"], _hash(password, row["salt"])):
        return dict(row)
    return None


def delete_user(user_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM users WHERE id=?", (user_id,))


# Business ---------------------------------------------------------------
def get_business(user_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM businesses WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


BUSINESS_FIELDS = ["name", "type", "location", "currency", "description", "target_customers",
                   "stage", "staff", "opening_cash", "opening_cash_date", "challenge", "ambition"]


def save_business(user_id: int, values: dict) -> int:
    fields = [f for f in BUSINESS_FIELDS if f in values]
    existing = get_business(user_id)
    with conn() as c:
        if existing:
            sets = ",".join(f"{f}=?" for f in fields)
            c.execute(f"UPDATE businesses SET {sets} WHERE id=?", [values[f] for f in fields] + [existing["id"]])
            return existing["id"]
        names = ",".join(["user_id"] + fields)
        marks = ",".join("?" * (len(fields) + 1))
        return c.execute(f"INSERT INTO businesses({names}) VALUES({marks})",
                         [user_id] + [values[f] for f in fields]).lastrowid


def save_business_cash(business_id: int, amount: float, as_of: str) -> None:
    with conn() as c:
        c.execute("UPDATE businesses SET opening_cash=?, opening_cash_date=? WHERE id=?", (amount, as_of, business_id))


def clear_business_data(business_id: int) -> None:
    with conn() as c:
        for table in list(EDITABLE) + ["insights", "chat_messages"]:
            c.execute(f"DELETE FROM {table} WHERE business_id=?", (business_id,))


# Tables -----------------------------------------------------------------
def fetch(table: str, business_id: int) -> pd.DataFrame:
    if table not in EDITABLE:
        raise ValueError(table)
    query = f"SELECT id,{','.join(EDITABLE[table])} FROM {table} WHERE business_id=?"
    if table in ORDER:
        query += f" ORDER BY {ORDER[table]}"
    with conn() as c:
        rows = c.execute(query, (business_id,)).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=["id"] + EDITABLE[table])


def _clean(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        return value.strip() or None
    return value.item() if hasattr(value, "item") else value


def sync(table: str, business_id: int, edited: pd.DataFrame, shown_ids: list[int]) -> dict:
    """Apply an edited grid. Only ids that were shown can be deleted, so paging is safe."""
    columns = EDITABLE[table]
    required = REQUIRED[table]
    kept, added, updated, skipped = set(), 0, 0, 0
    with conn() as c:
        for row in edited.to_dict("records"):
            values = {k: _clean(row.get(k)) for k in columns}
            rid = _clean(row.get("id"))
            if any(values[k] is None for k in required):
                if rid is None and all(v is None for v in values.values()):
                    continue
                skipped += 1
                if rid is not None:
                    kept.add(int(rid))
                continue
            if rid is None:
                names = ",".join(["business_id"] + columns)
                marks = ",".join("?" * (len(columns) + 1))
                c.execute(f"INSERT INTO {table}({names}) VALUES({marks})",
                          [business_id] + [values[k] for k in columns])
                added += 1
            else:
                kept.add(int(rid))
                sets = ",".join(f"{k}=?" for k in columns)
                c.execute(f"UPDATE {table} SET {sets} WHERE id=? AND business_id=?",
                          [values[k] for k in columns] + [int(rid), business_id])
                updated += 1
        removed = 0
        for rid in set(shown_ids) - kept:
            c.execute(f"DELETE FROM {table} WHERE id=? AND business_id=?", (int(rid), business_id))
            removed += 1
    return {"added": added, "updated": updated, "removed": removed, "skipped": skipped}


def insert_many(table: str, business_id: int, rows: list[dict]) -> int:
    columns = EDITABLE[table]
    names = ",".join(["business_id"] + columns)
    marks = ",".join("?" * (len(columns) + 1))
    with conn() as c:
        c.executemany(f"INSERT INTO {table}({names}) VALUES({marks})",
                      [[business_id] + [_clean(r.get(k)) for k in columns] for r in rows])
    return len(rows)


def add_task(business_id: int, title: str, priority: str = "Medium", due: str | None = None, source: str = "You") -> None:
    insert_many("tasks", business_id, [{"title": title, "priority": priority, "due_date": due, "done": 0, "source": source}])


def set_task_done(business_id: int, task_id: int, done: bool) -> None:
    with conn() as c:
        c.execute("UPDATE tasks SET done=? WHERE id=? AND business_id=?", (int(done), task_id, business_id))


# AI records -------------------------------------------------------------
def save_insight(business_id: int, fingerprint: str, payload: dict) -> None:
    with conn() as c:
        c.execute("INSERT INTO insights(business_id,created_at,fingerprint,payload) VALUES(?,?,?,?)",
                  (business_id, now(), fingerprint, json.dumps(payload)))


def latest_insight(business_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM insights WHERE business_id=? ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    if not row:
        return None
    return {"created_at": row["created_at"], "fingerprint": row["fingerprint"], "payload": json.loads(row["payload"])}


def take_ai_credit(business_id: int, daily_limit: int) -> bool:
    """Counts one AI use for today. Returns False once the daily limit is reached."""
    day = date.today().isoformat()
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO ai_usage(business_id,day,used) VALUES(?,?,0)", (business_id, day))
        cur = c.execute("UPDATE ai_usage SET used=used+1 WHERE business_id=? AND day=? AND used<?", (business_id, day, daily_limit))
        return cur.rowcount == 1


def add_message(business_id: int, role: str, content: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO chat_messages(business_id,role,content,created_at) VALUES(?,?,?,?)",
                  (business_id, role, content, now()))


def messages(business_id: int, limit: int = 100) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT role,content FROM chat_messages WHERE business_id=? ORDER BY id DESC LIMIT ?",
                         (business_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_messages(business_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM chat_messages WHERE business_id=?", (business_id,))
