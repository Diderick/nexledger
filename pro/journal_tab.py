# pro/journal_tab.py
# Full Journal Tab (Integrated Journal Engine) – 2025-11-18
# Requires: PyQt6, shared.db.get_conn(), shared.theme.get_widget_style()

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QDoubleSpinBox, QLineEdit, QTextEdit, QDateEdit, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt, QDate
from datetime import datetime
from shared.db import get_conn
from shared.theme import get_widget_style

# ---------------------------
# DB Migration / Schema Helpers
# ---------------------------
def ensure_table(conn, ddl):
    cur = conn.cursor()
    cur.execute(ddl)
    conn.commit()

def table_has_column(conn, table, column):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def add_column_if_missing(conn, table, column, ddl_fragment):
    if not table_has_column(conn, table, column):
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_fragment}")
        conn.commit()

def init_journal_schema():
    conn = get_conn()
    # Main header + lines for general journals (separate from 'journals' created by bank module)
    ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS journal_headers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_date TEXT NOT NULL,
            reference TEXT,
            description TEXT,
            total_debits REAL NOT NULL DEFAULT 0,
            total_credits REAL NOT NULL DEFAULT 0,
            journal_type TEXT DEFAULT 'GJ', -- GJ = General Journal
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            header_id INTEGER NOT NULL,
            gl_account_id INTEGER NOT NULL,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            line_description TEXT,
            FOREIGN KEY (header_id) REFERENCES journal_headers(id),
            FOREIGN KEY (gl_account_id) REFERENCES gl_accounts(id)
        );
    """)
    # keep backwards-compatible 'journals' / 'journal_lines' used by bank opening if present
    ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS journals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_date TEXT NOT NULL,
            description TEXT,
            created_on TEXT DEFAULT (datetime('now'))
        );
    """)
    ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_id INTEGER NOT NULL,
            gl_account_id INTEGER NOT NULL,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            narrative TEXT,
            FOREIGN KEY (journal_id) REFERENCES journals(id),
            FOREIGN KEY (gl_account_id) REFERENCES gl_accounts(id)
        );
    """)
    conn.close()

# initialize schema at import time
try:
    init_journal_schema()
except Exception as e:
    print("Warning: init_journal_schema failed:", e)

# ---------------------------
# Utility functions
# ---------------------------
def format_currency(v):
    try:
        return f"{float(v):,.2f}"
    except:
        return "0.00"

def next_journal_reference(conn, prefix="JRNL"):
    """Generate next ref: PREFIX-YYYY-000001 style using journal_headers table."""
    cur = conn.cursor()
    year = datetime.now().year
    cur.execute("SELECT MAX(id) FROM journal_headers")
    r = cur.fetchone()
    seq = (r[0] or 0) + 1
    return f"{prefix}-{year}-{seq:06d}"

# ---------------------------
# Posting helpers for integration
# ---------------------------
def post_manual_journal(journal_date, description, lines, journal_type="GJ", reference=None):
    """
    Post a general journal.
    lines: list of dict {gl_account_id: int, debit: float, credit: float, line_description: str}
    Ensures totals balance before posting.
    Returns inserted header id.
    """
    total_debits = sum(float(l.get("debit", 0) or 0) for l in lines)
    total_credits = sum(float(l.get("credit", 0) or 0) for l in lines)
    if round(total_debits, 2) != round(total_credits, 2):
        raise ValueError(f"Journal not balanced (Debits {total_debits:.2f} != Credits {total_credits:.2f})")

    conn = get_conn()
    cur = conn.cursor()
    if not reference:
        reference = next_journal_reference(conn)
    cur.execute("""
        INSERT INTO journal_headers (journal_date, reference, description, total_debits, total_credits, journal_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (journal_date, reference, description, total_debits, total_credits, journal_type))
    header_id = cur.lastrowid
    for ln in lines:
        gl = ln["gl_account_id"]
        d = float(ln.get("debit", 0) or 0)
        c = float(ln.get("credit", 0) or 0)
        narrative = ln.get("line_description") or ""
        cur.execute("""
            INSERT INTO journal_lines (header_id, gl_account_id, debit, credit, line_description)
            VALUES (?, ?, ?, ?, ?)
        """, (header_id, gl, d, c, narrative))
    conn.commit()
    conn.close()
    return header_id

