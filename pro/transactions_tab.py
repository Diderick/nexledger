# pro/transactions_tab.py
# FINAL – FIXED INDENT + RED DELETE BUTTON – 12 November 2025

import csv
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QLabel, QMessageBox, QHeaderView,
    QDateEdit, QFileDialog, QDialog, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QDate
from shared.db import get_conn
from shared.theme import is_dark_mode


class TransactionsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Transactions</h2>")
        header.addWidget(title)
        header.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search description...")
        self.search_box.textChanged.connect(self.filter_table)
        header.addWidget(self.search_box)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "Income", "Expense"])
        self.type_filter.currentTextChanged.connect(self.filter_table)
        header.addWidget(self.type_filter)

        add_btn = QPushButton("Add Transaction")
        add_btn.clicked.connect(self.add_transaction)  # ← FIXED INDENT
        header.addWidget(add_btn)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Date", "Description", "Amount", "Type", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.verticalHeader().setMinimumSectionSize(50)
        layout.addWidget(self.table)

        self.status = QLabel("Loading...")
        layout.addWidget(self.status)

    def refresh_data(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT t.id, t.date, t.description, t.amount, t.type
                FROM transactions t
                ORDER BY t.date DESC
            """)
            rows = cur.fetchall()
            conn.close()

            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self.table.setItem(r, 0, QTableWidgetItem(str(row[0])))
                self.table.setItem(r, 1, QTableWidgetItem(row[1]))
                self.table.setItem(r, 2, QTableWidgetItem(row[2]))
                amount = float(row[3])
                amt_item = QTableWidgetItem(f"R{abs(amount):,.2f}")
                amt_item.setForeground(Qt.GlobalColor.green if amount > 0 else Qt.GlobalColor.red)
                amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 3, amt_item)
                self.table.setItem(r, 4, QTableWidgetItem(row[4]))

                # Actions Widget
                actions = QWidget()
                lay = QHBoxLayout(actions)
                lay.setContentsMargins(8, 4, 8, 4)
                lay.setSpacing(8)

                edit_btn = QPushButton("Edit")
                edit_btn.setMinimumHeight(38)
                edit_btn.setStyleSheet("""
                    QPushButton {
                        background: #0078d4;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        padding: 6px 14px;
                        font-weight: bold;
                        font-size: 13px;
                    }
                    QPushButton:hover { background: #106ebe; }
                """)
                edit_btn.clicked.connect(lambda _, rid=row[0]: self.edit_transaction(rid))
                lay.addWidget(edit_btn)

                del_btn = QPushButton("Delete")
                del_btn.setMinimumHeight(38)
                del_btn.setStyleSheet("""
                    QPushButton {
                        background: #dc3545;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        padding: 6px 14px;
                        font-weight: bold;
                        font-size: 13px;
                    }
                    QPushButton:hover { background: #c82333; }
                """)
                del_btn.clicked.connect(lambda _, rid=row[0]: self.delete_transaction(rid))
                lay.addWidget(del_btn)

                self.table.setCellWidget(r, 5, actions)

            self.table.resizeRowsToContents()
            self.status.setText(f"{len(rows)} transactions")
            self.apply_theme()
        except Exception as e:
            self.status.setText(f"Error: {e}")
            print("Refresh error:", e)

    def filter_table(self):
        search = self.search_box.text().lower()
        typ = self.type_filter.currentText()
        for r in range(self.table.rowCount()):
            desc = self.table.item(r, 2).text().lower()
            ttype = self.table.item(r, 4).text()
            show = (search in desc) and (typ == "All" or typ == ttype)
            self.table.setRowHidden(r, not show)

    def add_transaction(self):
        self.show_dialog()

    def edit_transaction(self, tid):
        self.show_dialog(tid)

    def show_dialog(self, tid=None):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Transaction" if tid else "Add Transaction")
        dialog.setFixedSize(460, 280)
        lay = QFormLayout(dialog)

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate.currentDate())
        desc_edit = QLineEdit()
        amount_edit = QLineEdit()
        type_combo = QComboBox()
        type_combo.addItems(["Income", "Expense"])

        lay.addRow("Date:", date_edit)
        lay.addRow("Description:", desc_edit)
        lay.addRow("Amount:", amount_edit)
        lay.addRow("Type:", type_combo)

        btns = QDialogButtonBox()
        btns.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        lay.addRow(btns)

        if tid:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT * FROM transactions WHERE id=?", (tid,))
                row = cur.fetchone()
                conn.close()
                date_edit.setDate(QDate.fromString(row["date"], "yyyy-MM-dd"))
                desc_edit.setText(row["description"])
                amount_edit.setText(str(abs(row["amount"])))
                type_combo.setCurrentText(row["type"])
            except:
                pass

        def save():
            try:
                date = date_edit.date().toString("yyyy-MM-dd")
                desc = desc_edit.text().strip()
                amount = float(amount_edit.text())
                typ = type_combo.currentText()
                if not desc or amount <= 0:
                    QMessageBox.warning(dialog, "Error", "Invalid input")
                    return
                amount = amount if typ == "Income" else -amount

                conn = get_conn()
                cur = conn.cursor()
                if tid:
                    cur.execute("UPDATE transactions SET date=?, description=?, amount=?, type=? WHERE id=?",
                                (date, desc, amount, typ, tid))
                else:
                    cur.execute("INSERT INTO transactions (date, description, amount, type) VALUES (?, ?, ?, ?)",
                                (date, desc, amount, typ))
                conn.commit()
                conn.close()
                dialog.accept()
                self.refresh_data()
            except Exception as e:
                QMessageBox.critical(dialog, "Error", str(e))

        btns.accepted.connect(save)
        dialog.exec()

    def delete_transaction(self, tid):
        if QMessageBox.question(self, "Delete", "Delete this transaction?") == QMessageBox.StandardButton.Yes:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("DELETE FROM transactions WHERE id=?", (tid,))
                conn.commit()
                conn.close()
                self.refresh_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def apply_theme(self):
        dark = is_dark_mode()
        bg = "#2d2d2d" if dark else "#ffffff"
        text = "#ffffff" if dark else "#000000"
        border = "#444" if dark else "#ddd"

        style = f"""
            QTableWidget {{ 
                background: {bg}; 
                color: {text}; 
                gridline-color: {border}; 
                font-size: 14px;
            }}
            QHeaderView::section {{ 
                background: #0078d4; 
                color: white; 
                padding: 12px; 
                font-weight: bold; 
                font-size: 14px;
            }}
            QPushButton {{ 
                padding: 8px 16px; 
                border-radius: 6px; 
                font-weight: bold;
            }}
        """
        self.table.setStyleSheet(style)
        self.setStyleSheet(f"background: {bg}; color: {text};")