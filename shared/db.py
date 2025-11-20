# db.py
import sqlite3
import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

ROOT_DIR = Path(__file__).parent.parent
COMPANIES_DIR = ROOT_DIR / "companies"
SETTINGS_FILE = ROOT_DIR / "settings.json"

_CURRENT_COMPANY = None  # active company name


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def sanitize_company_name(name: str) -> str:
    if not name:
        return ""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', ' ', name)
    return name[:100]


def close_all_dbs():
    pass  # kept for backwards compatibility


def set_current_company(name: str):
    """Save active company name."""
    global _CURRENT_COMPANY
    _CURRENT_COMPANY = name
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"last_company": name}, f, indent=2)
    except:
        pass


def get_current_company() -> str | None:
    """Returns active company or loads last one."""
    global _CURRENT_COMPANY

    if _CURRENT_COMPANY is not None:
        return _CURRENT_COMPANY

    # load last company
    if SETTINGS_FILE.exists():
        try:
            data = json.load(open(SETTINGS_FILE))
            last = data.get("last_company")
            if last and (COMPANIES_DIR / last).exists():
                _CURRENT_COMPANY = last
                return last
        except:
            pass

    # fallback → pick first company
    companies = list_companies()
    if companies:
        set_current_company(companies[0])
        return companies[0]

    _CURRENT_COMPANY = None
    return None


def get_db_path() -> Path | None:
    company = get_current_company()
    if not company:
        return None
    return COMPANIES_DIR / company / "nexledger.db"


def require_company():
    if not get_current_company():
        raise ValueError("No company selected")


# ─────────────────────────────────────────────────────────────
# DB CONNECTION HANDLING
# ─────────────────────────────────────────────────────────────

@contextmanager
def db_connection():
    require_company()
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    first_time = not db_path.exists()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if first_time or not _table_exists(conn, "company_info"):
        init_db_for_company(conn, get_current_company())

    try:
        yield conn
    finally:
        conn.close()


def get_conn():
    require_company()
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    first_time = not db_path.exists()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if first_time or not _table_exists(conn, "company_info"):
        init_db_for_company(conn, get_current_company())

    return conn


def get_conn_safe():
    try:
        return get_conn()
    except:
        return None


def _table_exists(conn, name):
    try:
        res = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,)
        ).fetchone()
        return res is not None
    except:
        return False


def seed_chart_of_accounts(conn):
    """Creates a standard South African SME Chart of Accounts."""

    starter_accounts = [
        # -------------------------
        # ASSETS (1000–1999)
        # -------------------------
        ("1000", "Bank Account", "Asset"),
        ("1100", "Petty Cash", "Asset"),
        ("1200", "Accounts Receivable", "Asset"),
        ("1300", "Inventory", "Asset"),
        ("1400", "VAT Input", "Asset"),
        ("1500", "Property, Plant & Equipment", "Asset"),
        ("1600", "Accumulated Depreciation", "Asset"),

        # -------------------------
        # LIABILITIES (2000–2999)
        # -------------------------
        ("2000", "Accounts Payable", "Liability"),
        ("2100", "VAT Output", "Liability"),
        ("2200", "Payroll Liabilities", "Liability"),
        ("2300", "PAYE Payable", "Liability"),
        ("2400", "UIF Payable", "Liability"),
        ("2500", "SDL Payable", "Liability"),
        ("2600", "Loan Liability", "Liability"),

        # -------------------------
        # EQUITY (3000–3999)
        # -------------------------
        ("3000", "Owner's Equity", "Equity"),
        ("3100", "Retained Earnings", "Equity"),

        # -------------------------
        # INCOME (4000–4999)
        # -------------------------
        ("4000", "Sales", "Income"),
        ("4100", "Service Income", "Income"),
        ("4200", "Interest Income", "Income"),
        ("4300", "Other Income", "Income"),

        # -------------------------
        # COST OF SALES (5000–5999)
        # -------------------------
        ("5000", "Cost of Goods Sold", "Expense"),
        ("5100", "Purchases", "Expense"),

        # -------------------------
        # OPERATING EXPENSES (6000–6999)
        # -------------------------
        ("6000", "Advertising & Marketing", "Expense"),
        ("6100", "Bank Charges", "Expense"),
        ("6200", "Depreciation Expense", "Expense"),
        ("6300", "Employee Salaries", "Expense"),
        ("6400", "UIF Expense", "Expense"),
        ("6500", "SDL Expense", "Expense"),
        ("6600", "PAYE Expense", "Expense"),
        ("6700", "Insurance", "Expense"),
        ("6800", "Office Expenses", "Expense"),
        ("6900", "Rent", "Expense"),
        ("6950", "Repairs & Maintenance", "Expense"),
        ("6970", "Telephone & Internet", "Expense"),
        ("6990", "Utilities", "Expense"),
    ]

    cur = conn.cursor()
    for code, name, acc_type in starter_accounts:
        cur.execute(
            "INSERT OR IGNORE INTO accounts (code, name, type) VALUES (?, ?, ?)",
            (code, name, acc_type)
        )
    conn.commit()


