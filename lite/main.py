# lite/main.py
import sys, sqlite3
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QDateEdit, QComboBox, QMessageBox, QHeaderView, QCheckBox
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont
from shared.db import init_db, get_conn

class NexLedgerLite(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle("NexLedger Lite – Pastel-style")
        self.setGeometry(200, 200, 800, 600)
        self.init_ui()
        self.apply_style()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        # ---- Form ----
        form = QHBoxLayout()
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDate(QDate.currentDate())
        self.desc = QLineEdit(placeholderText="Description")
        self.amt = QLineEdit(placeholderText="0.00")
        self.typ = QComboBox()
        self.typ.addItems(["Income", "Expense"])
        add = QPushButton("Add")
        add.clicked.connect(self.add_tx)
        form.addWidget(QLabel("Date"))
        form.addWidget(self.date)
        form.addWidget(QLabel("Desc"))
        form.addWidget(self.desc)
        form.addWidget(QLabel("Amt"))
        form.addWidget(self.amt)
        form.addWidget(QLabel("Type"))
        form.addWidget(self.typ)
        form.addWidget(add)
        main.addLayout(form)

        # ---- Table ----
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date","Description","Amount","Type"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        main.addWidget(self.table)

        # ---- Theme toggle ----
        self.dark_cb = QCheckBox("Dark mode")
        self.dark_cb.stateChanged.connect(self.toggle_theme)
        main.addWidget(self.dark_cb)

        self.refresh()

    def add_tx(self):
        try:
            amount = float(self.amt.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid amount")
            return
        if not self.desc.text().strip():
            QMessageBox.warning(self, "Error", "Description required")
            return

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO lite_transactions (date,description,amount,type) VALUES (?,?,?,?)",
            (self.date.date().toString("yyyy-MM-dd"),
             self.desc.text(),
             amount,
             self.typ.currentText())
        )
        conn.commit()
        conn.close()
        self.desc.clear(); self.amt.clear()
        self.refresh()

    def refresh(self):
        conn = get_conn()
        rows = conn.execute("SELECT date,description,amount,type FROM lite_transactions ORDER BY date DESC").fetchall()
        conn.close()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r,0,QTableWidgetItem(row["date"]))
            self.table.setItem(r,1,QTableWidgetItem(row["description"]))
            self.table.setItem(r,2,QTableWidgetItem(f"${row['amount']:.2f}"))
            self.table.setItem(r,3,QTableWidgetItem(row["type"]))

    # ----------------- Styling -----------------
    def apply_style(self):
        self.setStyleSheet(self.light_style)

    light_style = """
        QWidget { background:#fafafa; font-family:Segoe UI; }
        QPushButton { background:#007acc; color:white; border:none; padding:8px; border-radius:4px; }
        QPushButton:hover { background:#005a99; }
        QLineEdit, QComboBox, QDateEdit { padding:6px; border:1px solid #ccc; border-radius:4px; }
        QTableWidget { gridline-color:#ddd; }
    """
    dark_style = """
        QWidget { background:#2b2b2b; color:#eee; font-family:Segoe UI; }
        QPushButton { background:#1e88e5; }
        QPushButton:hover { background:#1565c0; }
        QLineEdit, QComboBox, QDateEdit { background:#424242; color:#fff; border:1px solid #555; }
        QTableWidget { background:#424242; color:#fff; gridline-color:#555; }
    """

    def toggle_theme(self, state):
        self.setStyleSheet(self.dark_style if state else self.light_style)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = NexLedgerLite()
    win.show()
    sys.exit(app.exec())