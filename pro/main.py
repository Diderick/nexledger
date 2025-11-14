# pro/main.py
# FINAL MERGED + ALL FEATURES + THEME FIXED – 12 November 2025
# (patched 2025-11-15 to avoid closing persistent DBs)

import sys, os, json

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QTabWidget, QFrame, QCheckBox,
    QDialog, QDialogButtonBox, QLineEdit, QInputDialog, QRadioButton,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from pathlib import Path

from pro.dashboard import Dashboard
from pro.company_wizard import CompanySetupWizard
from pro.transactions_tab import TransactionsTab
from pro.bank_feeds_tab import BankFeedsTab
from pro.payroll_tab import PayrollTab
from shared.settings_tab import SettingsTab


from shared.db import (
    set_current_company, get_current_company, get_conn,
    init_db_for_company, list_companies, COMPANIES_DIR, delete_company, SETTINGS_FILE, is_duplicate_transaction,
    create_company
)
from shared.theme import get_widget_style, is_dark_mode, set_dark_mode


ICONS_DIR = Path(__file__).parent.parent / "icons"
def icon(name):
    p = ICONS_DIR / name
    return QIcon(str(p)) if p.exists() else QIcon()


# ========================
# Login Dialog
# ========================

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexLedger Pro – Login")
        self.setFixedSize(420, 340)
        self.setStyleSheet(get_widget_style())  # CENTRAL THEME

        lay = QVBoxLayout(self)
        lay.setSpacing(15)
        lay.setContentsMargins(40, 30, 40, 30)

        title = QLabel("<h2 style='margin:0;'>NexLedger Pro</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        self.user = QLineEdit()
        self.user.setPlaceholderText("Username")
        self.user.setMinimumHeight(45)
        lay.addWidget(self.user)

        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd.setPlaceholderText("Password")
        self.pwd.setMinimumHeight(45)
        lay.addWidget(self.pwd)

        login_btn = QPushButton("Login")
        login_btn.setMinimumHeight(50)
        login_btn.setStyleSheet("font-weight: bold; font-size: 15px;")
        login_btn.clicked.connect(self.validate_login)
        lay.addWidget(login_btn)

        footer = QLabel("© 2025 NexLedger Pro | SARS VAT Compliant")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("font-size: 11px; color: #888;")
        lay.addWidget(footer)

    def validate_login(self):
        if self.user.text().strip() and self.pwd.text().strip():
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Please enter username and password.")


# ========================
# Company Selector
# ========================

class CompanySelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Company")
        self.setFixedSize(500, 500)
        self.setStyleSheet(get_widget_style())  # CENTRAL THEME

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        layout.addWidget(QLabel("<h2>Select Company</h2>"))

        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Company Name"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        self.refresh_companies()

        create_btn = QPushButton("Create New Company")
        create_btn.setStyleSheet("background:#28a745; color:white; font-weight:bold; padding:10px; border-radius:6px;")
        create_btn.clicked.connect(self.show_create_company)
        layout.addWidget(create_btn)

        btns = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self.open_selected)
        btns.addWidget(open_btn)

        del_btn = QPushButton("Delete Selected")
        del_btn.setStyleSheet("background:#dc3545; color:white; font-weight:bold; padding:8px 16px; border-radius:6px;")
        del_btn.clicked.connect(self.delete_company)
        btns.addWidget(del_btn)

        btns.addStretch()
        layout.addLayout(btns)

    def refresh_companies(self):
        companies = list_companies()
        self.table.setRowCount(len(companies))
        last_company = get_current_company()
        selected_row = -1
        for i, name in enumerate(companies):
            item = QTableWidgetItem(name)
            if name == last_company:
                selected_row = i
                item.setBackground(Qt.GlobalColor.cyan)
            self.table.setItem(i, 0, item)
        if selected_row != -1:
            self.table.selectRow(selected_row)

    def show_create_company(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Company")
        dialog.setFixedSize(500, 300)
        dialog.setStyleSheet(get_widget_style())
        lay = QVBoxLayout(dialog)
        lay.setContentsMargins(30, 30, 30, 30)

        lay.addWidget(QLabel("<h3>Create Company</h3>"))

        quick = QRadioButton("Quick Add (Name only)")
        wizard = QRadioButton("Setup Wizard (Full details)")
        quick.setChecked(True)
        lay.addWidget(quick)
        lay.addWidget(wizard)

        btns = QDialogButtonBox()
        btns.addButton("Create", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(lambda: self.handle_create(quick.isChecked(), dialog))
        btns.rejected.connect(dialog.reject)
        lay.addWidget(btns)

        dialog.exec()

    def handle_create(self, is_quick, dialog):
        dialog.accept()
        if is_quick:
            name, ok = QInputDialog.getText(self, "Quick Add", "Company name:")
            if not ok or not name.strip():
                return
            name = name.strip()
            if name in list_companies():
                QMessageBox.warning(self, "Error", "Company exists")
                return
            try:
                # use create_company to initialize properly
                create_company(name)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
                return
        else:
            wizard = CompanySetupWizard(self)
            if wizard.exec() != QDialog.DialogCode.Accepted:
                return
        self.refresh_companies()

    def delete_company(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Select", "Please select a company.")
            return
        name = self.table.item(row, 0).text()
        if name == get_current_company():
            QMessageBox.warning(self, "Active", "Cannot delete the current company.")
            return

        reply = QMessageBox.question(
            self, "Delete Company",
            f"Permanently delete <b>{name}</b>?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if delete_company(name):
                QMessageBox.information(self, "Deleted", f"<b>{name}</b> has been deleted.")
                self.refresh_companies()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete company.")

    def open_selected(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Error", "Select a company.")
            return
        company = self.table.item(row, 0).text()
        set_current_company(company)
        self.accept()


# ========================
# Main App
# ========================

class NexLedgerPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexLedger Pro")
        self.setGeometry(100, 100, 1400, 800)
        self.sidebar_collapsed = False  # ← INITIALIZED

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.build_top_bar()
        self.content_area = QHBoxLayout()
        self.main_layout.addLayout(self.content_area, 1)

        self.setStyleSheet(get_widget_style())  # CENTRAL THEME

    def build_top_bar(self):
        top = QFrame()
        top.setFixedHeight(60)
        top.setStyleSheet("background:#0078d4;")
        lay = QHBoxLayout(top)
        lay.setContentsMargins(20, 0, 20, 0)

        comp_area = QHBoxLayout()
        comp_area.setSpacing(12)
        self.company_label = QLabel("No Company")
        self.company_label.setStyleSheet("color:white; font-weight:bold; font-size:22px;")
        comp_area.addWidget(self.company_label)

        self.change_btn = QPushButton("Change Company")
        self.change_btn.setStyleSheet("background:#0061a8; color:white; border:none; padding:8px 18px; border-radius:8px; font-weight:bold;")
        self.change_btn.clicked.connect(self.change_company)
        comp_area.addWidget(self.change_btn)
        lay.addLayout(comp_area)
        lay.addStretch()

        self.dark_cb = QCheckBox("Dark Mode")
        self.dark_cb.setStyleSheet("color:white;")
        self.dark_cb.setChecked(is_dark_mode())
        self.dark_cb.stateChanged.connect(self.toggle_theme)
        lay.addWidget(self.dark_cb)

        self.sidebar_btn = QPushButton("Collapse")
        self.sidebar_btn.setStyleSheet("background:#0061a8; color:white; border:none; padding:8px 16px; border-radius:6px;")
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        lay.addWidget(self.sidebar_btn)

        self.logout_btn = QPushButton("Log Out")
        self.logout_btn.setStyleSheet("background:#dc3545; color:white; border:none; padding:8px 16px; border-radius:6px;")
        self.logout_btn.clicked.connect(self.logout)
        lay.addWidget(self.logout_btn)

        self.main_layout.addWidget(top)

    def toggle_theme(self, state):
        is_dark = state == Qt.CheckState.Checked.value
        set_dark_mode(is_dark)
        self.setStyleSheet(get_widget_style())
        self.dark_cb.blockSignals(True)
        self.dark_cb.setChecked(is_dark)
        self.dark_cb.blockSignals(False)

    def start(self):
        self.load_company(get_current_company())

    def change_company(self):
        dlg = CompanySelector(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_company(get_current_company())

    def logout(self):
        if QMessageBox.question(self, "Log Out", "Sure?") == QMessageBox.StandardButton.Yes:
            try:
                SETTINGS_FILE.unlink(missing_ok=True)
            except:
                pass
            self.close()
            show_login_flow()

    def load_company(self, name):
        if not name:
            QMessageBox.warning(self, "No Company", "Please create or select a company.")
            return
        set_current_company(name)
        self.company_label.setText(f"Company: {name}")
        try:
            with open("settings.json", "w") as f:
                json.dump({"current_company": name}, f)
        except:
            pass

        self.clear_content()
        self.build_sidebar()
        self.build_tabs()
        self.show()

    def clear_content(self):
        while self.content_area.count():
            item = self.content_area.takeAt(0)
            if w := item.widget():
                w.deleteLater()

    def build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setStyleSheet(get_widget_style())
        lay = QVBoxLayout(self.sidebar)
        lay.setContentsMargins(10, 20, 10, 20)
        lay.setSpacing(8)

        items = [
            ("Dashboard",     "dashboard.svg",        self.show_dashboard),
            ("Customers",     "person.svg",           self.show_customers),
            ("Vendors",       "local_shipping.svg",   lambda: self.tabs.setCurrentIndex(2)),
            ("Invoices",      "receipt_long.svg",     lambda: self.tabs.setCurrentIndex(3)),
            ("Bills",         "receipt.svg",          lambda: self.tabs.setCurrentIndex(4)),
            ("Transactions",  "swap_horiz.svg",       lambda: self.tabs.setCurrentIndex(5)),
            ("Bank Feeds",    "account_balance.svg",  lambda: self.tabs.setCurrentIndex(6)),
            ("Categories",    "category.svg",         lambda: self.tabs.setCurrentIndex(7)),
            ("Reports",       "bar_chart.svg",        lambda: self.tabs.setCurrentIndex(8)),
            ("Settings",      "settings.svg",         lambda: self.tabs.setCurrentIndex(9)),
            ("Payroll", "work.svg", lambda: self.tabs.setCurrentIndex(10)),
        ]

        self.side_buttons = []
        for txt, ico, func in items:
            b = QPushButton(f"  {txt}")
            b.setIcon(icon(ico))
            b.setIconSize(QSize(24, 24))
            b.setProperty("txt", f"  {txt}")
            b.clicked.connect(func)
            lay.addWidget(b)
            self.side_buttons.append(b)
        lay.addStretch()
        self.content_area.addWidget(self.sidebar)

    def build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.content_area.addWidget(self.tabs, 1)
        if not get_current_company():
            self.tabs.addTab(QLabel("<h3>Please create or select a company first.</h3>"), "Welcome")
            return

        self.tabs.addTab(self.create_dashboard(), "Dashboard")
        self.tabs.addTab(self.create_customers(), "Customers")
        self.tabs.addTab(QWidget(), "Vendors")
        self.tabs.addTab(QWidget(), "Invoices")
        self.tabs.addTab(QWidget(), "Bills")
        self.tabs.addTab(TransactionsTab(self), "Transactions")
        self.tabs.addTab(BankFeedsTab(self), "Bank Feeds")
        self.tabs.addTab(QWidget(), "Categories")
        self.tabs.addTab(QWidget(), "Reports")
       # self.tabs.addTab(SettingsTab(self), "Settings")
        self.tabs.addTab(PayrollTab(self), "Payroll")

    def create_dashboard(self):
        return Dashboard(self)

    def create_customers(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(20, 20, 20, 20)
        v.addWidget(QLabel("<h2>Customers</h2>"))
        self.cust_table = QTableWidget()
        self.cust_table.setColumnCount(4)
        self.cust_table.setHorizontalHeaderLabels(["ID", "Name", "Email", "Phone"])
        self.cust_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.cust_table)
        self.load_customers()
        return w

    def load_customers(self):
        try:
            conn = get_conn()
            rows = conn.execute("SELECT id, name, email, phone FROM customers").fetchall()
            # DO NOT close the persistent connection here!
            self.cust_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    self.cust_table.setItem(r, c, QTableWidgetItem(str(val or "")))
        except Exception as e:
            print("Load error:", e)

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        w = 70 if self.sidebar_collapsed else 230
        self.sidebar.setFixedWidth(w)
        self.sidebar_btn.setText("Expand" if self.sidebar_collapsed else "Collapse")
        for b in self.side_buttons:
            b.setText("" if self.sidebar_collapsed else b.property("txt"))

    def show_dashboard(self): self.tabs.setCurrentIndex(0)
    def show_customers(self): self.tabs.setCurrentIndex(1)

    def select_and_open_company(self, name):
        set_current_company(name)
        self.load_company(name)

    def refresh_all(self):
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, 'refresh_data'):
                tab.refresh_data()
        if hasattr(self, 'dashboard'):
            self.dashboard.refresh()


# ========================
# Global Flow
# ========================

def show_login_flow():
    login = LoginDialog()
    if login.exec() == QDialog.DialogCode.Accepted:
        selector = CompanySelector(None)
        if selector.exec() == QDialog.DialogCode.Accepted:
            win = NexLedgerPro()
            win.start()
        else:
            show_login_flow()
    else:
        sys.exit()


def closeEvent(self, event):
    from shared.db import close_all_dbs
    close_all_dbs()
    super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    show_login_flow()
    sys.exit(app.exec())
