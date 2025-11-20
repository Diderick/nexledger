# banking_suite.py
# QuickBooks-style Banking Suite for NexLedger (Option A)
# Contains:
# - BankDashboardTab: left accounts list + action buttons
# - BankRegisterTab: register-style transaction view (running balance per transaction)\# - BankReconciliationTab: import statement, preview, auto-match, confirm matches
# - AccountManagerDialog: Add / Edit / Delete bank accounts
# - OpeningBalanceDialog: set opening balance (posts journal entry + cashbook)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QLineEdit, QMessageBox, QFileDialog, QDateEdit
)
from PyQt6.QtCore import Qt, QDate
from datetime import datetime
import sqlite3
import csv
import os

# Project DB helpers
try:
    from shared.db import db_connection, get_conn, get_conn_raw
    from shared.bank_import_engine import BankImportEngine
except Exception:
    # fallback stubs for standalone testing
    def get_conn():
        conn = sqlite3.connect(os.environ.get('LEDGER_DB', 'ledger.db'))
        conn.row_factory = sqlite3.Row
        return conn
    class BankImportEngine:
        def __init__(self, db_path=None):
            pass
        def import_csv_to_raw(self, filepath, mapping=None, date_format=None):
            return 0, []


# ---------- Utility helpers ----------

def format_money(v):
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return ""