# ─────────────────────────────────────────────────────────────
# DATABASE INITIALIZATION (VERY IMPORTANT)
# ─────────────────────────────────────────────────────────────

def init_db_for_company(conn, company_name: str):
    """
    FULL ACCOUNTING SCHEMA
    Covers all functional areas:
    - Company info
    - Users
    - Customers/vendors
    - Invoices, quotes, bills, purchase orders
    - Ledger / chart of accounts
    - Journal entries
    - Transactions
    - VAT
    - Payroll
    - Inventory
    - Cashbook & bank rec
    - Bank feeds (OFX / PDF imports)
    """

    cur = conn.cursor()

    cur.executescript("""

    -- ───────────────────────────────────────
    -- COMPANY INFO
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS company_info (
        id INTEGER PRIMARY KEY CHECK(id=1),
        name TEXT NOT NULL,
        trading_as TEXT,
        reg_no TEXT,
        vat_no TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        company_type TEXT DEFAULT 'Pty Ltd',
        website TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    -- ───────────────────────────────────────
    -- USERS
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    );

    -- ───────────────────────────────────────
    -- CUSTOMERS & VENDORS
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        address TEXT,
        vat_no TEXT,
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        address TEXT,
        vat_no TEXT
    );

    -- ───────────────────────────────────────
    -- CHART OF ACCOUNTS
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL, -- Asset, Liability, Equity, Income, Expense
        parent_id INTEGER
    );

    -- ───────────────────────────────────────
    -- GENERAL LEDGER JOURNAL
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        reference TEXT,
        memo TEXT
    );

    CREATE TABLE IF NOT EXISTS journal_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        debit REAL DEFAULT 0,
        credit REAL DEFAULT 0
    );

    -- ───────────────────────────────────────
    -- SALES (Invoices, Quotes)
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        date TEXT NOT NULL,
        due_date TEXT,
        reference TEXT,
        notes TEXT,
        status TEXT DEFAULT 'Draft',
        subtotal REAL DEFAULT 0,
        vat REAL DEFAULT 0,
        total REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        description TEXT,
        qty REAL,
        price REAL,
        vat REAL DEFAULT 0,
        vat_rate REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        date TEXT NOT NULL,
        valid_until TEXT,
        reference TEXT,
        subtotal REAL DEFAULT 0,
        vat REAL DEFAULT 0,
        total REAL DEFAULT 0,
        status TEXT DEFAULT 'Draft'
    );

    -- ───────────────────────────────────────
    -- PURCHASES (Bills, Supplier Invoices)
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id INTEGER,
        date TEXT NOT NULL,
        due_date TEXT,
        reference TEXT,
        subtotal REAL DEFAULT 0,
        vat REAL DEFAULT 0,
        total REAL DEFAULT 0,
        status TEXT DEFAULT 'Unpaid'
    );

    CREATE TABLE IF NOT EXISTS bill_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER,
        description TEXT,
        qty REAL,
        price REAL,
        vat_rate REAL DEFAULT 0
    );

    -- ───────────────────────────────────────
    -- INVENTORY
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE,
        name TEXT NOT NULL,
        qty REAL DEFAULT 0,
        cost REAL DEFAULT 0,
        sell_price REAL DEFAULT 0,
        vat_rate REAL DEFAULT 0
    );

    -- ───────────────────────────────────────
    -- VAT CONFIGURATION
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS vat_settings (
        id INTEGER PRIMARY KEY CHECK(id=1),
        vat_number TEXT,
        registration_date TEXT,
        vat_period TEXT DEFAULT 'Monthly'
    );

    -- ───────────────────────────────────────
    -- SIMPLE TRANSACTIONS (Banking → UI)
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        type TEXT CHECK(type IN ('Income','Expense')),
        category_id INTEGER,
        audit_user TEXT,
        audit_timestamp TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        type TEXT CHECK(type IN ('Income','Expense'))
    );

    -- ───────────────────────────────────────
    -- PAYROLL
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        id_number TEXT,
        tax_number TEXT,
        uif_number TEXT,
        salary REAL,
        paye_rate REAL DEFAULT 0,
        uif_rate REAL DEFAULT 0.01,
        sdl_rate REAL DEFAULT 0.01,
        start_date TEXT,
        address TEXT,
        marital_status TEXT
    );

    CREATE TABLE IF NOT EXISTS payroll_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        period TEXT NOT NULL,
        total_gross REAL,
        total_net REAL,
        total_paye REAL,
        total_uif REAL,
        total_sdl REAL,
        status TEXT DEFAULT 'Draft'
    );

    CREATE TABLE IF NOT EXISTS payroll_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        employee_id INTEGER,
        gross REAL,
        paye REAL,
        uif_employee REAL,
        uif_employer REAL,
        sdl REAL,
        net REAL
    );

    -- ───────────────────────────────────────
    -- CASHBOOK & BANK RECONCILIATION
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS cash_book (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        account TEXT NOT NULL,
        narration TEXT,
        reference TEXT,
        debit REAL DEFAULT 0,
        credit REAL DEFAULT 0,
        reconciled INTEGER DEFAULT 0,
        batch_no TEXT,
        entry_type TEXT DEFAULT 'normal'
    );

    CREATE TABLE IF NOT EXISTS reconciliations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cashbook_name TEXT,
        statement_from TEXT,
        statement_to TEXT,
        bank_balance REAL,
        reconciled_on TEXT DEFAULT (datetime('now')),
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS bank_statement_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reconciliation_id INTEGER,
        fitid TEXT,
        tx_date TEXT,
        description TEXT,
        amount REAL,
        source TEXT,
        matched_entry_id INTEGER,
        cleared INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS reconciliation_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reconciliation_id INTEGER,
        statement_line_id INTEGER,
        cashbook_entry_id INTEGER,
        matched_on TEXT DEFAULT (datetime('now')),
        match_score REAL
    );

    -- ───────────────────────────────────────
    -- AUDIT LOG
    -- ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        user TEXT,
        action TEXT
    );
    """)

    clean = sanitize_company_name(company_name)
    cur.execute("INSERT OR IGNORE INTO company_info (id, name) VALUES (1, ?)", (clean,))
    cur.execute("INSERT OR IGNORE INTO vat_settings (id) VALUES (1)")
    conn.commit()

    # Seed starter chart of accounts
    try:
        seed_chart_of_accounts(conn)
    except Exception as e:
        print("[db] Failed to seed chart of accounts:", e)

    print(f"Database initialized for company: {clean}")


