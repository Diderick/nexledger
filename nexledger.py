import sys
import sqlite3
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QPushButton, QLineEdit, QLabel, QTableWidget,
                             QTableWidgetItem, QComboBox, QDateEdit, QHeaderView,
                             QSplitter, QTabWidget, QMessageBox, QFileDialog, QTextEdit,
                             QCheckBox, QSpinBox)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QIcon, QPalette
import pyqtgraph as pg
from pyqtgraph import PlotWidget

# Database setup
def init_db():
    conn = sqlite3.connect('nexledger.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('Income', 'Expense'))
        )
    ''')
    conn.commit()
    conn.close()

# Fetch transactions for dashboard/chart
def get_transactions_summary():
    conn = sqlite3.connect('nexledger.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, SUM(amount) FROM transactions WHERE type=? GROUP BY date', ('Income',))
    income = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute('SELECT date, SUM(amount) FROM transactions WHERE type=? GROUP BY date', ('Expense',))
    expense = {row[0]: -row[1] for row in cursor.fetchall()}
    conn.close()
    return {**income, **expense}

# Main Application Class
class NexLedger(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        self.setWindowTitle('NexLedger - Modern Accounting')
        self.setGeometry(100, 100, 1200, 800)
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Sidebar (Navigation)
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(self.create_nav_button('Dashboard', self.show_dashboard))
        sidebar_layout.addWidget(self.create_nav_button('Transactions', self.show_transactions))
        sidebar_layout.addWidget(self.create_nav_button('Reports', self.show_reports))
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(self.create_theme_toggle())
        main_layout.addWidget(sidebar)

        # Content area with splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Tabs for content
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)

        # Initialize tabs
        self.dashboard_tab = self.create_dashboard_tab()
        self.transactions_tab = self.create_transactions_tab()
        self.reports_tab = self.create_reports_tab()

        self.tabs.addTab(self.dashboard_tab, 'Dashboard')
        self.tabs.addTab(self.transactions_tab, 'Transactions')
        self.tabs.addTab(self.reports_tab, 'Reports')

        # Default to dashboard
        self.show_dashboard()

    def create_nav_button(self, text, callback):
        btn = QPushButton(text)
        btn.setFont(QFont('Arial', 10, QFont.Weight.Bold))
        btn.clicked.connect(callback)
        return btn

    def create_theme_toggle(self):
        self.theme_cb = QCheckBox('Dark Mode')
        self.theme_cb.stateChanged.connect(self.toggle_theme)
        return self.theme_cb

    def create_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Summary labels
        summary_layout = QGridLayout()
        self.total_income = QLabel('Total Income: $0.00')
        self.total_expense = QLabel('Total Expense: $0.00')
        self.net_balance = QLabel('Net Balance: $0.00')
        summary_layout.addWidget(QLabel('Summary'), 0, 0)
        summary_layout.addWidget(self.total_income, 1, 0)
        summary_layout.addWidget(self.total_expense, 1, 1)
        summary_layout.addWidget(self.net_balance, 1, 2)
        layout.addLayout(summary_layout)

        # Chart
        self.chart_widget = PlotWidget()
        self.chart_widget.setBackground('w')
        self.chart_widget.addLegend()
        layout.addWidget(self.chart_widget)

        self.update_dashboard()
        return tab

    def create_transactions_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Add transaction form
        form_layout = QGridLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.desc_edit = QLineEdit()
        self.amount_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(['Income', 'Expense'])
        add_btn = QPushButton('Add Transaction')

        form_layout.addWidget(QLabel('Date:'), 0, 0)
        form_layout.addWidget(self.date_edit, 0, 1)
        form_layout.addWidget(QLabel('Description:'), 1, 0)
        form_layout.addWidget(self.desc_edit, 1, 1)
        form_layout.addWidget(QLabel('Amount:'), 2, 0)
        form_layout.addWidget(self.amount_edit, 2, 1)
        form_layout.addWidget(QLabel('Type:'), 3, 0)
        form_layout.addWidget(self.type_combo, 3, 1)
        form_layout.addWidget(add_btn, 4, 1)
        add_btn.clicked.connect(self.add_transaction)

        layout.addLayout(form_layout)

        # Transactions table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['Date', 'Description', 'Amount', 'Type'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.load_transactions()
        return tab

    def create_reports_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        export_btn = QPushButton('Export to CSV')
        export_btn.clicked.connect(self.export_report)
        layout.addWidget(self.report_text)
        layout.addWidget(export_btn)
        self.update_report()
        return tab

    def apply_styles(self):
        # Modern stylesheet for better looks
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
                font-family: 'Segoe UI', Arial;
            }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005fa3;
            }
            QLineEdit, QComboBox, QDateEdit {
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QTableWidget {
                gridline-color: #ddd;
                alternate-background-color: #f9f9f9;
            }
            QLabel {
                font-size: 12px;
                color: #333;
            }
        """)

    def toggle_theme(self):
        if self.theme_cb.isChecked():
            # Dark theme
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2b2b2b;
                    color: #fff;
                }
                QPushButton {
                    background-color: #1e88e5;
                }
                QPushButton:hover {
                    background-color: #1565c0;
                }
                QLineEdit, QComboBox, QDateEdit {
                    background-color: #424242;
                    color: #fff;
                    border: 1px solid #555;
                }
                QTableWidget {
                    background-color: #424242;
                    color: #fff;
                    gridline-color: #555;
                    alternate-background-color: #303030;
                }
                QLabel {
                    color: #ddd;
                }
                PlotWidget {
                    background-color: #2b2b2b;
                    color: #fff;
                }
            """)
            self.chart_widget.setBackground('#2b2b2b')
        else:
            # Light theme (reset)
            self.apply_styles()
            self.chart_widget.setBackground('w')

    def show_dashboard(self):
        self.tabs.setCurrentIndex(0)
        self.update_dashboard()

    def show_transactions(self):
        self.tabs.setCurrentIndex(1)
        self.load_transactions()

    def show_reports(self):
        self.tabs.setCurrentIndex(2)
        self.update_report()

    def add_transaction(self):
        date = self.date_edit.date().toString('yyyy-MM-dd')
        desc = self.desc_edit.text()
        try:
            amount = float(self.amount_edit.text())
        except ValueError:
            QMessageBox.warning(self, 'Error', 'Invalid amount.')
            return
        trans_type = self.type_combo.currentText()

        if not desc:
            QMessageBox.warning(self, 'Error', 'Description required.')
            return

        conn = sqlite3.connect('nexledger.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO transactions (date, description, amount, type) VALUES (?, ?, ?, ?)',
                       (date, desc, amount, trans_type))
        conn.commit()
        conn.close()

        self.desc_edit.clear()
        self.amount_edit.clear()
        self.load_transactions()
        self.update_dashboard()
        self.update_report()
        QMessageBox.information(self, 'Success', 'Transaction added!')

    def load_transactions(self):
        conn = sqlite3.connect('nexledger.db')
        cursor = conn.cursor()
        cursor.execute('SELECT date, description, amount, type FROM transactions ORDER BY date DESC')
        rows = cursor.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(row[0]))
            self.table.setItem(i, 1, QTableWidgetItem(row[1]))
            self.table.setItem(i, 2, QTableWidgetItem(f'${row[2]:.2f}'))
            self.table.setItem(i, 3, QTableWidgetItem(row[3]))

    def update_dashboard(self):
        data = get_transactions_summary()
        if not data:
            return

        dates = sorted(data.keys())
        income_data = [data.get(d, 0) for d in dates if data[d] > 0]
        expense_data = [abs(data.get(d, 0)) for d in dates if data[d] < 0]
        net_data = [data[d] for d in dates]

        # Clear previous plots
        self.chart_widget.clear()

        # Plot net balance
        self.chart_widget.plot(dates, net_data, pen='g', name='Net Balance', symbol='o')

        # Summary totals
        conn = sqlite3.connect('nexledger.db')
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE type=?', ('Income',))
        total_income = cursor.fetchone()[0] or 0
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE type=?', ('Expense',))
        total_expense = cursor.fetchone()[0] or 0
        net = total_income - total_expense
        conn.close()

        self.total_income.setText(f'Total Income: ${total_income:.2f}')
        self.total_expense.setText(f'Total Expense: ${total_expense:.2f}')
        self.net_balance.setText(f'Net Balance: ${net:.2f}')

    def update_report(self):
        conn = sqlite3.connect('nexledger.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transactions ORDER BY date DESC')
        rows = cursor.fetchall()
        conn.close()

        report = 'NexLedger Report\n' + '='*30 + '\n'
        report += f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n'
        report += 'Date | Description | Amount | Type\n'
        report += '-'*40 + '\n'
        for row in rows:
            report += f'{row[1]} | {row[2]} | ${row[3]:.2f} | {row[4]}\n'

        self.report_text.setText(report)

    def export_report(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Export Report', 'nexledger_report.csv', 'CSV Files (*.csv)')
        if file_path:
            with open(file_path, 'w') as f:
                f.write('Date,Description,Amount,Type\n')
                conn = sqlite3.connect('nexledger.db')
                cursor = conn.cursor()
                cursor.execute('SELECT date, description, amount, type FROM transactions ORDER BY date DESC')
                for row in cursor.fetchall():
                    f.write(f'{row[0]},{row[1]},{row[2]},{row[3]}\n')
                conn.close()
            QMessageBox.information(self, 'Success', 'Report exported!')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NexLedger()
    window.show()
    sys.exit(app.exec())