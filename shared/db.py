import sqlite3
import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import inspect

ROOT_DIR = Path(__file__).parent.parent
COMPANIES_DIR = ROOT_DIR / "companies"
SETTINGS_FILE = ROOT_DIR / "settings.json"
_CURRENT_COMPANY = None


def sanitize_company_name(name: str) -> str:
    if not name:
        return ""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', ' ', name)
    return name[:100]


def set_current_company(name: str):
    global _CURRENT_COMPANY
    _CURRENT_COMPANY = name
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"last_company": name}, f, indent=2)
    except Exception as e:
        print(f"Save settings failed: {e}")


def get_current_company() -> str | None:
    global _CURRENT_COMPANY
    if _CURRENT_COMPANY:
        return _CURRENT_COMPANY
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                name = data.get("last_company")
                if name and (COMPANIES_DIR / name).exists():
                    _CURRENT_COMPANY = name
                    return name
        except Exception as e:
            print(f"Load settings failed: {e}")
    companies = list_companies()
    if companies:
        name = companies[0]
        set_current_company(name)
        return name
    return None


def get_db_path() -> Path | None:
    company = get_current_company()
    if not company:
        return None
    return COMPANIES_DIR / company / "nexledger.db"


@contextmanager
def _get_conn_context():
    company = get_current_company()
    if not company:
        raise ValueError("No company selected. Create or select a company first.")

    db_path = get_db_path()
    if not db_path:
        raise ValueError("Invalid company path.")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    first_time = not db_path.exists()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if first_time or not _table_exists(conn, "company_info"):
        print(f"Initializing database for company: {company}")
        init_db_for_company(conn, company)

    try:
        yield conn
    finally:
        conn.close()


def get_conn():
    frame = inspect.currentframe().f_back
    code_context = (inspect.getframeinfo(frame).code_context or [""])[0].strip()

    if code_context.startswith("with "):
        return _get_conn_context()
    else:
        company = get_current_company()
        if not company:
            raise ValueError("No company selected. Create or select a company first.")

        db_path = get_db_path()
        if not db_path:
            raise ValueError("Invalid company path.")

        db_path.parent.mkdir(parents=True, exist_ok=True)

        first_time = not db_path.exists()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        if first_time or not _table_exists(conn, "company_info"):
            print(f"Initializing database for company: {company}")
            init_db_for_company(conn, company)

        return conn


def _table_exists(conn, table_name: str) -> bool:
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cur.fetchone() is not None
    except:
        return False


def init_db_for_company(conn, company_name: str):
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS company_info (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            trading_as TEXT, reg_no TEXT, vat_no TEXT,
            phone TEXT, email TEXT, address TEXT,
            company_type TEXT DEFAULT 'Pty Ltd', website TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT, phone TEXT, address TEXT
        );

        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT, phone TEXT
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, 
            description TEXT NOT NULL,
            amount REAL NOT NULL, 
            type TEXT NOT NULL CHECK(type IN ('Income','Expense')),
            category_id INTEGER,
            audit_user TEXT,
            audit_timestamp TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, 
            type TEXT NOT NULL CHECK(type IN ('Income','Expense'))
        );

        CREATE TABLE IF NOT EXISTS vat_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            vat_number TEXT, registration_date TEXT,
            vat_period TEXT DEFAULT 'Monthly'
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user TEXT NOT NULL,
            action TEXT NOT NULL
        );

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
            address TEXT
        );

        CREATE TABLE IF NOT EXISTS payroll_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            period TEXT NOT NULL,
            total_gross REAL DEFAULT 0,
            total_net REAL DEFAULT 0,
            total_paye REAL DEFAULT 0,
            total_uif REAL DEFAULT 0,
            total_sdl REAL DEFAULT 0,
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
            net REAL,
            FOREIGN KEY(run_id) REFERENCES payroll_runs(id),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );
    ''')
    clean_name = sanitize_company_name(company_name)
    cur.execute("INSERT OR IGNORE INTO company_info (id, name) VALUES (1, ?)", (clean_name,))
    cur.execute("INSERT OR IGNORE INTO vat_settings (id, vat_period) VALUES (1, 'Monthly')")
    conn.commit()
    print(f"Database initialized for: {clean_name}")


def create_company(company_name: str) -> str:
    clean_name = sanitize_company_name(company_name)
    if not clean_name:
        raise ValueError("Company name cannot be empty.")

    company_dir = COMPANIES_DIR / clean_name
    if company_dir.exists():
        raise FileExistsError(f"Company '{clean_name}' already exists.")

    company_dir.mkdir(parents=True, exist_ok=False)
    db_path = company_dir / "nexledger.db"

    with sqlite3.connect(db_path) as conn:
        init_db_for_company(conn, clean_name)

    set_current_company(clean_name)
    return clean_name


def delete_company(company_name: str) -> bool:
    company_dir = COMPANIES_DIR / company_name
    if not company_dir.exists():
        return False
    try:
        shutil.rmtree(company_dir)
        if get_current_company() == company_name:
            global _CURRENT_COMPANY
            _CURRENT_COMPANY = None
            if SETTINGS_FILE.exists():
                SETTINGS_FILE.unlink()
        return True
    except Exception as e:
        print(f"Delete failed: {e}")
        return False


def save_company_info(data: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO company_info 
        (id, name, trading_as, reg_no, vat_no, phone, email, address, company_type, website)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("name"), data.get("trading_as"), data.get("reg_no"), data.get("vat_no"),
        data.get("phone"), data.get("email"), data.get("address"),
        data.get("company_type", "Pty Ltd"), data.get("website")
    ))
    conn.commit()
    conn.close()


def get_company_info() -> dict:
    try:
        conn = get_conn()
        row = conn.execute("SELECT * FROM company_info WHERE id = 1").fetchone()
        conn.close()
        return dict(row) if row else {"name": get_current_company()}
    except Exception as e:
        print(f"Get company info error: {e}")
        return {"name": get_current_company() or "Unknown"}


def list_companies() -> list[str]:
    if not COMPANIES_DIR.exists():
        return []
    return sorted([
        d.name for d in COMPANIES_DIR.iterdir()
        if d.is_dir() and (d / "nexledger.db").exists()
    ])


def is_duplicate_transaction(date: str, description: str) -> bool:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM transactions 
            WHERE date = ? AND LOWER(TRIM(description)) = LOWER(TRIM(?))
            LIMIT 1
        """, (date, description))
        exists = cur.fetchone() is not None
        conn.close()
        return exists
    except Exception as e:
        print("Duplicate check error:", e)
        return False


def log_audit(action: str, user: str = "user"):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (timestamp, user, action)
            VALUES (?, ?, ?)
        """, (datetime.now().isoformat(), user, action))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Audit log failed:", e)


def get_conn_raw():
    """Direct connection – use when you need conn.cursor() outside 'with'"""
    company = get_current_company()
    if not company:
        raise ValueError("No company selected.")
    db_path = COMPANIES_DIR / company / "nexledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def close_all_dbs():
    """Close all persistent DB connections gracefully on application shutdown."""
    global _connections
    for conn in list(_connections.values()):
        try:
            conn.commit()
            conn.close()
        except Exception:
            pass
    _connections.clear()