def similarity(a: str, b: str) -> float:
    import difflib
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------- Dashboard Tab (Accounts list + actions) ----------
class BankDashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_accounts()

    def init_ui(self):
        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("Bank Accounts"))
        self.list = QListWidget()
        self.list.itemClicked.connect(self.open_register_for_item)
        left.addWidget(self.list)

        btn_add = QPushButton("Add Account")
        btn_add.clicked.connect(self.add_account)
        btn_edit = QPushButton("Edit Account")
        btn_edit.clicked.connect(self.edit_selected_account)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.load_accounts)
        left.addWidget(btn_add)
        left.addWidget(btn_edit)
        left.addWidget(btn_refresh)

        layout.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Actions"))
        btn_open_register = QPushButton("Open Register")
        btn_open_register.clicked.connect(self.open_register_for_selected)
        btn_reconcile = QPushButton("Reconcile")
        btn_reconcile.clicked.connect(self.open_reconciliation_for_selected)
        btn_import = QPushButton("Import Statement")
        btn_import.clicked.connect(self.import_statement_for_selected)
        right.addWidget(btn_open_register)
        right.addWidget(btn_reconcile)
        right.addWidget(btn_import)
        right.addStretch()

        layout.addLayout(right, 0)

    def load_accounts(self):
        self.list.clear()
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, code, name FROM accounts WHERE type='Asset' AND code LIKE '1%' ORDER BY code")
                rows = cur.fetchall()
        except Exception as e:
            print('[bank_dashboard] load_accounts error', e)
            rows = []

        for r in rows:
            item = QListWidgetItem(f"{r['code']} - {r['name']}")
            item.setData(Qt.ItemDataRole.UserRole, r['id'])
            self.list.addItem(item)

    def selected_account_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def open_register_for_item(self, item):
        acc_id = item.data(Qt.ItemDataRole.UserRole)
        self.open_register(acc_id)

    def open_register_for_selected(self):
        acc_id = self.selected_account_id()
        if not acc_id:
            QMessageBox.information(self, 'Select', 'Please select an account first')
            return
        self.open_register(acc_id)

    def open_register(self, account_id):
        tab = BankRegisterTab(account_id, parent=self)
        tab.show()

    def open_reconciliation_for_selected(self):
        acc_id = self.selected_account_id()
        if not acc_id:
            QMessageBox.information(self, 'Select', 'Please select an account first')
            return
        tab = BankReconciliationTab(acc_id, parent=self)
        tab.show()

    def import_statement_for_selected(self):
        acc_id = self.selected_account_id()
        if not acc_id:
            QMessageBox.information(self, 'Select', 'Please select an account first')
            return
        engine = BankImportEngine()
        fn, _ = QFileDialog.getOpenFileName(self, "Import statement (CSV)", os.getcwd(), "CSV Files (*.csv)")
        if not fn:
            return
        count, preview = engine.import_csv_to_raw(fn)
        QMessageBox.information(self, 'Imported', f'Imported {count} rows to Bank Feeds (raw).')

    def add_account(self):
        dlg = AccountManagerDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_accounts()

    def edit_selected_account(self):
        acc_id = self.selected_account_id()
        if not acc_id:
            QMessageBox.information(self, 'Select', 'Select account to edit')
            return
        dlg = AccountManagerDialog(account_id=acc_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_accounts()


# ---------- Bank Register Tab (Window) ----------
class BankRegisterTab(QWidget):
    def __init__(self, account_id: int, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.setWindowTitle('Bank Register')
        self.resize(900, 600)
        self.init_ui()
        self.load_transactions()

    def init_ui(self):
        layout = QVBoxLayout(self)
        hdr_layout = QHBoxLayout()
        hdr_layout.addWidget(QLabel('Account:'))
        self.account_label = QLabel('')
        hdr_layout.addWidget(self.account_label)
        hdr_layout.addStretch()
        self.from_date = QDateEdit()
        self.from_date.setDisplayFormat('yyyy-MM-dd')
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date = QDateEdit()
        self.to_date.setDisplayFormat('yyyy-MM-dd')
        self.to_date.setDate(QDate.currentDate())
        hdr_layout.addWidget(QLabel('From:'))
        hdr_layout.addWidget(self.from_date)
        hdr_layout.addWidget(QLabel('To:'))
        hdr_layout.addWidget(self.to_date)
        btn_refresh = QPushButton('Refresh')
        btn_refresh.clicked.connect(self.load_transactions)
        hdr_layout.addWidget(btn_refresh)
        layout.addLayout(hdr_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['Date','Reference','Description','Debit','Credit','Running Balance','Source'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        new_btn = QPushButton('New Transaction')
        new_btn.clicked.connect(self.create_transaction)
        reconcile_btn = QPushButton('Reconcile')
        reconcile_btn.clicked.connect(self.open_reconcile)
        btn_layout.addWidget(new_btn)
        btn_layout.addWidget(reconcile_btn)
        layout.addLayout(btn_layout)

    def load_transactions(self):
        acc_id = self.account_id
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT code, name FROM accounts WHERE id=?', (acc_id,))
                acc = cur.fetchone()
                if acc:
                    self.account_label.setText(f"{acc['code']} - {acc['name']}")
                    acc_name = acc['name']
                else:
                    self.account_label.setText('Unknown')
                    acc_name = ''

                from_date = self.from_date.date().toString('yyyy-MM-dd')
                to_date = self.to_date.date().toString('yyyy-MM-dd')

                # Gather journal_lines for this account
                cur.execute(
                    "SELECT jl.id as id, je.date as date, je.reference as reference, je.memo as description, jl.debit, jl.credit, 'Journal' as source "
                    "FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_id "
                    "WHERE jl.account_id = ? AND je.date BETWEEN ? AND ?",
                    (acc_id, from_date, to_date)
                )
                journal_rows = [dict(r) for r in cur.fetchall()]

                # Gather cash_book lines where account text matches the account name
                cur.execute(
                    "SELECT id, date, reference, narration as description, debit, credit, 'Cashbook' as source FROM cash_book "
                    "WHERE account = ? AND date BETWEEN ? AND ?",
                    (acc_name, from_date, to_date)
                )
                cb_rows = [dict(r) for r in cur.fetchall()]

                # unify and sort
                lines = journal_rows + cb_rows
        except Exception as e:
            print('[bank_register] load_transactions', e)
            lines = []

        # sort by date then id
        def parse_date(d):
            try:
                return datetime.fromisoformat(d)
            except Exception:
                return datetime.min
        lines.sort(key=lambda x: (parse_date(x.get('date')), x.get('id')))

        # compute running balance
        running = 0.0
        self.table.setRowCount(len(lines))
        for i, L in enumerate(lines):
            debit = float(L.get('debit') or 0)
            credit = float(L.get('credit') or 0)
            running += (debit - credit)
            self.table.setItem(i, 0, QTableWidgetItem(str(L.get('date') or '')))
            self.table.setItem(i, 1, QTableWidgetItem(str(L.get('reference') or '')))
            self.table.setItem(i, 2, QTableWidgetItem(str(L.get('description') or '')))
            self.table.setItem(i, 3, QTableWidgetItem(format_money(debit) if debit else ''))
            self.table.setItem(i, 4, QTableWidgetItem(format_money(credit) if credit else ''))
            self.table.setItem(i, 5, QTableWidgetItem(format_money(running)))
            self.table.setItem(i, 6, QTableWidgetItem(str(L.get('source') or '')))

    def create_transaction(self):
        dlg = OpeningBalanceDialog(account_id=self.account_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_transactions()

    def open_reconcile(self):
        dlg = BankReconciliationTab(self.account_id, parent=self)
        dlg.show()


# ---------- Reconciliation Tab (Window) ----------
class BankReconciliationTab(QWidget):
    def __init__(self, account_id: int, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.setWindowTitle('Bank Reconciliation')
        self.resize(1000, 700)
        self.init_ui()
        self.load_state()

    def init_ui(self):
        layout = QVBoxLayout(self)
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('Account:'))
        self.account_label = QLabel('')
        hdr.addWidget(self.account_label)
        hdr.addStretch()
        self.from_date = QDateEdit()
        self.from_date.setDisplayFormat('yyyy-MM-dd')
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date = QDateEdit()
        self.to_date.setDisplayFormat('yyyy-MM-dd')
        self.to_date.setDate(QDate.currentDate())
        hdr.addWidget(QLabel('From:'))
        hdr.addWidget(self.from_date)
        hdr.addWidget(QLabel('To:'))
        hdr.addWidget(self.to_date)
        load_btn = QPushButton('Load')
        load_btn.clicked.connect(self.load_state)
        hdr.addWidget(load_btn)
        layout.addLayout(hdr)

        # Split: left = statement lines, right = cashbook matches
        body = QHBoxLayout()
        # statement table
        self.stmt_table = QTableWidget()
        self.stmt_table.setColumnCount(5)
        self.stmt_table.setHorizontalHeaderLabels(['Date','Description','Amount','Matched','Stmt ID'])
        self.stmt_table.setColumnHidden(4, True)
        body.addWidget(self.stmt_table, 1)

        # cashbook table
        self.cb_table = QTableWidget()
        self.cb_table.setColumnCount(6)
        self.cb_table.setHorizontalHeaderLabels(['Date','Reference','Description','Debit','Credit','CB ID'])
        self.cb_table.setColumnHidden(5, True)
        body.addWidget(self.cb_table, 1)

        layout.addLayout(body)

        # actions
        actions = QHBoxLayout()
        import_btn = QPushButton('Import Statement (CSV)')
        import_btn.clicked.connect(self.import_statement)
        auto_match_btn = QPushButton('Auto Match')
        auto_match_btn.clicked.connect(self.auto_match)
        confirm_btn = QPushButton('Confirm Matches')
        confirm_btn.clicked.connect(self.confirm_matches)
        actions.addWidget(import_btn)
        actions.addWidget(auto_match_btn)
        actions.addWidget(confirm_btn)
        layout.addLayout(actions)

    def load_state(self):
        # load account label
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT code, name FROM accounts WHERE id=?', (self.account_id,))
                acc = cur.fetchone()
                if acc:
                    self.account_label.setText(f"{acc['code']} - {acc['name']}")
                    acc_name = acc['name']
                else:
                    acc_name = ''

                # load bank_statement_lines for this account and date range
                from_date = self.from_date.date().toString('yyyy-MM-dd')
                to_date = self.to_date.date().toString('yyyy-MM-dd')
                cur.execute(
                    "SELECT id, tx_date, description, amount, matched_entry_id FROM bank_statement_lines "
                    "WHERE tx_date BETWEEN ? AND ?",
                    (from_date, to_date)
                )
                stmt_rows = [dict(r) for r in cur.fetchall()]

                # load cash_book entries for this account name
                cur.execute(
                    "SELECT id, date, reference, narration, debit, credit FROM cash_book WHERE account = ? AND date BETWEEN ? AND ?",
                    (acc_name, from_date, to_date)
                )
                cb_rows = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print('[bank_recon] load_state', e)
            stmt_rows = []
            cb_rows = []

        # populate tables
        self.stmt_table.setRowCount(len(stmt_rows))
        for i, s in enumerate(stmt_rows):
            self.stmt_table.setItem(i, 0, QTableWidgetItem(str(s.get('tx_date') or '')))
            self.stmt_table.setItem(i, 1, QTableWidgetItem(str(s.get('description') or '')))
            self.stmt_table.setItem(i, 2, QTableWidgetItem(format_money(s.get('amount') or 0)))
            matched = 'Yes' if s.get('matched_entry_id') else 'No'
            self.stmt_table.setItem(i, 3, QTableWidgetItem(matched))
            self.stmt_table.setItem(i, 4, QTableWidgetItem(str(s.get('id'))))

        self.cb_table.setRowCount(len(cb_rows))
        for i, c in enumerate(cb_rows):
            self.cb_table.setItem(i, 0, QTableWidgetItem(str(c.get('date') or '')))
            self.cb_table.setItem(i, 1, QTableWidgetItem(str(c.get('reference') or '')))
            self.cb_table.setItem(i, 2, QTableWidgetItem(str(c.get('narration') or '')))
            self.cb_table.setItem(i, 3, QTableWidgetItem(format_money(c.get('debit') or 0)))
            self.cb_table.setItem(i, 4, QTableWidgetItem(format_money(c.get('credit') or 0)))
            self.cb_table.setItem(i, 5, QTableWidgetItem(str(c.get('id'))))

    def import_statement(self):
        fn, _ = QFileDialog.getOpenFileName(self, 'Import CSV statement', os.getcwd(), 'CSV Files (*.csv)')
        if not fn:
            return
        engine = BankImportEngine()
        count, preview = engine.import_csv_to_raw(fn)
        QMessageBox.information(self, 'Imported', f'Imported {count} rows to bank_statement_lines (raw).')
        self.load_state()

    def auto_match(self):
        # naive matching: for each statement line find cash_book line with same amount and date +/-2 days and payee similarity
        stmt_matches = []
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT id, tx_date, amount, description FROM bank_statement_lines WHERE matched_entry_id IS NULL')
                stmts = [dict(r) for r in cur.fetchall()]
                cur.execute('SELECT id, date, reference, narration, debit, credit FROM cash_book WHERE reconciled = 0')
                cbs = [dict(r) for r in cur.fetchall()]

                for s in stmts:
                    s_amt = float(s['amount'] or 0)
                    s_date = s['tx_date']
                    best = None
                    best_score = 0
                    for c in cbs:
                        c_amt = float(c.get('debit') or 0) - float(c.get('credit') or 0)
                        if abs(c_amt - s_amt) > 0.01:
                            continue
                        # date window check
                        try:
                            sd = datetime.fromisoformat(s_date).date()
                            cd = datetime.fromisoformat(c.get('date')).date()
                            days = abs((sd - cd).days)
                        except Exception:
                            days = 999
                        if days > 3:
                            continue
                        # payee similarity
                        score = similarity(s.get('description') or '', c.get('narration') or '')
                        if score > best_score:
                            best_score = score
                            best = c
                    if best and best_score > 0.4:
                        stmt_matches.append((s['id'], best['id'], best_score))

                # store matches temporarily in memory (not committing) — show to user
                if not stmt_matches:
                    QMessageBox.information(self, 'Auto Match', 'No matches found')
                    return
                # present a simple confirmation list
                msg = '\n'.join([f"Stmt {a} -> CB {b} (score {c:.2f})" for a,b,c in stmt_matches])
                ok = QMessageBox.question(self, 'Confirm Auto Match', f'Apply these matches?\n\n{msg}')
                if ok == QMessageBox.StandardButton.Yes:
                    for sid, cid, score in stmt_matches:
                        cur.execute('UPDATE bank_statement_lines SET matched_entry_id = ? WHERE id = ?', (cid, sid))
                        cur.execute('UPDATE cash_book SET reconciled = 1 WHERE id = ?', (cid,))
                        cur.execute('INSERT INTO reconciliation_matches (reconciliation_id, statement_line_id, cashbook_entry_id, match_score) VALUES (?, ?, ?, ?)', (None, sid, cid, score))
                    conn.commit()
                    QMessageBox.information(self, 'Matches applied', f'Applied {len(stmt_matches)} matches')
                    self.load_state()
        except Exception as e:
            print('[bank_recon] auto_match error', e)
            QMessageBox.critical(self, 'Error', str(e))

    def confirm_matches(self):
        # finalize matches already assigned
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT id, matched_entry_id FROM bank_statement_lines WHERE matched_entry_id IS NOT NULL')
                rows = [dict(r) for r in cur.fetchall()]
                if not rows:
                    QMessageBox.information(self, 'No matches', 'No matches to confirm')
                    return
                for r in rows:
                    stmt_id = r['id']
                    cb_id = r['matched_entry_id']
                    cur.execute('UPDATE bank_statement_lines SET matched_entry_id = ? WHERE id = ?', (cb_id, stmt_id))
                    cur.execute('UPDATE cash_book SET reconciled = 1 WHERE id = ?', (cb_id,))
                    cur.execute('INSERT INTO reconciliation_matches (reconciliation_id, statement_line_id, cashbook_entry_id, match_score) VALUES (?, ?, ?, ?)', (None, stmt_id, cb_id, 1.0))
                conn.commit()
                QMessageBox.information(self, 'Confirmed', f'Confirmed {len(rows)} matches')
                self.load_state()
        except Exception as e:
            print('[bank_recon] confirm_matches', e)
            QMessageBox.critical(self, 'Error', str(e))


# ---------- Account Manager Dialog (Add/Edit/Delete) ----------
class AccountManagerDialog(QDialog):
    def __init__(self, account_id: int = None, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.init_ui()
        if account_id:
            self.load_account(account_id)

    def init_ui(self):
        self.setWindowTitle('Account Manager')
        layout = QFormLayout(self)
        self.code = QLineEdit()
        self.name = QLineEdit()
        layout.addRow('Code:', self.code)
        layout.addRow('Name:', self.name)
        btn_save = QPushButton('Save')
        btn_save.clicked.connect(self.save)
        btn_delete = QPushButton('Delete')
        btn_delete.clicked.connect(self.delete)
        layout.addRow(btn_save, btn_delete)

    def load_account(self, account_id):
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT code, name FROM accounts WHERE id=?', (account_id,))
                r = cur.fetchone()
                if r:
                    self.code.setText(str(r['code']))
                    self.name.setText(str(r['name']))
        except Exception as e:
            print('[account_mgr] load', e)

    def save(self):
        code = self.code.text().strip()
        name = self.name.text().strip()
        if not code or not name:
            QMessageBox.warning(self, 'Validation', 'Code and name required')
            return
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                if self.account_id:
                    cur.execute('UPDATE accounts SET code=?, name=? WHERE id=?', (code, name, self.account_id))
                else:
                    cur.execute('INSERT INTO accounts(code, name, type) VALUES (?, ?, "Asset")', (code, name))
                conn.commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, 'Save error', str(e))

    def delete(self):
        if not self.account_id:
            QMessageBox.information(self, 'Delete', 'Account not yet created')
            return
        ok = QMessageBox.question(self, 'Delete', 'Delete this account? This will not remove historic entries.')
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM accounts WHERE id=?', (self.account_id,))
                conn.commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, 'Delete error', str(e))


# ---------- Opening Balance Dialog (posts journal + cashbook) ----------
class OpeningBalanceDialog(QDialog):
    def __init__(self, account_id: int, parent=None):
        super().__init__(parent)
        self.account_id = account_id
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Opening Balance / New Transaction')
        layout = QFormLayout(self)
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat('yyyy-MM-dd')
        self.date_edit.setDate(QDate.currentDate())
        self.amount_edit = QLineEdit()
        self.ref_edit = QLineEdit()
        self.desc_edit = QLineEdit()
        layout.addRow('Date:', self.date_edit)
        layout.addRow('Amount:', self.amount_edit)
        layout.addRow('Reference:', self.ref_edit)
        layout.addRow('Description:', self.desc_edit)
        btn_save = QPushButton('Save')
        btn_save.clicked.connect(self.save)
        layout.addRow(btn_save)

    def save(self):
        date = self.date_edit.date().toString('yyyy-MM-dd')
        try:
            amt = float(self.amount_edit.text())
        except Exception:
            QMessageBox.warning(self, 'Validation', 'Invalid amount')
            return
        ref = self.ref_edit.text().strip()
        desc = self.desc_edit.text().strip()

        try:
            with db_connection() as conn:
                cur = conn.cursor()
                # Insert into journal_entries and journal_lines (double entry):
                # Debit the bank account, Credit Opening Balances (equity) 3000
                cur.execute('INSERT INTO journal_entries(date, reference, memo) VALUES (?, ?, ?)', (date, ref, desc))
                jid = cur.lastrowid
                # bank debit
                cur.execute('INSERT INTO journal_lines(journal_id, account_id, debit, credit) VALUES (?, ?, ?, ?)', (jid, self.account_id, amt, 0))
                # credit to owner's equity (assume account code 3000 exists)
                cur.execute('SELECT id FROM accounts WHERE code = "3000" LIMIT 1')
                eq = cur.fetchone()
                if not eq:
                    cur.execute('INSERT INTO accounts(code, name, type) VALUES ("3000", "Owner\'s Equity", "Equity")')
                    cur.execute('SELECT id FROM accounts WHERE code = "3000" LIMIT 1')
                    eq = cur.fetchone()
                cur.execute('INSERT INTO journal_lines(journal_id, account_id, debit, credit) VALUES (?, ?, ?, ?)', (jid, eq['id'], 0, amt))
                # Also insert a cash_book entry for traceability
                cur.execute('INSERT INTO cash_book(date, account, narration, reference, debit, credit) VALUES (?, ?, ?, ?, ?, ?)', (date, self._account_name(conn), desc, ref, amt, 0))
                conn.commit()
            QMessageBox.information(self, 'Saved', 'Opening balance recorded')
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    def _account_name(self, conn):
        cur = conn.cursor()
        cur.execute('SELECT name FROM accounts WHERE id=?', (self.account_id,))
        r = cur.fetchone()
        return r['name'] if r else ''
