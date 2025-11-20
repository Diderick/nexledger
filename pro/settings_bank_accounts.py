# pro/settings_bank_accounts.py
# Bank Accounts setup: list + add/edit dialog + automatic opening balance posting (Option A)
# Drop into your project and add as a settings tab:
#   self.tabs.addTab(BankAccountsTab(), "Bank Accounts")

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox,
    QLabel, QTextEdit
)
from PyQt6.QtCore import Qt, QDate
from datetime import datetime
from shared.db import get_conn
from shared.theme import get_widget_style
import sqlite3

# ---------------------------
# DB MIGRATIONS / HELPERS
# ---------------------------
def ensure_table(conn, ddl):
    """Create table if not exists using provided DDL."""
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

def init_schema():
    conn = get_conn()
    # GL accounts (chart of accounts)
    ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS gl_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_number TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('BANK','CASH','ASSET','LIABILITY','INCOME','EXPENSE','EQUITY')),
            active INTEGER DEFAULT 1,
            opening_balance REAL DEFAULT 0,
            opening_date TEXT DEFAULT NULL,
            notes TEXT DEFAULT ''
        );
    """)

    # cashbooks table linking to GL account
    ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS cashbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            gl_account_id INTEGER NOT NULL,
            FOREIGN KEY (gl_account_id) REFERENCES gl_accounts(id)
        );
    """)

    # simple journal header + lines to record opening balances & future postings
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

    # safe add columns if older schema exists
    add_column_if_missing(conn, "gl_accounts", "opening_balance", "REAL DEFAULT 0")
    add_column_if_missing(conn, "gl_accounts", "opening_date", "TEXT")
    add_column_if_missing(conn, "gl_accounts", "notes", "TEXT DEFAULT ''")
    conn.close()

# Initialize DB schema on import
try:
    init_schema()
except Exception as e:
    # DB might not be accessible at import-time in some test scenarios; let UI show errors later
    print("Warning: init_schema failed:", e)

