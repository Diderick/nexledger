# reports_tab.py
# NexLedger Reports Tab (QuickBooks-style)
# Provides:
# • Profit & Loss
# • Balance Sheet
# • Trial Balance
# • VAT Report
# • Cash Flow Summary
# Uses db.py schema

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit
)
from PyQt6.QtCore import QDate
from datetime import datetime
from shared.db import db_connection

class ReportsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Report selector
        top = QHBoxLayout()
        self.report_type = QComboBox()
        self.report_type.addItems([
            "Profit & Loss",
            "Balance Sheet",
            "Trial Balance",
            "VAT Report",
            "Cash Flow"
        ])
        top.addWidget(QLabel("Report:"))
        top.addWidget(self.report_type)

        self.from_date = QDateEdit()
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(QDate.currentDate().addMonths(-1))

        self.to_date = QDateEdit()
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())

        top.addWidget(QLabel("From:"))
        top.addWidget(self.from_date)
        top.addWidget(QLabel("To:"))
        top.addWidget(self.to_date)

        btn_run = QPushButton("Run Report")
        btn_run.clicked.connect(self.run_report)
        top.addWidget(btn_run)

        layout.addLayout(top)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Account", "Debit", "Credit"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    # ----------------------------------------------------------
    # REPORT DISPATCHER
    # ----------------------------------------------------------
    def run_report(self):
        r = self.report_type.currentText()
        f = self.from_date.date().toString("yyyy-MM-dd")
        t = self.to_date.date().toString("yyyy-MM-dd")

        if r == "Profit & Loss":
            self.run_profit_and_loss(f, t)
        elif r == "Balance Sheet":
            self.run_balance_sheet(f, t)
        elif r == "Trial Balance":
            self.run_trial_balance(f, t)
        elif r == "VAT Report":
            self.run_vat_report(f, t)
        elif r == "Cash Flow":
            self.run_cash_flow(f, t)

    # ----------------------------------------------------------
    # PROFIT & LOSS (Income - Expenses)
    # ----------------------------------------------------------
    def run_profit_and_loss(self, f, t):
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT a.name, SUM(jl.debit) AS d, SUM(jl.credit) AS c "
                "FROM journal_lines jl "
                "JOIN journal_entries je ON je.id = jl.journal_id "
                "JOIN accounts a ON a.id = jl.account_id "
                "WHERE je.date BETWEEN ? AND ? AND a.type IN ('Income','Expense') "
                "GROUP BY a.name ORDER BY a.name",
                (f, t)
            )
            rows = cur.fetchall()

        self.fill_table(rows)

    # ----------------------------------------------------------
    # TRIAL BALANCE
    # ----------------------------------------------------------
    def run_trial_balance(self, f, t):
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT a.name, SUM(jl.debit) AS d, SUM(jl.credit) AS c "
                "FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_id "
                "JOIN accounts a ON a.id = jl.account_id "
                "WHERE je.date BETWEEN ? AND ? GROUP BY a.name ORDER BY a.code",
                (f, t)
            )
            rows = cur.fetchall()

        self.fill_table(rows)

    # ----------------------------------------------------------
    # BALANCE SHEET (Assets, Liabilities, Equity)
    # ----------------------------------------------------------
    def run_balance_sheet(self, f, t):
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT a.type, a.name, SUM(jl.debit) AS d, SUM(jl.credit) AS c "
                "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id "
                "JOIN journal_entries je ON je.id = jl.journal_id "
                "WHERE je.date <= ? GROUP BY a.id ORDER BY a.code",
                (t,)
            )
            rows = cur.fetchall()

        self.fill_table(rows)

    # ----------------------------------------------------------
    # VAT REPORT (Based on VAT columns in invoice_items / bill_items)
    # ----------------------------------------------------------
    def run_vat_report(self, f, t):
        with db_connection() as conn:
            cur = conn.cursor()
            # VAT collected (Sales)
            cur.execute(
                "SELECT 'VAT Output', SUM(vat) AS vat, SUM(total) AS amount FROM invoices WHERE date BETWEEN ? AND ?",
                (f, t)
            )
            out_vat = cur.fetchone()

            # VAT paid (Purchases)
            cur.execute(
                "SELECT 'VAT Input', SUM(vat) AS vat, SUM(total) AS amount FROM bills WHERE date BETWEEN ? AND ?",
                (f, t)
            )
            in_vat = cur.fetchone()

        rows = []
        if out_vat:
            rows.append({'name': 'VAT Output', 'd': out_vat['amount'], 'c': out_vat['vat']})
        if in_vat:
            rows.append({'name': 'VAT Input', 'd': in_vat['amount'], 'c': in_vat['vat']})

        self.fill_table(rows)

    # ----------------------------------------------------------
    # CASH FLOW SUMMARY
    # ----------------------------------------------------------
    def run_cash_flow(self, f, t):
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT a.name, SUM(jl.debit - jl.credit) AS cf "
                "FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_id "
                "JOIN accounts a ON a.id = jl.account_id "
                "WHERE je.date BETWEEN ? AND ? GROUP BY a.name",
                (f, t)
            )
            rows = cur.fetchall()

        self.fill_table(rows)

    # ----------------------------------------------------------
    # HELPER: Fill the report table
    # ----------------------------------------------------------
    def fill_table(self, rows):
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name = r['name'] if 'name' in r.keys() else r[0]
            d = r['d'] if 'd' in r.keys() else r[1]
            c = r['c'] if 'c' in r.keys() else r[2]
            self.table.setItem(i, 0, QTableWidgetItem(str(name)))
            self.table.setItem(i, 1, QTableWidgetItem(str(d or 0)))
            self.table.setItem(i, 2, QTableWidgetItem(str(c or 0)))

        self.table.resizeRowsToContents()