# ─────────────────────────────────────────────────────────────
# PUBLIC FUNCTIONS
# ─────────────────────────────────────────────────────────────

def create_company(name: str):
    clean = sanitize_company_name(name)
    if not clean:
        raise ValueError("Invalid company name")

    dir_ = COMPANIES_DIR / clean
    if dir_.exists():
        raise FileExistsError("Company already exists")

    dir_.mkdir(parents=True)

    # create db
    db_path = dir_ / "nexledger.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db_for_company(conn, clean)
    conn.close()

    set_current_company(clean)
    return clean


def delete_company(name: str) -> bool:
    try:
        shutil.rmtree(COMPANIES_DIR / name)
        if get_current_company() == name:
            global _CURRENT_COMPANY
            _CURRENT_COMPANY = None
            if SETTINGS_FILE.exists():
                SETTINGS_FILE.unlink()
        return True
    except:
        return False


def list_companies():
    if not COMPANIES_DIR.exists():
        return []
    return sorted([
        d.name for d in COMPANIES_DIR.iterdir()
        if d.is_dir() and (d / "nexledger.db").exists()
    ])


def save_company_info(data: dict):
    with db_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO company_info
            (id, name, trading_as, reg_no, vat_no, phone, email, address, company_type, website)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name"),
            data.get("trading_as"),
            data.get("reg_no"),
            data.get("vat_no"),
            data.get("phone"),
            data.get("email"),
            data.get("address"),
            data.get("company_type"),
            data.get("website")
        ))
        conn.commit()


def get_company_info():
    conn = get_conn_safe()
    if not conn:
        return {"name": "No company"}
    row = conn.execute("SELECT * FROM company_info WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {"name": get_current_company()}


def log_audit(action: str, user="user"):
    conn = get_conn_safe()
    if not conn:
        return
    conn.execute(
        "INSERT INTO audit_log(timestamp, user, action) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), user, action)
    )
    conn.commit()
    conn.close()


def get_conn_raw():
    """
    Returns a raw SQLite connection to the current company's database.
    Does not wrap with context managers or auto-init logic.
    Raises ValueError if no company is selected.
    """
    require_company()  # ensure a company is selected
    db_path = get_db_path()
    if not db_path:
        raise ValueError("Database path not found for the current company.")
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn




def is_duplicate_transaction(date: str, description: str) -> bool:
    conn = get_conn_safe()
    if not conn:
        return False
    row = conn.execute("""
        SELECT 1 FROM transactions
        WHERE date=? AND LOWER(description)=LOWER(?)
        LIMIT 1
    """, (date, description)).fetchone()
    conn.close()
    return row is not None
