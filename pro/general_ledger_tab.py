# general_ledger_tab.py
# Professional General Ledger tab integrated with project's db.py
# Uses journal_entries/journal_lines and cash_book to display a unified general ledger per account.

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QDateEdit, QComboBox
)
from PyQt6.QtCore import Qt, QDate
from datetime import datetime
import sqlite3
import os

# Import project's DB helpers
try:
    from shared.db import db_connection, get_conn, list_companies, get_current_company
except Exception:
    # fallback if run as standalone during testing
    def get_conn():
        conn = sqlite3.connect(os.environ.get('LEDGER_DB', 'ledger.db'))
        conn.row_factory = sqlite3.Row
        return conn
    def db_connection():
        class Ctx:
            def __enter__(self_c):
                return get_conn()
            def __exit__(self_c, exc_type, exc, tb):
                pass
        return Ctx()


class GeneralLedgerTab(QWidget):
    """
    GENERAL LEDGER TAB — Integrated with NexLedger DB

    - Shows journal lines (journal_entries + journal_lines) and cash_book entries
    - Account filter uses accounts table (code + name)
    - Date range filter
    - Running balance computed per selected account (if 'All Accounts', balance is cumulative across all accounts)

    Notes:
    - Expects accounts, journal_entries, journal_lines and cash_book tables as in db.py
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_accounts()
        self.load_ledger()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Filters
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("From:"))
        self.from_date = QDateEdit()
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.from_date.dateChanged.connect(self.load_ledger)
        filter_layout.addWidget(self.from_date)

        filter_layout.addWidget(QLabel("To:"))
        self.to_date = QDateEdit()
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.load_ledger)
        filter_layout.addWidget(self.to_date)

        filter_layout.addWidget(QLabel("Account:"))
        self.account_filter = QComboBox()
        self.account_filter.currentIndexChanged.connect(self.load_ledger)
        filter_layout.addWidget(self.account_filter)

        layout.addLayout(filter_layout)

        # Ledger table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Date", "Source", "Reference", "Account", "Debit", "Credit", "Description", "Running Balance", "Line ID"
        ])
        self.table.setColumnHidden(8, True)  # hide internal Line ID
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Controls
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_ledger)
        btn_layout.addWidget(refresh_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        btn_layout.addWidget(export_btn)

        layout.addLayout(btn_layout)

    def load_accounts(self):
        # Load accounts as 'code - name'
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, code, name FROM accounts ORDER BY code")
                accounts = cur.fetchall()
        except Exception:
            # fallback to empty
            accounts = []

        self.account_filter.clear()
        self.account_filter.addItem("All Accounts", None)
        for a in accounts:
            label = f"{a['code']} - {a['name']}"
            self.account_filter.addItem(label, a['id'])

    def load_ledger(self):
        # Build unified list of lines from journal_lines + cash_book within date range
        from_date = self.from_date.date().toString("yyyy-MM-dd")
        to_date = self.to_date.date().toString("yyyy-MM-dd")
        selected_account_id = self.account_filter.currentData()

        lines = []
        # --- journal lines ---
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT jl.id as line_id, je.date as entry_date, 'Journal' as source, je.reference as reference, "
                    "a.code || ' - ' || a.name as account, jl.debit as debit, jl.credit as credit, je.memo as description, a.id as account_id "
                    "FROM journal_entries je JOIN journal_lines jl ON jl.journal_id = je.id JOIN accounts a ON a.id = jl.account_id "
                    "WHERE je.date BETWEEN ? AND ?",
                    (from_date, to_date)
                )
                rows = cur.fetchall()
                for r in rows:
                    lines.append(dict(r))

                # --- cash_book lines ---
                # cash_book.account stores account text; we will try to match by code or name
                cur.execute(
                    "SELECT id as line_id, date as entry_date, 'Cashbook' as source, reference, account as account_text, debit, credit, narration as description "
                    "FROM cash_book WHERE date BETWEEN ? AND ?",
                    (from_date, to_date)
                )
                cb_rows = cur.fetchall()
                # attempt to resolve account_text to account id and account label
                for r in cb_rows:
                    account_text = r['account'] or ''
                    # try to find account by code or name
                    cur.execute("SELECT id, code, name FROM accounts WHERE code = ? OR name = ? LIMIT 1", (account_text, account_text))
                    a = cur.fetchone()
                    if a:
                        account_label = f"{a['code']} - {a['name']}"
                        account_id = a['id']
                    else:
                        account_label = account_text
                        account_id = None
                    line = {
                        'line_id': r['line_id'],
                        'entry_date': r['entry_date'],
                        'source': 'Cashbook',
                        'reference': r['reference'],
                        'account': account_label,
                        'debit': r['debit'],
                        'credit': r['credit'],
                        'description': r['description'],
                        'account_id': account_id
                    }
                    lines.append(line)
        except Exception as e:
            print('[general_ledger] DB error:', e)

        # Filter by selected account if provided
        if selected_account_id:
            lines = [L for L in lines if L.get('account_id') == selected_account_id]

        # Sort by date then line_id
        def parse_date(d):
            try:
                return datetime.fromisoformat(d)
            except Exception:
                try:
                    return datetime.strptime(d, '%Y-%m-%d')
                except Exception:
                    return datetime.min

        lines.sort(key=lambda x: (parse_date(x['entry_date']), x['line_id']))

        # Populate table and compute running balance
        self.table.setRowCount(len(lines))
        running_balance = 0.0
        for i, L in enumerate(lines):
            debit = float(L.get('debit') or 0)
            credit = float(L.get('credit') or 0)
            running_balance += (debit - credit)

            self.table.setItem(i, 0, QTableWidgetItem(str(L.get('entry_date'))))
            self.table.setItem(i, 1, QTableWidgetItem(str(L.get('source'))))
            self.table.setItem(i, 2, QTableWidgetItem(str(L.get('reference') or '')))
            self.table.setItem(i, 3, QTableWidgetItem(str(L.get('account') or '')))
            self.table.setItem(i, 4, QTableWidgetItem(('{:.2f}'.format(debit) if debit else '')))
            self.table.setItem(i, 5, QTableWidgetItem(('{:.2f}'.format(credit) if credit else '')))
            self.table.setItem(i, 6, QTableWidgetItem(str(L.get('description') or '')))
            self.table.setItem(i, 7, QTableWidgetItem('{:.2f}'.format(running_balance)))
            self.table.setItem(i, 8, QTableWidgetItem(str(L.get('line_id'))))

        self.table.resizeRowsToContents()

    def export_csv(self):
        # Exports visible table to CSV in current directory
        import csv
        rows = []
        headers = [self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount()) if not self.table.isColumnHidden(c)]
        for r in range(self.table.rowCount()):
            row = []
            for c in range(self.table.columnCount()):
                if self.table.isColumnHidden(c):
                    continue
                item = self.table.item(r, c)
                row.append(item.text() if item else '')
            rows.append(row)
        out = 'general_ledger_export.csv'
        with open(out, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        print(f'Exported {len(rows)} rows to {out}')
