# cash_book_tab.py
# Cashbook / Banking Tab for NexLedger Pro — Extended
# Gold & Emerald themed, includes:
#  - Bank Accounts (cards)
#  - Transactions / Register (running balance + footer)
#  - Import (CSV / basic OFX) with preview and rules engine
#  - Reconciliation screen (statement import + matching + undo)
#  - Add/Edit/Delete bank accounts + opening balance
#  - QuickBooks-style import workflow (imports -> transactions -> match/reconcile)
#  - Automation rules (simple "if contains -> category/action")
#  - Simple audit & undo stack for import/match actions

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QFileDialog, QMessageBox, QDialog, QFormLayout, QLineEdit,
    QSpinBox, QComboBox, QDateEdit, QTabWidget, QTextEdit, QSplitter, QInputDialog
)
from PyQt6.QtCore import Qt, QDate
from shared.db import get_conn, get_conn_safe, get_current_company, log_audit
from shared.theme import get_widget_style, EMERALD, GOLD
from datetime import datetime
import csv
import io
import sqlite3
import xml.etree.ElementTree as ET

# ----------------------- Helpers & Migration -----------------------

def ensure_bank_tables(conn):
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            bank TEXT,
            account_no TEXT,
            branch_code TEXT,
            opening_balance REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bank_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            imported_on TEXT DEFAULT (datetime('now')),
            source TEXT,
            raw TEXT,
            status TEXT DEFAULT 'new'
        );

        CREATE TABLE IF NOT EXISTS bank_feed_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER,
            tx_date TEXT,
            description TEXT,
            amount REAL,
            fitid TEXT,
            matched_entry_id INTEGER,
            cleared INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bank_import_staging (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            tx_date TEXT,
            description TEXT,
            amount REAL,
            fitid TEXT
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

        CREATE TABLE IF NOT EXISTS reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashbook_name TEXT,
            statement_from TEXT,
            statement_to TEXT,
            bank_balance REAL,
            reconciled_on TEXT DEFAULT (datetime('now')),
            notes TEXT
        );

        -- Automation rules
        CREATE TABLE IF NOT EXISTS bank_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            action TEXT NOT NULL, -- e.g. 'categorize:Bank Charges' or 'split:...'
            enabled INTEGER DEFAULT 1
        );

        -- Simple undo stack for bank ops
        CREATE TABLE IF NOT EXISTS bank_undo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            payload TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    ''')
    conn.commit()

# ----------------------- Small utilities -----------------------

def apply_rules_to_description(conn, description):
    # returns action string or None
    cur = conn.cursor()
    cur.execute("SELECT id, pattern, action FROM bank_rules WHERE enabled=1 ORDER BY id ASC")
    for rid, pattern, action in cur.fetchall():
        try:
            if pattern.lower() in (description or '').lower():
                return action
        except Exception:
            continue
    return None

def push_undo(conn, action, payload):
    cur = conn.cursor()
    cur.execute('INSERT INTO bank_undo (action, payload) VALUES (?,?)', (action, payload))
    conn.commit()

def pop_undo(conn):
    cur = conn.cursor()
    row = cur.execute('SELECT id, action, payload FROM bank_undo ORDER BY id DESC LIMIT 1').fetchone()
    if not row:
        return None
    cur.execute('DELETE FROM bank_undo WHERE id=?', (row[0],))
    conn.commit()
    return row[1], row[2]

# ----------------------- OFX basic parser -----------------------

def parse_basic_ofx(xml_text):
    """Very small OFX/SGML-ish parser that handles simple OFX XML output.
    It attempts to find <STMTTRN> entries.
    Returns list of dicts: {date, description, amount, fitid}
    """
    try:
        # OFX is sometimes SGML — try to find XML-like tags
        root = ET.fromstring(xml_text)
    except Exception:
        # try to wrap/cleanup
        try:
            cleaned = xml_text.replace('<', '&lt;')
            root = ET.fromstring('<root></root>')
            return []
        except Exception:
            return []
    out = []
    for stmt in root.findall('.//STMTTRN'):
        data = {'date': None, 'description': None, 'amount': None, 'fitid': None}
        for ch in stmt:
            tag = ch.tag.upper()
            text = ch.text.strip() if ch.text else ''
            if tag.endswith('DTPOSTED') or tag == 'DTPOSTED':
                data['date'] = text[:10]
            elif tag.endswith('TRNAMT') or tag == 'TRNAMT':
                try:
                    data['amount'] = float(text)
                except:
                    data['amount'] = 0.0
            elif tag.endswith('FITID') or tag == 'FITID':
                data['fitid'] = text
            elif tag.endswith('NAME') or tag == 'NAME' or tag.endswith('MEMO'):
                data['description'] = text
        out.append(data)
    return out

# ----------------------- Main Tab Widget -----------------------
class CashBookTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(get_widget_style())
        self.parent = parent
        self.build_ui()
        try:
            if get_current_company():
                with get_conn() as conn:
                    ensure_bank_tables(conn)
            self.refresh_all()
        except Exception as e:
            print('CashBook init error:', e)

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12,12,12,12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(QLabel('<h2>Cashbook & Banking</h2>'))
        header.addStretch()
        btn_add_account = QPushButton('Add Bank Account')
        btn_add_account.clicked.connect(self.add_bank_account)
        header.addWidget(btn_add_account)
        btn_import = QPushButton('Import Bank Statement')
        #btn_import.clicked.connect(self.import_bank_statement)
        header.addWidget(btn_import)
        btn_rules = QPushButton('Rules')
        btn_rules.clicked.connect(self.open_rules_manager)
        header.addWidget(btn_rules)
        btn_undo = QPushButton('Undo Last')
        btn_undo.clicked.connect(self.undo_last)
        header.addWidget(btn_undo)
        outer.addLayout(header)

        # Splitter: left = accounts/cards, right = tabbed area
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: account cards
        left = QFrame(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(8,8,8,8)
        left_layout.addWidget(QLabel('<b>Bank Accounts</b>'))
        self.accounts_container = QVBoxLayout()
        left_layout.addLayout(self.accounts_container)
        left_layout.addStretch()
        splitter.addWidget(left)

        # Right: tabs
        right = QFrame(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(8,8,8,8)
        self.tabs = QTabWidget()
        self.tab_transactions = QWidget(); self.tab_reconcile = QWidget(); self.tab_import = QWidget(); self.tab_manage = QWidget()
        self.tabs.addTab(self.tab_transactions, 'Transactions')
        self.tabs.addTab(self.tab_import, 'Import')
        self.tabs.addTab(self.tab_reconcile, 'Reconcile')
        self.tabs.addTab(self.tab_manage, 'Manage Accounts')
        right_layout.addWidget(self.tabs)
        splitter.addWidget(right)

        outer.addWidget(splitter)

        # Build tab contents
        self.build_transactions_tab()
        self.build_import_tab()
        self.build_reconcile_tab()
        self.build_manage_tab()

    # ---------------- Accounts list/cards ----------------
    def refresh_accounts_cards(self):
        def clear_layout(l):
            while l.count():
                it = l.takeAt(0)
                w = it.widget()
                if w: w.deleteLater()
        clear_layout(self.accounts_container)

        conn = get_conn_safe()
        if not conn:
            self.accounts_container.addWidget(QLabel('No company / DB'))
            return
        cur = conn.cursor()
        cur.execute('SELECT id, name, bank, account_no, opening_balance FROM bank_accounts')
        rows = cur.fetchall()
        for r in rows:
            aid, name, bank, accno, opening = r
            card = QFrame(); card.setFrameShape(QFrame.Shape.StyledPanel); card.setStyleSheet(f'background:#f8f8f8; border-left:4px solid {EMERALD}; padding:8px;')
            layout = QHBoxLayout(card)
            info = QLabel(f"<b>{name}</b><br><small>{bank} • {accno or ''}</small>")
            layout.addWidget(info)
            layout.addStretch()
            balance = self._get_running_balance_for_account(aid)
            layout.addWidget(QLabel(f"<b>R {balance:,.2f}</b>"))
            btn_view = QPushButton('View'); btn_view.clicked.connect(lambda _, a=aid: self.open_ledger(a)); layout.addWidget(btn_view)
            btn_rec = QPushButton('Reconcile'); btn_rec.clicked.connect(lambda _, a=aid: self.open_reconcile_dialog(a)); layout.addWidget(btn_rec)
            self.accounts_container.addWidget(card)
        conn.close()

    def _get_running_balance_for_account(self, account_id):
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute('SELECT opening_balance FROM bank_accounts WHERE id=?', (account_id,))
                row = cur.fetchone(); opening = row[0] if row else 0
                cur.execute('SELECT IFNULL(SUM(debit),0)-IFNULL(SUM(credit),0) FROM cash_book WHERE account=?', (str(account_id),))
                delta = cur.fetchone()[0] or 0
                return opening + delta
        except Exception:
            return 0.0

    # ---------------- Transactions tab ----------------
    def build_transactions_tab(self):
        layout = QVBoxLayout(self.tab_transactions)
        layout.setContentsMargins(6,6,6,6)
        hl = QHBoxLayout(); hl.addWidget(QLabel('Account:'))
        self.tx_account_combo = QComboBox(); hl.addWidget(self.tx_account_combo)
        self.tx_account_combo.currentIndexChanged.connect(self.load_transactions_for_selected_account)
        hl.addStretch()
        layout.addLayout(hl)

        self.tbl_transactions = QTableWidget(); self.tbl_transactions.setColumnCount(9)
        self.tbl_transactions.setHorizontalHeaderLabels(['Date','Description','Ref','Debit','Credit','Balance','Reconciled','Actions','Run Bal'])
        self.tbl_transactions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tbl_transactions)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        btn_add = QPushButton('Add Transaction'); btn_add.clicked.connect(self.add_manual_transaction); btn_row.addWidget(btn_add)
        btn_match = QPushButton('Auto-match'); btn_match.clicked.connect(self.auto_match_transactions); btn_row.addWidget(btn_match)
        btn_export = QPushButton('Export Register CSV'); btn_export.clicked.connect(self.export_register_csv); btn_row.addWidget(btn_export)
        layout.addLayout(btn_row)

        self.load_accounts_in_combo()

    def export_register_csv(self):
        aid = self.tx_account_combo.currentData()
        if not aid: QMessageBox.warning(self,'Account','Select account'); return
        path, _ = QFileDialog.getSaveFileName(self,'Export Register', f'register_{aid}.csv','CSV (*.csv)')
        if not path: return
        try:
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT date,narration,reference,debit,credit,reconciled FROM cash_book WHERE account=? ORDER BY date ASC', (str(aid),))
                rows = cur.fetchall()
            with open(path,'w',newline='',encoding='utf-8') as f:
                w = csv.writer(f); w.writerow(['Date','Narration','Reference','Debit','Credit','Reconciled'])
                for r in rows: w.writerow([r[0], r[1], r[2], r[3], r[4], r[5]])
            QMessageBox.information(self,'Export','Register exported')
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def load_accounts_in_combo(self):
        self.tx_account_combo.clear()
        conn = get_conn_safe()
        if not conn:
            return
        cur = conn.cursor(); cur.execute('SELECT id, name FROM bank_accounts'); rows = cur.fetchall();
        for r in rows: self.tx_account_combo.addItem(f"{r[1]} (#{r[0]})", r[0])

    def load_transactions_for_selected_account(self):
        aid = self.tx_account_combo.currentData()
        if not aid:
            self.tbl_transactions.setRowCount(0); return
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute('SELECT id,date,narration,reference,debit,credit,reconciled FROM cash_book WHERE account=? ORDER BY date ASC', (str(aid),))
                rows = cur.fetchall()
            balance = 0.0
            run_bal = 0.0
            self.tbl_transactions.setRowCount(len(rows))
            for r,row in enumerate(rows):
                idd, date, narr, ref, debit, credit, rec = row
                d = debit or 0; c = credit or 0
                run_bal += (d - c)
                self.tbl_transactions.setItem(r,0,QTableWidgetItem(str(date)))
                self.tbl_transactions.setItem(r,1,QTableWidgetItem(str(narr)))
                self.tbl_transactions.setItem(r,2,QTableWidgetItem(str(ref or '')))
                self.tbl_transactions.setItem(r,3,QTableWidgetItem(f"{d:.2f}" if d else ''))
                self.tbl_transactions.setItem(r,4,QTableWidgetItem(f"{c:.2f}" if c else ''))
                self.tbl_transactions.setItem(r,5,QTableWidgetItem(f"{run_bal:.2f}"))
                self.tbl_transactions.setItem(r,6,QTableWidgetItem('Yes' if rec else 'No'))
                act = QPushButton('Edit'); act.clicked.connect(lambda _, cid=idd: self.edit_cashbook_entry(cid)); self.tbl_transactions.setCellWidget(r,7,act)
                self.tbl_transactions.setItem(r,8,QTableWidgetItem(f"{run_bal:.2f}"))
            # footer: compute closing balance including opening
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT opening_balance FROM bank_accounts WHERE id=?', (aid,)); ob = cur.fetchone()[0] or 0
            closing = ob + run_bal
            # show footer as a last-row label
            footer_row = self.tbl_transactions.rowCount()
            self.tbl_transactions.insertRow(footer_row)
            self.tbl_transactions.setSpan(footer_row,0,1,6)
            item = QTableWidgetItem(f'Opening balance: R {ob:,.2f} — Closing balance: R {closing:,.2f}')
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tbl_transactions.setItem(footer_row,0,item)
        except Exception as e:
            print('load tx err', e)

    def add_manual_transaction(self):
        aid = self.tx_account_combo.currentData()
        if not aid:
            QMessageBox.warning(self,'Select Account','Choose a bank account first'); return
        dlg = QDialog(self); dlg.setWindowTitle('Add Transaction'); form = QFormLayout(dlg)
        date = QDateEdit(); date.setCalendarPopup(True); date.setDate(QDate.currentDate())
        narr = QLineEdit(); ref = QLineEdit(); debit = QLineEdit(); credit = QLineEdit()
        form.addRow('Date', date); form.addRow('Narration', narr); form.addRow('Reference', ref); form.addRow('Debit', debit); form.addRow('Credit', credit)
        btns = QPushButton('Save'); btns.clicked.connect(lambda: self._save_manual_tx(dlg, aid, date, narr, ref, debit, credit)); form.addRow(btns)
        dlg.exec()

    def _save_manual_tx(self, dlg, account_id, date_widget, narr, ref, debit_w, credit_w):
        try:
            dt = date_widget.date().toString('yyyy-MM-dd')
            d = float(debit_w.text() or 0)
            c = float(credit_w.text() or 0)
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute('INSERT INTO cash_book (date, account, narration, reference, debit, credit, reconciled) VALUES (?,?,?,?,?,?,0)', (dt, str(account_id), narr.text().strip(), ref.text().strip(), d, c))
                trans_id = cur.lastrowid
                push_undo(conn, 'insert_cashbook', str(trans_id))
                conn.commit()
            dlg.accept(); self.load_transactions_for_selected_account(); log_audit('Manual transaction added')
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def edit_cashbook_entry(self, cid):
        try:
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT id,date,account,narration,reference,debit,credit FROM cash_book WHERE id=?', (cid,)); row = cur.fetchone()
            if not row: return
            dlg = QDialog(self); dlg.setWindowTitle('Edit Entry'); form = QFormLayout(dlg)
            date = QDateEdit(); date.setCalendarPopup(True); date.setDate(QDate.fromString(row[1],'yyyy-MM-dd'))
            narr = QLineEdit(row[3]); ref = QLineEdit(row[4]); debit = QLineEdit(str(row[5] or '0')); credit = QLineEdit(str(row[6] or '0'))
            form.addRow('Date', date); form.addRow('Narration', narr); form.addRow('Reference', ref); form.addRow('Debit', debit); form.addRow('Credit', credit)
            btns = QPushButton('Save'); btns.clicked.connect(lambda: self._save_edit_entry(dlg, cid, date, narr, ref, debit, credit)); form.addRow(btns); dlg.exec()
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def _save_edit_entry(self, dlg, cid, date_w, narr, ref, debit_w, credit_w):
        try:
            dt = date_w.date().toString('yyyy-MM-dd')
            d = float(debit_w.text() or 0); c = float(credit_w.text() or 0)
            with get_conn() as conn:
                cur = conn.cursor();
                # save previous snapshot to undo
                cur.execute('SELECT date,narration,reference,debit,credit FROM cash_book WHERE id=?', (cid,)); prev = cur.fetchone()
                push_undo(conn, 'edit_cashbook', f"{cid}|||{prev[0]}|||{prev[1]}|||{prev[2]}|||{prev[3]}|||{prev[4]}")
                cur.execute('UPDATE cash_book SET date=?, narration=?, reference=?, debit=?, credit=? WHERE id=?', (dt, narr.text().strip(), ref.text().strip(), d, c, cid)); conn.commit()
            dlg.accept(); self.load_transactions_for_selected_account(); log_audit('Cashbook entry edited')
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def undo_last(self):
        try:
            with get_conn() as conn:
                rec = pop_undo(conn)
                if not rec:
                    QMessageBox.information(self,'Undo','Nothing to undo')
                    return
                action, payload = rec
                if action == 'insert_cashbook':
                    cid = int(payload)
                    cur = conn.cursor(); cur.execute('DELETE FROM cash_book WHERE id=?', (cid,)); conn.commit(); QMessageBox.information(self,'Undo','Last inserted cashbook entry removed')
                elif action == 'edit_cashbook':
                    parts = payload.split('|||')
                    cid = int(parts[0]); dt, narr, ref, d, c = parts[1], parts[2], parts[3], parts[4], parts[5]
                    cur = conn.cursor(); cur.execute('UPDATE cash_book SET date=?, narration=?, reference=?, debit=?, credit=? WHERE id=?', (dt, narr, ref, d, c, cid)); conn.commit(); QMessageBox.information(self,'Undo','Last edit reverted')
                else:
                    QMessageBox.information(self,'Undo','Unknown undo action')
            self.refresh_all()
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def auto_match_transactions(self):
        try:
            aid = self.tx_account_combo.currentData();
            if not aid: QMessageBox.warning(self,'Account','Select an account'); return
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute('SELECT id, amount, tx_date, description FROM bank_feed_lines WHERE matched_entry_id IS NULL')
                feeds = cur.fetchall()
                matched = 0
                for f in feeds:
                    fid, amt, txd, desc = f
                    # try exact match
                    cur.execute('SELECT id FROM cash_book WHERE account=? AND (ABS(debit - ?)<0.01 OR ABS(credit - ?)<0.01) ORDER BY date ASC LIMIT 1', (str(aid), amt, abs(amt)))
                    match = cur.fetchone()
                    if match:
                        mid = match[0]
                        cur.execute('UPDATE bank_feed_lines SET matched_entry_id=? WHERE id=?', (mid, fid))
                        matched += 1
                conn.commit()
            QMessageBox.information(self,'Auto-match',f'Auto-matching completed — matched {matched} lines')
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    # ---------------- Import Tab ----------------
    def build_import_tab(self):
        layout = QVBoxLayout(self.tab_import); layout.setContentsMargins(6,6,6,6)
        hl = QHBoxLayout(); hl.addWidget(QLabel('Import to account:'))
        self.import_account = QComboBox(); hl.addWidget(self.import_account)
        btn_load = QPushButton('Load CSV'); btn_load.clicked.connect(self.load_csv_for_import); hl.addWidget(btn_load)
        btn_ofx = QPushButton('Load OFX'); btn_ofx.clicked.connect(self.load_ofx_for_import); hl.addWidget(btn_ofx)
        layout.addLayout(hl)

        self.import_preview = QTableWidget(); self.import_preview.setColumnCount(5); self.import_preview.setHorizontalHeaderLabels(['Date','Description','Amount','FITID','Rule'])
        self.import_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.import_preview)

        btns = QHBoxLayout(); btns.addStretch(); btn_post = QPushButton('Post to Transactions'); btn_post.clicked.connect(self.post_import_to_transactions); btns.addWidget(btn_post); layout.addLayout(btns)
        self.load_accounts_in_import()

    def load_accounts_in_import(self):
        self.import_account.clear(); conn = get_conn_safe();
        if not conn: return
        cur = conn.cursor(); cur.execute('SELECT id, name FROM bank_accounts'); rows = cur.fetchall()
        for r in rows: self.import_account.addItem(f"{r[1]} (#{r[0]})", r[0])

    def load_csv_for_import(self):
        path, _ = QFileDialog.getOpenFileName(self,'Load CSV','', 'CSV Files (*.csv)')
        if not path: return
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.import_preview.setRowCount(len(rows))
            for r,row in enumerate(rows):
                date = row.get('Date') or row.get('date') or row.get('Transaction Date') or ''
                desc = row.get('Description') or row.get('Payee') or ''
                amt = row.get('Amount') or row.get('amount') or '0'
                fitid = row.get('FITID') or row.get('fitid') or ''
                # apply rules
                action = None
                with get_conn() as conn:
                    action = apply_rules_to_description(conn, desc)
                self.import_preview.setItem(r,0,QTableWidgetItem(str(date)))
                self.import_preview.setItem(r,1,QTableWidgetItem(str(desc)))
                self.import_preview.setItem(r,2,QTableWidgetItem(str(amt)))
                self.import_preview.setItem(r,3,QTableWidgetItem(str(fitid)))
                self.import_preview.setItem(r,4,QTableWidgetItem(str(action or '')))
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def load_ofx_for_import(self):
        path, _ = QFileDialog.getOpenFileName(self,'Load OFX','', 'OFX Files (*.ofx *.xml)')
        if not path: return
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                txt = f.read()
            parsed = parse_basic_ofx(txt)
            self.import_preview.setRowCount(len(parsed))
            for r,row in enumerate(parsed):
                d = row.get('date') or ''
                desc = row.get('description') or ''
                amt = row.get('amount') or 0
                fitid = row.get('fitid') or ''
                with get_conn() as conn:
                    action = apply_rules_to_description(conn, desc)
                self.import_preview.setItem(r,0,QTableWidgetItem(str(d)))
                self.import_preview.setItem(r,1,QTableWidgetItem(str(desc)))
                self.import_preview.setItem(r,2,QTableWidgetItem(str(amt)))
                self.import_preview.setItem(r,3,QTableWidgetItem(str(fitid)))
                self.import_preview.setItem(r,4,QTableWidgetItem(str(action or '')))
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def post_import_to_transactions(self):
        aid = self.import_account.currentData()
        if not aid: QMessageBox.warning(self,'Account','Select an account'); return
        rows = []
        for r in range(self.import_preview.rowCount()):
            date = self.import_preview.item(r,0).text() if self.import_preview.item(r,0) else ''
            desc = self.import_preview.item(r,1).text() if self.import_preview.item(r,1) else ''
            try:
                amt = float(self.import_preview.item(r,2).text() or 0)
            except:
                amt = 0.0
            fitid = self.import_preview.item(r,3).text() if self.import_preview.item(r,3) else ''
            rows.append((date, desc, amt, fitid))
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                for date,desc,amt,fitid in rows:
                    ttype = 'Income' if amt > 0 else 'Expense'
                    cur.execute('INSERT INTO transactions (date, description, amount, type) VALUES (?,?,?,?)', (date or datetime.now().strftime('%Y-%m-%d'), desc, abs(amt), ttype))
                    trans_id = cur.lastrowid
                    if amt > 0:
                        cur.execute('INSERT INTO cash_book (date, account, narration, reference, debit, credit, reconciled) VALUES (?,?,?,?,?,?,0)', (date or datetime.now().strftime('%Y-%m-%d'), str(aid), desc, fitid, amt, 0))
                    else:
                        cur.execute('INSERT INTO cash_book (date, account, narration, reference, debit, credit, reconciled) VALUES (?,?,?,?,?,?,0)', (date or datetime.now().strftime('%Y-%m-%d'), str(aid), desc, fitid, 0, abs(amt)))
                    cb_id = cur.lastrowid
                    # push undo for each inserted cash_book entry
                    push_undo(conn, 'insert_cashbook', str(cb_id))
                conn.commit()
            QMessageBox.information(self,'Imported','Imported to transactions and cashbook. Use Match / Reconcile to post.')
            log_audit('Bank statement imported')
            self.refresh_all()
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    # ---------------- Reconcile Tab ----------------
    def build_reconcile_tab(self):
        layout = QVBoxLayout(self.tab_reconcile)
        hl = QHBoxLayout(); hl.addWidget(QLabel('Account:'))
        self.rec_account = QComboBox(); hl.addWidget(self.rec_account)
        btn_load = QPushButton('Load Statement (CSV)'); btn_load.clicked.connect(self.load_statement_for_reconcile); hl.addWidget(btn_load)
        layout.addLayout(hl)

        self.rec_left = QTableWidget(); self.rec_left.setColumnCount(4); self.rec_left.setHorizontalHeaderLabels(['Date','Description','Amount','FITID'])
        self.rec_right = QTableWidget(); self.rec_right.setColumnCount(6); self.rec_right.setHorizontalHeaderLabels(['Date','Narration','Ref','Debit','Credit','Matched'])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_frame = QFrame(); lf_layout = QVBoxLayout(left_frame); lf_layout.addWidget(QLabel('Bank Statement'))
        lf_layout.addWidget(self.rec_left); splitter.addWidget(left_frame)
        right_frame = QFrame(); rf_layout = QVBoxLayout(right_frame); rf_layout.addWidget(QLabel('Ledger (Cash Book)'))
        rf_layout.addWidget(self.rec_right); splitter.addWidget(right_frame)
        layout.addWidget(splitter)

        btns = QHBoxLayout(); btns.addStretch(); match_btn = QPushButton('Match Selected'); match_btn.clicked.connect(self.match_selected_statement_lines); btns.addWidget(match_btn)
        undo_match_btn = QPushButton('Undo Last Match'); undo_match_btn.clicked.connect(self.undo_last_match); btns.addWidget(undo_match_btn)
        layout.addLayout(btns)
        self.load_accounts_in_reconcile()

    def load_accounts_in_reconcile(self):
        self.rec_account.clear(); conn = get_conn_safe();
        if not conn: return
        cur = conn.cursor(); cur.execute('SELECT id, name FROM bank_accounts'); rows = cur.fetchall()
        for r in rows: self.rec_account.addItem(f"{r[1]} (#{r[0]})", r[0])

    def load_statement_for_reconcile(self):
        path, _ = QFileDialog.getOpenFileName(self,'Load Bank Statement CSV','', 'CSV (*.csv)')
        if not path: return
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.rec_left.setRowCount(len(rows))
            for r,row in enumerate(rows):
                d = row.get('Date') or row.get('date')
                desc = row.get('Description') or row.get('Payee')
                amt = row.get('Amount') or row.get('amount')
                fitid = row.get('FITID') or ''
                self.rec_left.setItem(r,0,QTableWidgetItem(str(d)))
                self.rec_left.setItem(r,1,QTableWidgetItem(str(desc)))
                self.rec_left.setItem(r,2,QTableWidgetItem(str(amt)))
                self.rec_left.setItem(r,3,QTableWidgetItem(str(fitid)))
            aid = self.rec_account.currentData()
            if not aid: return
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT id,date,narration,reference,debit,credit,reconciled FROM cash_book WHERE account=? ORDER BY date ASC', (str(aid),))
                rows = cur.fetchall()
            self.rec_right.setRowCount(len(rows))
            for r,row in enumerate(rows):
                idd, date, narr, ref, debit, credit, rec = row
                self.rec_right.setItem(r,0,QTableWidgetItem(str(date)))
                self.rec_right.setItem(r,1,QTableWidgetItem(str(narr)))
                self.rec_right.setItem(r,2,QTableWidgetItem(str(ref)))
                self.rec_right.setItem(r,3,QTableWidgetItem(str(debit or '')))
                self.rec_right.setItem(r,4,QTableWidgetItem(str(credit or '')))
                self.rec_right.setItem(r,5,QTableWidgetItem('Yes' if rec else 'No'))
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def match_selected_statement_lines(self):
        left_sel = self.rec_left.currentRow(); right_sel = self.rec_right.currentRow()
        if left_sel == -1 or right_sel == -1: QMessageBox.warning(self,'Select','Select a statement row and a ledger row to match'); return
        fitid = self.rec_left.item(left_sel,3).text() if self.rec_left.item(left_sel,3) else ''
        amt_text = self.rec_left.item(left_sel,2).text() if self.rec_left.item(left_sel,2) else '0'
        try:
            amt = float(amt_text)
        except:
            amt = 0.0
        with get_conn() as conn:
            cur = conn.cursor();
            rdate = self.rec_right.item(right_sel,0).text()
            narr = self.rec_right.item(right_sel,1).text()
            cur.execute('SELECT id,debit,credit FROM cash_book WHERE date=? AND narration=? LIMIT 1', (rdate, narr))
            found = cur.fetchone()
            if not found:
                QMessageBox.warning(self,'Not found','Ledger line not found to match')
                return
            lid = found[0]; debit = found[1] or 0; credit = found[2] or 0
            cur.execute('INSERT INTO bank_statement_lines (fitid, tx_date, description, amount, source, matched_entry_id, cleared) VALUES (?,?,?,?,?,?,1)', (fitid, self.rec_left.item(left_sel,0).text(), self.rec_left.item(left_sel,1).text(), amt, 'csv', lid,))
            cur.execute('UPDATE cash_book SET reconciled=1 WHERE id=?', (lid,))
            conn.commit()
            # push undo for match
            push_undo(conn, 'match', f'{lid}|||{fitid}|||{amt}')
        QMessageBox.information(self,'Matched','Statement line matched to ledger entry')
        self.refresh_all()

    def undo_last_match(self):
        try:
            with get_conn() as conn:
                rec = pop_undo(conn)
                if not rec: QMessageBox.information(self,'Undo','Nothing to undo'); return
                action, payload = rec
                if action == 'match':
                    parts = payload.split('|||')
                    lid = int(parts[0]); fitid = parts[1]; amt = float(parts[2])
                    cur = conn.cursor();
                    cur.execute('DELETE FROM bank_statement_lines WHERE matched_entry_id=?', (lid,))
                    cur.execute('UPDATE cash_book SET reconciled=0 WHERE id=?', (lid,))
                    conn.commit(); QMessageBox.information(self,'Undo','Last match undone')
                else:
                    QMessageBox.information(self,'Undo','Last action not a match, cannot undo here')
            self.refresh_all()
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    # ---------------- Manage Accounts Tab ----------------
    def build_manage_tab(self):
        layout = QVBoxLayout(self.tab_manage)
        self.manage_tbl = QTableWidget(); self.manage_tbl.setColumnCount(6); self.manage_tbl.setHorizontalHeaderLabels(['ID','Name','Bank','Account No','Opening Balance','Actions']); self.manage_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.manage_tbl)
        btn_row = QHBoxLayout(); btn_row.addStretch(); btn_add = QPushButton('Add Account'); btn_add.clicked.connect(self.add_bank_account); btn_row.addWidget(btn_add); layout.addLayout(btn_row)
        self.load_manage_accounts()

    def load_manage_accounts(self):
        try:
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT id,name,bank,account_no,opening_balance FROM bank_accounts'); rows = cur.fetchall()
            self.manage_tbl.setRowCount(len(rows))
            for r,row in enumerate(rows):
                for c,val in enumerate(row): self.manage_tbl.setItem(r,c,QTableWidgetItem(str(val)))
                btn = QPushButton('Edit'); btn.clicked.connect(lambda _, aid=row[0]: self.edit_bank_account(aid)); self.manage_tbl.setCellWidget(r,5,btn)
        except Exception as e:
            print('load_manage_accounts', e)

    def add_bank_account(self):
        dlg = QDialog(self); dlg.setWindowTitle('Add Bank Account'); form = QFormLayout(dlg)
        name = QLineEdit(); bank = QLineEdit(); acc = QLineEdit(); branch = QLineEdit(); opening = QLineEdit('0')
        form.addRow('Account Name', name); form.addRow('Bank', bank); form.addRow('Account No', acc); form.addRow('Branch Code', branch); form.addRow('Opening Balance', opening)
        btn = QPushButton('Save'); btn.clicked.connect(lambda: self._save_new_account(dlg, name, bank, acc, branch, opening)); form.addRow(btn)
        dlg.exec()

    def _save_new_account(self, dlg, name, bank, acc, branch, opening):
        try:
            ob = float(opening.text() or 0)
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('INSERT INTO bank_accounts (name, bank, account_no, branch_code, opening_balance) VALUES (?,?,?,?,?)', (name.text().strip(), bank.text().strip(), acc.text().strip(), branch.text().strip(), ob)); conn.commit()
            dlg.accept(); self.refresh_all(); QMessageBox.information(self,'Saved','Bank account added')
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def edit_bank_account(self, aid):
        try:
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT id,name,bank,account_no,branch_code,opening_balance FROM bank_accounts WHERE id=?', (aid,)); row = cur.fetchone()
            if not row: return
            dlg = QDialog(self); dlg.setWindowTitle('Edit Bank Account'); form = QFormLayout(dlg)
            name = QLineEdit(row[1]); bank = QLineEdit(row[2]); acc = QLineEdit(row[3]); branch = QLineEdit(row[4]); opening = QLineEdit(str(row[5] or 0))
            form.addRow('Account Name', name); form.addRow('Bank', bank); form.addRow('Account No', acc); form.addRow('Branch Code', branch); form.addRow('Opening Balance', opening)
            btn = QPushButton('Save'); btn.clicked.connect(lambda: self._save_edit_account(dlg, aid, name, bank, acc, branch, opening)); form.addRow(btn); dlg.exec()
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    def _save_edit_account(self, dlg, aid, name, bank, acc, branch, opening):
        try:
            ob = float(opening.text() or 0)
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('UPDATE bank_accounts SET name=?, bank=?, account_no=?, branch_code=?, opening_balance=? WHERE id=?', (name.text().strip(), bank.text().strip(), acc.text().strip(), branch.text().strip(), ob, aid)); conn.commit()
            dlg.accept(); self.refresh_all(); QMessageBox.information(self,'Saved','Bank account updated')
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    # ---------------- Rules Manager ----------------
    def open_rules_manager(self):
        dlg = QDialog(self); dlg.setWindowTitle('Bank Rules'); dlg.setFixedSize(600,400)
        layout = QVBoxLayout(dlg)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(['ID','Pattern','Action','Enabled']); layout.addWidget(table)
        btn_row = QHBoxLayout(); btn_add = QPushButton('Add Rule'); btn_add.clicked.connect(lambda: self.add_rule(table)); btn_row.addWidget(btn_add); btn_row.addStretch(); layout.addLayout(btn_row)
        try:
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('SELECT id,pattern,action,enabled FROM bank_rules'); rows = cur.fetchall()
            table.setRowCount(len(rows))
            for r,row in enumerate(rows):
                table.setItem(r,0,QTableWidgetItem(str(row[0]))); table.setItem(r,1,QTableWidgetItem(row[1])); table.setItem(r,2,QTableWidgetItem(row[2])); table.setItem(r,3,QTableWidgetItem(str(bool(row[3]))))
        except Exception as e:
            print('rules load', e)
        dlg.exec()

    def add_rule(self, table=None):
        dlg = QDialog(self); dlg.setWindowTitle('Add Rule'); form = QFormLayout(dlg)
        pattern = QLineEdit(); action = QLineEdit(); enabled = QComboBox(); enabled.addItems(['1','0'])
        form.addRow('Pattern (contains):', pattern); form.addRow('Action (e.g. categorize:Bank Charges):', action); form.addRow('Enabled', enabled)
        btn = QPushButton('Save'); btn.clicked.connect(lambda: self._save_rule(dlg, pattern, action, enabled, table)); form.addRow(btn); dlg.exec()

    def _save_rule(self, dlg, pattern, action, enabled, table):
        try:
            with get_conn() as conn:
                cur = conn.cursor(); cur.execute('INSERT INTO bank_rules (pattern, action, enabled) VALUES (?,?,?)', (pattern.text().strip(), action.text().strip(), int(enabled.currentText()))); conn.commit()
            dlg.accept(); QMessageBox.information(self,'Saved','Rule added')
            if table: self.open_rules_manager()
        except Exception as e:
            QMessageBox.critical(self,'Error',str(e))

    # ---------------- Top-level refresh ----------------
    def refresh_all(self):
        try:
            self.refresh_accounts_cards(); self.load_accounts_in_combo(); self.load_accounts_in_import(); self.load_manage_accounts(); self.load_accounts_in_reconcile(); self.refresh_transactions_panel()
        except Exception as e:
            print('refresh all', e)

    def refresh_transactions_panel(self):
        self.load_accounts_in_combo(); self.load_transactions_for_selected_account();

    def open_ledger(self, account_id):
        idx = self.tabs.indexOf(self.tab_transactions)
        self.tabs.setCurrentIndex(idx)
        for i in range(self.tx_account_combo.count()):
            if self.tx_account_combo.itemData(i) == account_id:
                self.tx_account_combo.setCurrentIndex(i); break

    def open_reconcile_dialog(self, account_id):
        idx = self.tabs.indexOf(self.tab_reconcile); self.tabs.setCurrentIndex(idx)
        for i in range(self.rec_account.count()):
            if self.rec_account.itemData(i) == account_id:
                self.rec_account.setCurrentIndex(i); break

# End of file
