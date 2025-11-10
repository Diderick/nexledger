# shared/db.py
import sqlite3
import os
from pathlib import Path

# Global
COMPANIES_DIR = Path(__file__).parent.parent / "companies"
CURRENT_COMPANY = None

def set_current_company(name):
    global CURRENT_COMPANY
    CURRENT_COMPANY = name
    # Save to settings
    settings_path = Path(__file__).parent.parent / "settings.json"
    import json
    with open(settings_path, "w") as f:
        json.dump({"last_company": name}, f)

def get_current_company():
    return CURRENT_COMPANY

def get_db_path():
    if not CURRENT_COMPANY:
        return None
    return COMPANIES_DIR / CURRENT_COMPANY / "nexledger.db"

def get_conn():
    path = get_db_path()
    if not path:
        raise ValueError("No company selected")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db_for_company(company_name):
    company_dir = COMPANIES_DIR / company_name
    company_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(company_dir / "nexledger.db")
    cur = conn.cursor()

    cur.executescript('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('Income','Expense')),
            linked_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS customers (...);
        CREATE TABLE IF NOT EXISTS vendors (...);
        CREATE TABLE IF NOT EXISTS invoices (...);
        CREATE TABLE IF NOT EXISTS invoice_items (...);
        CREATE TABLE IF NOT EXISTS bank_accounts (...);
        CREATE TABLE IF NOT EXISTS categories (...);
    ''')

    try:
        cur.execute("PRAGMA table_info(transactions)")
        cols = [r[1] for r in cur.fetchall()]
        if 'linked_id' not in cols:
            cur.execute("ALTER TABLE transactions ADD COLUMN linked_id INTEGER")
    except: pass

    conn.commit()
    conn.close()

def list_companies():
    if not COMPANIES_DIR.exists():
        return []
    return [d.name for d in COMPANIES_DIR.iterdir() if d.is_dir()]

def is_duplicate_transaction(date, description):
    conn = get_conn()
    row = conn.execute("SELECT id FROM transactions WHERE date=? AND description=?", (date, description)).fetchone()
    conn.close()
    return row is not None