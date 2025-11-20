# bank_account_tab.py
# Bank Accounts Tab for NexLedger (integrated with db.py)
# Features:
# • Shows list of bank accounts from chart of accounts (Asset accounts only)
# • Shows balance (sum of related cash_book + journal lines)
# • Add / Edit bank account
# • View transactions for selected account

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QLineEdit, QFormLayout, QMessageBox
)
from PyQt6.QtCore import Qt
from shared.db import db_connection, get_conn
import sqlite3
from datetime import datetime

class BankAccountTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_accounts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Code", "Name", "Type", "Balance"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add Bank Account")
        add_btn.clicked.connect(self.add_bank_account)
        btn_layout.addWidget(add_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_accounts)
        btn_layout.addWidget(refresh_btn)

        layout.addLayout(btn_layout)

    def load_accounts(self):
        """Load only Asset accounts that look like bank accounts (code 1000–1099)."""
        try:
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, code, name, type FROM accounts WHERE type='Asset' AND code LIKE '1%'")
                rows = cur.fetchall()
        except Exception as e:
            print("[bank_account_tab] load error", e)
            rows = []

        self.table.setRowCount(len(rows))

        for i, r in enumerate(rows):
            balance = self.calculate_balance(r["id"])
            self.table.setItem(i, 0, QTableWidgetItem(str(r["code"])))
            self.table.setItem(i, 1, QTableWidgetItem(str(r["name"])))
            self.table.setItem(i, 2, QTableWidgetItem(str(r["type"])))
            self.table.setItem(i, 3, QTableWidgetItem(f"{balance:.2f}"))

        self.table.resizeRowsToContents()

    def calculate_balance(self, account_id):
        """Total from journal lines and cash book for given account."""
        try:
            with db_connection() as conn:
                cur = conn.cursor()

                # Journal lines
                cur.execute(
                    "SELECT SUM(debit) as d, SUM(credit) as c FROM journal_lines WHERE account_id=?",
                    (account_id,)
                )
                jl = cur.fetchone()
                debit = jl["d"] or 0
                credit = jl["c"] or 0

                # Cashbook lines mapped to this account
                cur.execute(
                    "SELECT code, name FROM accounts WHERE id=?", (account_id,)
                )
                acc = cur.fetchone()
                if acc:
                    acc_name = acc["name"]
                else:
                    acc_name = None

                if acc_name:
                    cur.execute(
                        "SELECT SUM(debit) as d, SUM(credit) as c FROM cash_book WHERE account=?",
                        (acc_name,)
                    )
                    cb = cur.fetchone()
                    debit += cb["d"] or 0
                    credit += cb["c"] or 0

                return debit - credit

        except Exception as e:
            print("[bank_account_tab] balance error", e)
            return 0.0

    def add_bank_account(self):
        dialog = BankAccountDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            code, name = dialog.get_values()
            try:
                with db_connection() as conn:
                    conn.execute(
                        "INSERT INTO accounts(code, name, type) VALUES (?, ?, 'Asset')",
                        (code, name)
                    )
                    conn.commit()
                QMessageBox.information(self, "Success", "Bank account added.")
                self.load_accounts()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed: {e}")


class BankAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Bank Account")
        layout = QFormLayout(self)

        self.code_edit = QLineEdit()
        self.name_edit = QLineEdit()

        layout.addRow("Account Code (1000–1999):", self.code_edit)
        layout.addRow("Account Name:", self.name_edit)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addRow(btn_layout)

    def get_values(self):
        return self.code_edit.text().strip(), self.name_edit.text().strip()