def post_cashbook_transaction(cashbook_name, tx_date, amount, contra_gl_account_id, description="", is_receipt=True):
    """
    Convenience function to post a cashbook transaction to the journal engine.
    - cashbook_name: name used to find cashbook -> gl_account_id
    - amount: positive value
    - contra_gl_account_id: the other side of the transaction (e.g., Sales GL)
    - is_receipt: True => Receipt (bank debited), False => Payment (bank credited)
    Returns header_id.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT gl_account_id FROM cashbooks WHERE name = ?", (cashbook_name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Cashbook '{cashbook_name}' not found.")
    bank_gl = row[0]
    lines = []
    amt = float(amount)
    if is_receipt:
        # Debit bank, Credit contra
        lines.append({"gl_account_id": bank_gl, "debit": amt, "credit": 0, "line_description": description})
        lines.append({"gl_account_id": contra_gl_account_id, "debit": 0, "credit": amt, "line_description": description})
    else:
        # Payment: Debit contra, Credit bank
        lines.append({"gl_account_id": contra_gl_account_id, "debit": amt, "credit": 0, "line_description": description})
        lines.append({"gl_account_id": bank_gl, "debit": 0, "credit": amt, "line_description": description})
    header_id = post_manual_journal(tx_date, f"Cashbook post: {description}", lines, journal_type="CB")
    conn.close()
    return header_id

def create_reversing_journal(original_header_id, reversal_date=None):
    """Create a reversing journal that swaps debit/credit for each line."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT journal_date, description FROM journal_headers WHERE id = ?", (original_header_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("Original journal not found")
    orig_date, orig_desc = row
    cur.execute("SELECT gl_account_id, debit, credit, line_description FROM journal_lines WHERE header_id = ?", (original_header_id,))
    lines = []
    for r in cur.fetchall():
        gl, d, c, narr = r
        # swap
        lines.append({"gl_account_id": gl, "debit": float(c), "credit": float(d), "line_description": f"Reversal: {narr}"})
    rev_date = reversal_date or datetime.now().strftime("%Y-%m-%d")
    rev_ref = next_journal_reference(conn).replace("JRNL", "REV")
    hid = post_manual_journal(rev_date, f"Reversal of {orig_desc}", lines, journal_type="RV", reference=rev_ref)
    conn.close()
    return hid

# ---------------------------
# Journal Tab UI
# ---------------------------
class JournalTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.account_map = {}  # gl_account_id -> "account_number - name"
        self.setup_ui()
        self.load_gl_accounts()
        self.add_line()  # start with one line

    def setup_ui(self):
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(12, 12, 12, 12)
        title = QLabel("<b>Journal Entries</b>")
        title.setStyleSheet("font-size:16px;font-weight:700;")
        self.layout().addWidget(title)

        # Top form: date, reference, description
        top = QHBoxLayout()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.ref_edit = QLineEdit()
        self.ref_edit.setPlaceholderText("Leave blank to auto-generate")
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Journal description...")
        top.addWidget(QLabel("Date:"))
        top.addWidget(self.date_edit)
        top.addWidget(QLabel("Reference:"))
        top.addWidget(self.ref_edit)
        top.addWidget(QLabel("Description:"))
        top.addWidget(self.desc_edit)
        self.layout().addLayout(top)

        # Table for lines
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(5)
        self.tbl.setHorizontalHeaderLabels(["Account", "Debit", "Credit", "Line Description", ""])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.setAlternatingRowColors(True)
        self.layout().addWidget(self.tbl, 1)

        # Bottom controls: add line, totals, save
        bottom = QHBoxLayout()
        self.btn_add = QPushButton("Add Line")
        self.btn_add.clicked.connect(self.add_line)
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self.remove_selected)
        bottom.addWidget(self.btn_add)
        bottom.addWidget(self.btn_remove)

        bottom.addStretch()
        self.debit_total_lbl = QLabel("Debits: 0.00")
        self.credit_total_lbl = QLabel("Credits: 0.00")
        self.status_lbl = QLabel("")  # will show balanced/unbalanced
        bottom.addWidget(self.debit_total_lbl)
        bottom.addWidget(self.credit_total_lbl)
        bottom.addWidget(self.status_lbl)

        self.btn_save = QPushButton("Save Journal Entry")
        self.btn_save.clicked.connect(self.save_journal)
        self.btn_save.setEnabled(False)
        bottom.addWidget(self.btn_save)

        self.layout().addLayout(bottom)
        self.setStyleSheet(get_widget_style())

    def load_gl_accounts(self):
        """Load GL accounts into a list for the account combo boxes."""
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, account_number, name FROM gl_accounts WHERE active = 1 ORDER BY account_number")
        rows = cur.fetchall()
        self.accounts = [(r[0], f"{r[1]} - {r[2]}") for r in rows]
        self.account_map = {r[0]: f"{r[1]} - {r[2]}" for r in rows}
        conn.close()

    def add_line(self, gl_id=None, debit=0.0, credit=0.0, line_desc=""):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)

        # Account Combo
        cb = QComboBox()
        for aid, label in self.accounts:
            cb.addItem(label, aid)
        if gl_id:
            # try to set index to matching gl_id
            idx = next((i for i, (a,_) in enumerate(self.accounts) if a == gl_id), 0)
            cb.setCurrentIndex(idx)
        self.tbl.setCellWidget(row, 0, cb)

        # Debit spin
        dspin = QDoubleSpinBox()
        dspin.setRange(-1e12, 1e12)
        dspin.setDecimals(2)
        dspin.setValue(float(debit or 0))
        dspin.valueChanged.connect(self.recalculate_totals)
        self.tbl.setCellWidget(row, 1, dspin)

        # Credit spin
        cspin = QDoubleSpinBox()
        cspin.setRange(-1e12, 1e12)
        cspin.setDecimals(2)
        cspin.setValue(float(credit or 0))
        cspin.valueChanged.connect(self.recalculate_totals)
        self.tbl.setCellWidget(row, 2, cspin)

        # Line description
        ldesc = QLineEdit()
        ldesc.setText(line_desc or "")
        self.tbl.setCellWidget(row, 3, ldesc)

        # Remove button / handle
        btn = QPushButton("X")
        btn.clicked.connect(lambda _, r=row: self.remove_row(r))
        self.tbl.setCellWidget(row, 4, btn)

        self.recalculate_totals()

    def remove_row(self, row_idx):
        # Removing by index: safer to find actual row index for the widget because lambda binds early
        # We'll remove currently selected row if index out of range
        if row_idx >= self.tbl.rowCount() or row_idx < 0:
            sel = self.tbl.currentRow()
            if sel >= 0:
                self.tbl.removeRow(sel)
        else:
            # find the current count and remove that row
            try:
                self.tbl.removeRow(row_idx)
            except Exception:
                # fallback
                sel = self.tbl.currentRow()
                if sel >= 0:
                    self.tbl.removeRow(sel)
        self.recalculate_totals()

    def remove_selected(self):
        sel = self.tbl.currentRow()
        if sel >= 0:
            self.tbl.removeRow(sel)
            self.recalculate_totals()
        else:
            QMessageBox.information(self, "Remove", "Select a row to remove.")

    def recalculate_totals(self):
        total_debit = 0.0
        total_credit = 0.0
        for r in range(self.tbl.rowCount()):
            dspin = self.tbl.cellWidget(r, 1)
            cspin = self.tbl.cellWidget(r, 2)
            d = float(dspin.value() if dspin else 0)
            c = float(cspin.value() if cspin else 0)
            total_debit += d
            total_credit += c
        self.debit_total_lbl.setText(f"Debits: {format_currency(total_debit)}")
        self.credit_total_lbl.setText(f"Credits: {format_currency(total_credit)}")
        # Visual cue
        if round(total_debit, 2) == round(total_credit, 2) and total_debit != 0:
            self.status_lbl.setText("<font color='green'><b>Balanced</b></font>")
            self.btn_save.setEnabled(True)
        else:
            if total_debit == 0 and total_credit == 0:
                self.status_lbl.setText("")
            else:
                self.status_lbl.setText("<font color='red'><b>Not Balanced</b></font>")
            self.btn_save.setEnabled(False)

    def collect_lines(self):
        lines = []
        for r in range(self.tbl.rowCount()):
            cb = self.tbl.cellWidget(r, 0)
            dspin = self.tbl.cellWidget(r, 1)
            cspin = self.tbl.cellWidget(r, 2)
            ldesc = self.tbl.cellWidget(r, 3)
            if cb is None:
                continue
            gl_id = cb.currentData()
            debit = float(dspin.value() if dspin else 0)
            credit = float(cspin.value() if cspin else 0)
            if round(debit, 2) == 0 and round(credit, 2) == 0:
                continue  # skip empty lines
            lines.append({
                "gl_account_id": int(gl_id),
                "debit": debit,
                "credit": credit,
                "line_description": ldesc.text() if ldesc else ""
            })
        return lines

    def save_journal(self):
        lines = self.collect_lines()
        if not lines:
            QMessageBox.warning(self, "Empty", "Journal has no lines.")
            return
        total_debits = sum(l["debit"] for l in lines)
        total_credits = sum(l["credit"] for l in lines)
        if round(total_debits, 2) != round(total_credits, 2):
            QMessageBox.critical(self, "Unbalanced", "Journal is not balanced. Debits must equal Credits.")
            return

        date_s = self.date_edit.date().toString("yyyy-MM-dd")
        description = self.desc_edit.text().strip()
        reference = self.ref_edit.text().strip() or None

        try:
            header_id = post_manual_journal(date_s, description, lines, journal_type="GJ", reference=reference)
            QMessageBox.information(self, "Saved", f"Journal saved (ID {header_id}).")
            # reset UI
            self.tbl.setRowCount(0)
            self.add_line()
            self.ref_edit.clear()
            self.desc_edit.clear()
            self.recalculate_totals()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

# ---------------------------
# Integration helper & test-run
# ---------------------------
def add_journal_tab_to_ui(tab_widget):
    t = JournalTab()
    tab_widget.addTab(t, "Journals")
    return t

if __name__ == "__main__":
    # quick manual test runner
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    w = JournalTab()
    w.show()
    sys.exit(app.exec())