# ---------------------------
# Bank Account Dialog
# ---------------------------
class BankAccountDialog(QDialog):
    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Bank Account")
        self.setMinimumWidth(480)
        self.account = account  # None => new, otherwise dict with fields
        self.setup_ui()
        if self.account:
            self.load_account()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.txt_number = QLineEdit()
        self.txt_name = QLineEdit()
        self.cb_type = QComboBox()
        self.cb_type.addItems(["BANK", "CASH"])
        self.spin_opening = QDoubleSpinBox()
        self.spin_opening.setRange(-1e12, 1e12)
        self.spin_opening.setDecimals(2)
        self.spin_opening.setSingleStep(10.0)
        self.date_open = QDateEdit(QDate.currentDate())
        self.date_open.setCalendarPopup(True)
        self.txt_notes = QTextEdit()
        self.txt_notes.setFixedHeight(80)

        form.addRow("Account Number:", self.txt_number)
        form.addRow("Account Name:", self.txt_name)
        form.addRow("Type:", self.cb_type)
        form.addRow("Opening Balance:", self.spin_opening)
        form.addRow("Opening Date:", self.date_open)
        form.addRow("Notes:", self.txt_notes)

        layout.addLayout(form)

        btns = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

    def load_account(self):
        self.txt_number.setText(self.account.get("account_number", ""))
        self.txt_name.setText(self.account.get("name", ""))
        t = self.account.get("type", "BANK")
        idx = 0 if t == "BANK" else 1
        self.cb_type.setCurrentIndex(idx)
        self.spin_opening.setValue(float(self.account.get("opening_balance", 0) or 0))
        od = self.account.get("opening_date")
        if od:
            try:
                dt = datetime.strptime(od, "%Y-%m-%d")
                self.date_open.setDate(QDate(dt.year, dt.month, dt.day))
            except:
                pass
        self.txt_notes.setPlainText(self.account.get("notes", ""))

    def on_save(self):
        acc_no = self.txt_number.text().strip()
        name = self.txt_name.text().strip()
        acc_type = self.cb_type.currentText()
        opening = float(self.spin_opening.value())
        opening_date = self.date_open.date().toString("yyyy-MM-dd")
        notes = self.txt_notes.toPlainText().strip()

        if not acc_no or not name:
            QMessageBox.critical(self, "Validation", "Please provide both Account Number and Account Name.")
            return

        conn = get_conn()
        cur = conn.cursor()

        try:
            if self.account:  # update existing
                cur.execute("""
                    UPDATE gl_accounts
                    SET account_number=?, name=?, type=?, opening_balance=?, opening_date=?, notes=?
                    WHERE id=?
                """, (acc_no, name, acc_type, opening, opening_date, notes, self.account["id"]))
                conn.commit()
                QMessageBox.information(self, "Saved", "Account updated.")
                self.accept()
                return

            # insert new account
            cur.execute("""
                INSERT INTO gl_accounts (account_number, name, type, opening_balance, opening_date, notes, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (acc_no, name, acc_type, opening, opening_date, notes))
            acc_id = cur.lastrowid

            # Option A: automatically post opening balance to journals (debit the bank if positive opening)
            # Posting convention: positive opening => Debit bank (asset), Credit Opening Bal Equity/Retained Earnings
            if abs(opening) > 0.0:
                # Ensure there's an 'OPENING BALANCE' GL placeholder account (create if missing)
                cur.execute("SELECT id FROM gl_accounts WHERE account_number = '0000' AND name = 'Opening Bal Equity'")
                row = cur.fetchone()
                if row:
                    opening_equity_id = row[0]
                else:
                    cur.execute("""
                        INSERT INTO gl_accounts (account_number, name, type, active)
                        VALUES ('0000', 'Opening Bal Equity', 'EQUITY', 1)
                    """)
                    opening_equity_id = cur.lastrowid

                # Create journal header
                desc = f"Opening balance for {name} ({acc_no})"
                journal_date = opening_date or datetime.now().strftime("%Y-%m-%d")
                cur.execute("INSERT INTO journals (journal_date, description) VALUES (?, ?)", (journal_date, desc))
                journal_id = cur.lastrowid

                # If opening > 0 => debit bank, credit opening equity
                if opening > 0:
                    debit_amt = opening
                    credit_amt = opening
                    # bank line (debit)
                    cur.execute("""
                        INSERT INTO journal_lines (journal_id, gl_account_id, debit, credit, narrative)
                        VALUES (?, ?, ?, 0, ?)
                    """, (journal_id, acc_id, debit_amt, f"Opening balance ({acc_no})"))
                    # opening equity line (credit)
                    cur.execute("""
                        INSERT INTO journal_lines (journal_id, gl_account_id, debit, credit, narrative)
                        VALUES (?, ?, 0, ?, ?)
                    """, (journal_id, opening_equity_id, credit_amt, f"Opening balance ({acc_no})"))
                else:
                    # negative opening (bank overdrawn) => credit bank, debit opening equity (or opposite)
                    debit_amt = abs(opening)
                    credit_amt = abs(opening)
                    cur.execute("""
                        INSERT INTO journal_lines (journal_id, gl_account_id, debit, credit, narrative)
                        VALUES (?, ?, ?, 0, ?)
                    """, (journal_id, opening_equity_id, debit_amt, f"Opening balance ({acc_no})"))
                    cur.execute("""
                        INSERT INTO journal_lines (journal_id, gl_account_id, debit, credit, narrative)
                        VALUES (?, ?, 0, ?, ?)
                    """, (journal_id, acc_id, credit_amt, f"Opening balance ({acc_no})"))

            conn.commit()
            QMessageBox.information(self, "Saved", "Account created and opening balance posted.")
            self.accept()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            conn.close()

# ---------------------------
# Bank Accounts Tab
# ---------------------------
class BankAccountsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        lbl = QLabel("<b>Bank / Cash Accounts</b>")
        lbl.setStyleSheet("font-size:16px;font-weight:700;")
        top.addWidget(lbl)
        top.addStretch()

        btn_add = QPushButton("Add Account")
        btn_edit = QPushButton("Edit Account")
        btn_delete = QPushButton("Deactivate")
        btn_reload = QPushButton("Refresh")

        btn_add.clicked.connect(self.add_account)
        btn_edit.clicked.connect(self.edit_account)
        btn_delete.clicked.connect(self.deactivate_account)
        btn_reload.clicked.connect(self.load_accounts)

        top.addWidget(btn_add)
        top.addWidget(btn_edit)
        top.addWidget(btn_delete)
        top.addWidget(btn_reload)

        layout.addLayout(top)

        # table
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(6)
        self.tbl.setHorizontalHeaderLabels(["ID", "Account No", "Account Name", "Type", "Opening Balance", "Active"])
        self.tbl.horizontalHeader().setSectionResizeMode(1, self.tbl.horizontalHeader().ResizeMode.Stretch)
        self.tbl.setColumnHidden(0, True)  # hide internal id by default
        self.tbl.setAlternatingRowColors(True)
        self.tbl.cellDoubleClicked.connect(self.on_double_click)
        layout.addWidget(self.tbl, 1)

        self.setStyleSheet(get_widget_style())

    def load_accounts(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, account_number, name, type, opening_balance, active FROM gl_accounts ORDER BY account_number")
            rows = cur.fetchall()
            self.tbl.setRowCount(0)
            for i, r in enumerate(rows):
                self.tbl.insertRow(i)
                for c, v in enumerate(r):
                    if c == 4 and v is not None:
                        item = QTableWidgetItem(f"{float(v):.2f}")
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    elif c == 5:
                        item = QTableWidgetItem("Yes" if int(v) else "No")
                    else:
                        item = QTableWidgetItem(str(v))
                    self.tbl.setItem(i, c, item)
        except Exception as e:
            QMessageBox.critical(self, "Error loading accounts", str(e))

    def get_selected_account(self):
        sel = self.tbl.currentRow()
        if sel < 0:
            return None
        try:
            acc_id = int(self.tbl.item(sel, 0).text())
            return self.fetch_account(acc_id)
        except Exception:
            return None

    def fetch_account(self, acc_id):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, account_number, name, type, opening_balance, opening_date, notes, active FROM gl_accounts WHERE id = ?", (acc_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return None
        return {
            "id": r[0], "account_number": r[1], "name": r[2], "type": r[3],
            "opening_balance": r[4], "opening_date": r[5], "notes": r[6], "active": r[7]
        }

    def add_account(self):
        dlg = BankAccountDialog(self)
        if dlg.exec():
            self.load_accounts()

    def edit_account(self):
        acc = self.get_selected_account()
        if not acc:
            QMessageBox.information(self, "Select", "Please select an account to edit (double-click row or select and press Edit).")
            return
        dlg = BankAccountDialog(self, account=acc)
        if dlg.exec():
            self.load_accounts()

    def deactivate_account(self):
        acc = self.get_selected_account()
        if not acc:
            QMessageBox.information(self, "Select", "Please select an account to deactivate.")
            return
        if QMessageBox.question(self, "Deactivate", f"Deactivate account {acc['name']} ({acc['account_number']})?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE gl_accounts SET active = 0 WHERE id = ?", (acc["id"],))
            conn.commit()
            QMessageBox.information(self, "Deactivated", "Account deactivated.")
            self.load_accounts()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            conn.close()

    def on_double_click(self, row, col):
        # treat double click as edit
        self.edit_account()

# ---------------------------
# Quick integration helper
# ---------------------------
def add_bank_accounts_tab_to_settings(settings_tab_widget):
    """
    Call this from your SettingsTab initialization to add the BankAccountsTab.
    Example:
        add_bank_accounts_tab_to_settings(self.settings_tabs)
    """
    tab = BankAccountsTab()
    settings_tab_widget.addTab(tab, "Bank Accounts")
    return tab

# If run as main for testing (not typical in app)
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    w = BankAccountsTab()
    w.show()
    sys.exit(app.exec())
