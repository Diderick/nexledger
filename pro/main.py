# pro/main.py
import sys, csv, os, pandas as pd, re, time, shutil, json
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QDateEdit, QComboBox, QMessageBox, QHeaderView, QTabWidget,
    QFileDialog, QCheckBox, QInputDialog, QFrame, QDialog, QDialogButtonBox,
    QTreeWidget, QTreeWidgetItem, QSpinBox, QDoubleSpinBox, QTextEdit
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QIcon
import pyqtgraph as pg
from pyqtgraph import DateAxisItem
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
try:
    from ofxparse import OfxParser
    HAS_OFX = True
except ImportError:
    HAS_OFX = False
from shared.db import (
    set_current_company, get_current_company, get_conn, get_db_path,
    init_db_for_company, list_companies, is_duplicate_transaction
)


# ----------------------------------------------------------------------
# Helper – safe icon loader
# ----------------------------------------------------------------------
ICONS_DIR = os.path.join(os.path.dirname(__file__), "..", "icons")
def safe_icon(name):
    path = os.path.join(ICONS_DIR, name)
    return QIcon(path) if os.path.isfile(path) else QIcon()


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------
class NexLedgerPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexLedger Pro")
        self.setGeometry(100, 100, 1400, 800)
        self.setWindowIcon(safe_icon("dashboard.svg"))
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- TOP BAR ------------------------------------------------
        top_bar = QFrame()
        top_bar.setStyleSheet("background:#0078d4;padding:10px;")
        top_lay = QHBoxLayout(top_bar)
        self.company_label = QLabel("No Company")
        self.company_label.setStyleSheet("color:white;font-weight:bold;")
        top_lay.addWidget(self.company_label)
        top_lay.addStretch()
        self.dark_cb = QCheckBox("Dark Mode")
        self.dark_cb.setStyleSheet("color:white;")
        self.dark_cb.stateChanged.connect(self.toggle_theme)
        top_lay.addWidget(self.dark_cb)
        main_layout.addWidget(top_bar)

        # ---- CONTENT ------------------------------------------------
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)

        # ---- SIDEBAR ------------------------------------------------
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("background:#f1f3f4;border-right:1px solid #d0d0d0;")
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(10, 20, 10, 20)
        sb_lay.setSpacing(5)

        nav = [
            ("Open Company",   "folder_open.svg",      self.show_open_company),
            ("Dashboard",      "dashboard.svg",        self.show_dash),
            ("Customers",      "person.svg",           self.show_customers),
            ("Vendors",        "local_shipping.svg",   self.show_vendors),
            ("Invoices",       "receipt_long.svg",     self.show_invoices),
            ("Bills",          "receipt.svg",          self.show_bills),
            ("Transactions",   "swap_horiz.svg",       self.show_tx),
            ("Bank Feeds",     "account_balance.svg",  self.show_bank),
            ("Bank Accounts",  "account_balance_wallet.svg", self.show_bank_accounts),
            ("Categories",     "category.svg",         self.show_categories),
            ("Reports",        "bar_chart.svg",        self.show_reports),
            ("Settings",       "settings.svg",         self.show_settings),
        ]
        for txt, ico, cb in nav:
            btn = QPushButton()
            btn.setIcon(safe_icon(ico))
            btn.setText(f"  {txt}")
            btn.setStyleSheet("""
                QPushButton {text-align:left;padding:12px;border:none;border-radius:6px;
                             font-weight:bold;color:#2c2c2c;}
                QPushButton:hover {background:#e1e1e1;}
                QPushButton:pressed {background:#d0d0d0;}
            """)
            btn.clicked.connect(cb)
            sb_lay.addWidget(btn)
        sb_lay.addStretch()
        content.addWidget(sidebar)

        # ---- TABS ---------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet("QTabWidget::pane{border:none;}")
        content.addWidget(self.tabs, 1)

        # Create tabs
        self.open_comp_tab = self.create_open_company()
        self.dash_tab = self.create_dash()
        self.cust_tab = self.create_customers()
        self.vend_tab = self.create_vendors()
        self.inv_tab  = self.create_invoices()
        self.bill_tab = self.create_bills()
        self.tx_tab   = self.create_transactions()
        self.bank_tab = self.create_bank()
        self.ba_tab   = self.create_bank_accounts()
        self.cat_tab  = self.create_categories()
        self.rep_tab  = self.create_reports()
        self.set_tab  = self.create_settings()

        self.tabs.addTab(self.open_comp_tab, "")
        self.tabs.addTab(self.dash_tab, "")
        self.tabs.addTab(self.cust_tab, "")
        self.tabs.addTab(self.vend_tab, "")
        self.tabs.addTab(self.inv_tab,  "")
        self.tabs.addTab(self.bill_tab, "")
        self.tabs.addTab(self.tx_tab,   "")
        self.tabs.addTab(self.bank_tab, "")
        self.tabs.addTab(self.ba_tab,   "")
        self.tabs.addTab(self.cat_tab,  "")
        self.tabs.addTab(self.rep_tab,  "")
        self.tabs.addTab(self.set_tab,  "")

        main_layout.addLayout(content)

        # AUTO-OPEN LAST COMPANY
        self.load_last_company()

    # --------------------------------------------------------------
    # STYLES – FIXED LIGHT MODE TEXT + DARK MODE BUTTONS
    # --------------------------------------------------------------
    def apply_styles(self):
        self.light_style = """
            QWidget {font-family:'Segoe UI',sans-serif; color: #000000;}
            QLineEdit,QComboBox,QDateEdit,QTextEdit {padding:8px;border:1px solid #ccc;border-radius:4px;background:white;}
            QPushButton {background:#007bff;color:white;border:none;padding:10px 16px;
                         border-radius:6px;font-weight:bold;}
            QPushButton:hover {background:#0056b3;}
            QTableWidget {border:1px solid #ddd;gridline-color:#eee;
                          alternate-background-color:#f9f9f9;color:#000000;}
            QTableWidget::item:hover {background:#e3f2fd;}
            QLabel {color:#000000;}
        """
        self.dark_style = """
            QWidget {background:#1e1e1e;color:#ffffff;}
            QLineEdit,QComboBox,QDateEdit,QTextEdit {background:#333;color:#fff;border:1px solid #555;}
            QPushButton {background:#0d6efd;color:white;border:none;padding:10px 16px;
                         border-radius:6px;font-weight:bold;}
            QPushButton:hover {background:#0b5ed7;}
            QTableWidget {background:#2d2d2e;color:#eee;gridline-color:#444;}
            QTableWidget::item:hover {background:#1a3a5f;}
            QLabel {color:#ffffff;}
        """
        self.setStyleSheet(self.light_style)

    def toggle_theme(self, state):
        self.setStyleSheet(self.dark_style if state else self.light_style)
        if hasattr(self, 'chart'):
            self.chart.setBackground('#2d2d2e' if state else 'w')

    # --------------------------------------------------------------
    # OPEN COMPANY TAB
    # --------------------------------------------------------------
    def create_open_company(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)

        title = QLabel("<h2>Select or Create Company</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        self.comp_table = QTableWidget()
        self.comp_table.setColumnCount(1)
        self.comp_table.setHorizontalHeaderLabels(["Company Name"])
        self.comp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.comp_table)

        btn_lay = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self.open_selected_company)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.show_dash)
        self.manage_btn = QPushButton("Manage")
        self.manage_btn.clicked.connect(self.manage_companies)
        self.add_btn = QPushButton("Add Company")
        self.add_btn.clicked.connect(self.add_company)

        for b in [self.open_btn, self.cancel_btn, self.manage_btn, self.add_btn]:
            b.setStyleSheet("padding:10px;font-weight:bold;")
            btn_lay.addWidget(b)
        lay.addLayout(btn_lay)

        self.auto_cb = QCheckBox("Open last used company on startup")
        self.auto_cb.setChecked(True)
        lay.addWidget(self.auto_cb)

        self.refresh_company_list()
        return w

    def refresh_company_list(self):
        companies = list_companies()
        self.comp_table.setRowCount(len(companies))
        for i, name in enumerate(companies):
            self.comp_table.setItem(i, 0, QTableWidgetItem(name))

    def add_company(self):
        name, ok = QInputDialog.getText(self, "New Company", "Company Name:")
        if not ok or not name.strip(): return
        name = name.strip()
        if name in list_companies():
            QMessageBox.warning(self, "Error", "Company already exists")
            return
        init_db_for_company(name)
        self.refresh_company_list()

    def open_selected_company(self):
        row = self.comp_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Error", "Select a company")
            return
        name = self.comp_table.item(row, 0).text()
        set_current_company(name)
        self.company_label.setText(f"Company: {name}")
        self.tabs.setCurrentIndex(1)  # Dashboard
        self.refresh_all()

    def manage_companies(self):
        row = self.comp_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Error", "Select a company")
            return
        name = self.comp_table.item(row, 0).text()
        action, ok = QInputDialog.getItem(self, "Manage Company", "Action:", ["Rename", "Delete"], 0, False)
        if not ok: return

        if action == "Rename":
            new_name, ok = QInputDialog.getText(self, "Rename", "New Name:", text=name)
            if not ok or not new_name.strip(): return
            new_name = new_name.strip()
            if new_name in list_companies():
                QMessageBox.warning(self, "Error", "Name exists")
                return
            (COMPANIES_DIR / name).rename(COMPANIES_DIR / new_name)
            if get_current_company() == name:
                set_current_company(new_name)
                self.company_label.setText(f"Company: {new_name}")
            self.refresh_company_list()

        elif action == "Delete":
            reply = QMessageBox.question(self, "Delete", f"Delete '{name}' and all data?\nThis cannot be undone.",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                shutil.rmtree(COMPANIES_DIR / name, ignore_errors=True)
                if get_current_company() == name:
                    set_current_company(None)
                    self.company_label.setText("No Company")
                self.refresh_company_list()

    def load_last_company(self):
        if not Path("settings.json").exists():
            self.show_open_company()
            return
        with open("settings.json") as f:
            data = json.load(f)
        last = data.get("last_company")
        if last and last in list_companies():
            set_current_company(last)
            self.company_label.setText(f"Company: {last}")
            self.tabs.setCurrentIndex(1)
            self.refresh_all()
        else:
            self.show_open_company()

    def refresh_all(self):
        self.refresh_dash()
        self.load_customers()
        self.load_vendors()
        self.load_invoices()
        self.load_tx()
        self.load_bank_accounts()
        self.load_categories()
        self.refresh_report()

    # --------------------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------------------
    def create_dash(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        cards = QHBoxLayout()
        self.card_inc = self.make_card()
        self.card_exp = self.make_card()
        self.card_bal = self.make_card()
        cards.addWidget(self.card_inc)
        cards.addWidget(self.card_exp)
        cards.addWidget(self.card_bal)
        lay.addLayout(cards)
        self.chart = pg.PlotWidget(axisItems={'bottom': DateAxisItem()})
        self.chart.setBackground('w')
        self.chart.showGrid(x=True, y=True)
        lay.addWidget(self.chart, 1)
        return w

    def make_card(self):
        frame = QFrame()
        frame.setStyleSheet("background:white;border:1px solid #ddd;border-radius:8px;padding:15px;margin:5px;")
        layout = QVBoxLayout(frame)
        title = QLabel()
        val_lbl = QLabel("R0.00")
        val_lbl.setStyleSheet("font-size:20px;font-weight:bold;")
        layout.addWidget(title)
        layout.addWidget(val_lbl)
        frame.title_lbl = title
        frame.val_lbl = val_lbl
        return frame

    def refresh_dash(self):
        try:
            conn = get_conn()
            inc = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='Income'").fetchone()[0] or 0
            exp = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='Expense'").fetchone()[0] or 0
            conn.close()
            self.card_inc.title_lbl.setText("<b>Total Income</b>")
            self.card_inc.val_lbl.setText(f"R{inc:,.2f}")
            self.card_inc.val_lbl.setStyleSheet("font-size:20px;color:#28a745;font-weight:bold;")
            self.card_exp.title_lbl.setText("<b>Total Expenses</b>")
            self.card_exp.val_lbl.setText(f"R{exp:,.2f}")
            self.card_exp.val_lbl.setStyleSheet("font-size:20px;color:#dc3545;font-weight:bold;")
            self.card_bal.title_lbl.setText("<b>Net Balance</b>")
            self.card_bal.val_lbl.setText(f"R{inc-exp:,.2f}")
            self.card_bal.val_lbl.setStyleSheet("font-size:20px;color:#007bff;font-weight:bold;")

            conn = get_conn()
            rows = conn.execute("SELECT date, SUM(CASE WHEN type='Income' THEN amount ELSE -amount END) AS net FROM transactions GROUP BY date ORDER BY date").fetchall()
            conn.close()
            if not rows:
                self.chart.clear()
                return
            dates_str = [r["date"] for r in rows]
            nets = [r["net"] for r in rows]
            x_timestamps = [int(time.mktime(time.strptime(d, "%Y-%m-%d"))) for d in dates_str]
            self.chart.clear()
            self.chart.plot(x_timestamps, nets, pen=pg.mkPen('#007bff', width=3), symbol='o', symbolBrush='#007bff', symbolSize=8)
        except Exception as e:
            print(f"Dashboard error: {e}")

    # --------------------------------------------------------------
    # CUSTOMERS
    # --------------------------------------------------------------
    def create_customers(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        form = QGridLayout()
        self.c_name  = QLineEdit()
        self.c_email = QLineEdit()
        self.c_phone = QLineEdit()
        add = QPushButton("Add Customer")
        add.clicked.connect(self.add_customer)
        for i, (lbl, wid) in enumerate([("Name*",self.c_name),("Email",self.c_email),("Phone",self.c_phone)]):
            form.addWidget(QLabel(lbl), i, 0)
            form.addWidget(wid, i, 1)
        form.addWidget(add, 3, 1)
        lay.addLayout(form)
        self.c_table = QTableWidget()
        self.c_table.setColumnCount(4)
        self.c_table.setHorizontalHeaderLabels(["ID","Name","Email","Phone"])
        self.c_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.c_table)
        self.load_customers()
        return w

    def add_customer(self):
        name = self.c_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Name required")
            return
        conn = get_conn()
        conn.execute("INSERT INTO customers (name,email,phone) VALUES (?,?,?)",
                     (name, self.c_email.text(), self.c_phone.text()))
        conn.commit()
        conn.close()
        self.c_name.clear(); self.c_email.clear(); self.c_phone.clear()
        self.load_customers()

    def load_customers(self):
        try:
            conn = get_conn()
            rows = conn.execute("SELECT id,name,email,phone FROM customers").fetchall()
            conn.close()
            self.c_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, v in enumerate(row):
                    self.c_table.setItem(r, c, QTableWidgetItem(str(v)))
        except Exception as e:
            print(f"Customers error: {e}")

    # --------------------------------------------------------------
    # VENDORS
    # --------------------------------------------------------------
    def create_vendors(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        form = QGridLayout()
        self.v_name  = QLineEdit()
        self.v_email = QLineEdit()
        self.v_phone = QLineEdit()
        add = QPushButton("Add Vendor")
        add.clicked.connect(self.add_vendor)
        for i, (lbl, wid) in enumerate([("Name*",self.v_name),("Email",self.v_email),("Phone",self.v_phone)]):
            form.addWidget(QLabel(lbl), i, 0)
            form.addWidget(wid, i, 1)
        form.addWidget(add, 3, 1)
        lay.addLayout(form)
        self.v_table = QTableWidget()
        self.v_table.setColumnCount(4)
        self.v_table.setHorizontalHeaderLabels(["ID","Name","Email","Phone"])
        self.v_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.v_table)
        self.load_vendors()
        return w

    def add_vendor(self):
        name = self.v_name.text().strip()
        if not name: return
        conn = get_conn()
        conn.execute("INSERT INTO vendors (name,email,phone) VALUES (?,?,?)",
                     (name, self.v_email.text(), self.v_phone.text()))
        conn.commit()
        conn.close()
        self.v_name.clear(); self.v_email.clear(); self.v_phone.clear()
        self.load_vendors()

    def load_vendors(self):
        try:
            conn = get_conn()
            rows = conn.execute("SELECT id,name,email,phone FROM vendors").fetchall()
            conn.close()
            self.v_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, v in enumerate(row):
                    self.v_table.setItem(r, c, QTableWidgetItem(str(v)))
        except Exception as e:
            print(f"Vendors error: {e}")

    # --------------------------------------------------------------
    # INVOICES
    # --------------------------------------------------------------
    def create_invoices(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        new_btn = QPushButton("Create New Invoice")
        new_btn.clicked.connect(self.new_invoice)
        lay.addWidget(new_btn)
        self.i_table = QTableWidget()
        self.i_table.setColumnCount(6)
        self.i_table.setHorizontalHeaderLabels(["Inv#","Customer","Date","Due","Total","Status"])
        self.i_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.i_table.itemDoubleClicked.connect(self.edit_invoice)
        lay.addWidget(self.i_table)
        self.load_invoices()
        return w

    def new_invoice(self):
        try:
            custs = get_conn().execute("SELECT id,name FROM customers").fetchall()
            if not custs:
                QMessageBox.warning(self, "No customers", "Add a customer first.")
                return
            items = [f"{c['name']} ({c['id']})" for c in custs]
            choice, ok = QInputDialog.getItem(self, "Select Customer", "Customer:", items, 0, False)
            if not ok: return
            cust_id = int(choice.split("(")[-1].strip(")"))
            inv_no = datetime.now().strftime("%Y%m%d-%H%M%S")
            date = QDate.currentDate().toString("yyyy-MM-dd")
            due  = QDate.currentDate().addDays(30).toString("yyyy-MM-dd")
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO invoices (customer_id,invoice_no,date,due_date,total) VALUES (?,?,?,?,?)",
                        (cust_id, inv_no, date, due, 0))
            inv_id = cur.lastrowid
            conn.commit()
            conn.close()
            self.edit_invoice_detail(inv_id)
        except Exception as e:
            print(f"Invoice error: {e}")

    def edit_invoice_detail(self, inv_id):
        dlg = InvoiceEditor(inv_id, self)
        dlg.exec()
        self.load_invoices()
        self.refresh_dash()

    def edit_invoice(self, item):
        row = item.row()
        inv_no = self.i_table.item(row, 0).text()
        inv_id = get_conn().execute("SELECT id FROM invoices WHERE invoice_no=?", (inv_no,)).fetchone()[0]
        self.edit_invoice_detail(inv_id)

    def load_invoices(self):
        try:
            conn = get_conn()
            rows = conn.execute("""
                SELECT i.id,  i.invoice_no, c.name, i.date, i.due_date, i.total, i.status
                FROM invoices i LEFT JOIN customers c ON i.customer_id=c.id
                ORDER BY i.date DESC
            """).fetchall()
            conn.close()
            self.i_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self.i_table.setItem(r,0,QTableWidgetItem(row["invoice_no"]))
                self.i_table.setItem(r,1,QTableWidgetItem(row["name"] or ""))
                self.i_table.setItem(r,2,QTableWidgetItem(row["date"]))
                self.i_table.setItem(r,3,QTableWidgetItem(row["due_date"]))
                self.i_table.setItem(r,4,QTableWidgetItem(f"R{row['total']:.2f}"))
                self.i_table.setItem(r,5,QTableWidgetItem(row["status"]))
        except Exception as e:
            print(f"Invoices error: {e}")

    # --------------------------------------------------------------
    # BILLS
    # --------------------------------------------------------------
    def create_bills(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        new_btn = QPushButton("Create New Bill")
        new_btn.clicked.connect(self.new_bill)
        lay.addWidget(new_btn)
        self.b_table = QTableWidget()
        self.b_table.setColumnCount(6)
        self.b_table.setHorizontalHeaderLabels(["Bill#","Vendor","Date","Due","Total","Status"])
        self.b_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.b_table)
        self.load_bills()
        return w

    def new_bill(self):
        # Similar to new_invoice but for vendors
        try:
            vendors = get_conn().execute("SELECT id,name FROM vendors").fetchall()
            if not vendors:
                QMessageBox.warning(self, "No vendors", "Add a vendor first.")
                return
            items = [f"{v['name']} ({v['id']})" for v in vendors]
            choice, ok = QInputDialog.getItem(self, "Select Vendor", "Vendor:", items, 0, False)
            if not ok: return
            vendor_id = int(choice.split("(")[-1].strip(")"))
            bill_no = datetime.now().strftime("%Y%m%d-%H%M%S")
            date = QDate.currentDate().toString("yyyy-MM-dd")
            due  = QDate.currentDate().addDays(30).toString("yyyy-MM-dd")
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO bills (vendor_id,bill_no,date,due_date,total) VALUES (?,?,?,?,?)",
                        (vendor_id, bill_no, date, due, 0))
            bill_id = cur.lastrowid
            conn.commit()
            conn.close()
            self.edit_bill_detail(bill_id)
        except Exception as e:
            print(f"Bill error: {e}")

    def edit_bill_detail(self, bill_id):
        # Similar to InvoiceEditor
        dlg = BillEditor(bill_id, self)
        dlg.exec()
        self.load_bills()
        self.refresh_dash()

    def load_bills(self):
        try:
            conn = get_conn()
            rows = conn.execute("""
                SELECT b.id, b.bill_no, v.name, b.date, b.due_date, b.total, b.status
                FROM bills b LEFT JOIN vendors v ON b.vendor_id=v.id
                ORDER BY b.date DESC
            """).fetchall()
            conn.close()
            self.b_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self.b_table.setItem(r,0,QTableWidgetItem(row["bill_no"]))
                self.b_table.setItem(r,1,QTableWidgetItem(row["name"] or ""))
                self.b_table.setItem(r,2,QTableWidgetItem(row["date"]))
                self.b_table.setItem(r,3,QTableWidgetItem(row["due_date"]))
                self.b_table.setItem(r,4,QTableWidgetItem(f"R{row['total']:.2f}"))
                self.b_table.setItem(r,5,QTableWidgetItem(row["status"]))
        except Exception as e:
            print(f"Bills error: {e}")

    # --------------------------------------------------------------
    # TRANSACTIONS
    # --------------------------------------------------------------
    def create_transactions(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        form = QGridLayout()
        self.tx_date = QDateEdit(calendarPopup=True); self.tx_date.setDate(QDate.currentDate())
        self.tx_desc = QLineEdit()
        self.tx_amt  = QLineEdit()
        self.tx_typ  = QComboBox(); self.tx_typ.addItems(["Income","Expense"])
        add = QPushButton("Add")
        add.clicked.connect(self.add_tx)
        for i, (lbl, wid) in enumerate([("Date",self.tx_date),("Desc",self.tx_desc),("Amt",self.tx_amt),("Type",self.tx_typ)]):
            form.addWidget(QLabel(lbl), i, 0)
            form.addWidget(wid, i, 1)
        form.addWidget(add, 4, 1)
        lay.addLayout(form)
        self.tx_table = QTableWidget()
        self.tx_table.setColumnCount(5)
        self.tx_table.setHorizontalHeaderLabels(["Date","Desc","Amount","Type","Link"])
        self.tx_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tx_table)
        self.load_tx()
        return w

    def add_tx(self):
        try:
            amt = float(self.tx_amt.text())
        except:
            QMessageBox.warning(self, "Error", "Invalid amount")
            return
        if not self.tx_desc.text().strip():
            QMessageBox.warning(self, "Error", "Description required")
            return
        conn = get_conn()
        conn.execute("INSERT INTO transactions (date,description,amount,type) VALUES (?,?,?,?)",
                     (self.tx_date.date().toString("yyyy-MM-dd"),
                      self.tx_desc.text(), amt, self.tx_typ.currentText()))
        conn.commit()
        conn.close()
        self.tx_desc.clear(); self.tx_amt.clear()
        self.load_tx()
        self.refresh_dash()

    def load_tx(self):
        try:
            conn = get_conn()
            rows = conn.execute("SELECT date,description,amount,type,linked_id FROM transactions ORDER BY date DESC").fetchall()
            conn.close()
            self.tx_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self.tx_table.setItem(r,0,QTableWidgetItem(row["date"]))
                self.tx_table.setItem(r,1,QTableWidgetItem(row["description"]))
                self.tx_table.setItem(r,2,QTableWidgetItem(f"R{row['amount']:.2f}"))
                self.tx_table.setItem(r,3,QTableWidgetItem(row["type"]))
                self.tx_table.setItem(r,4,QTableWidgetItem(str(row["linked_id"]) if row["linked_id"] else ""))
        except Exception as e:
            print(f"Transactions error: {e}")

    # --------------------------------------------------------------
    # BANK FEEDS
    # --------------------------------------------------------------
    def create_bank(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        upload = QPushButton("Import Bank File (CSV/PDF/OFX)")
        upload.clicked.connect(self.import_bank_file)
        upload.setStyleSheet("font-size: 16px; padding: 12px;")
        lay.addWidget(upload)
        sup = QLabel("""
        <b>Supported:</b><br>
        • CSV (FNB, Standard Bank)<br>
        • PDF (FNB Statements)<br>
        • OFX (FNB/Standard Bank)<br><br>
        <b>Currency:</b> ZAR (R) – auto-detected
        """)
        sup.setWordWrap(True)
        lay.addWidget(sup)
        self.bank_table = QTableWidget()
        self.bank_table.setColumnCount(4)
        self.bank_table.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Status"])
        self.bank_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.bank_table)
        return w

    def import_bank_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Bank File", "",
                                             "All Supported (*.csv *.pdf *.ofx);;CSV (*.csv);;PDF (*.pdf);;OFX (*.ofx)")
        if not path: return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.csv':
                df = self.parse_csv(path)
            elif ext == '.pdf' and HAS_PDF:
                df = self.parse_pdf(path)
            elif ext == '.ofx' and HAS_OFX:
                df = self.parse_ofx(path)
            else:
                raise ValueError("Unsupported format.")
            if df is None or df.empty:
                raise ValueError("No transactions found.")
            df = self.clean_bank_data(df)
            dlg = BankImportDialog(df, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.do_import_bank(df)
                self.show_tx()
                self.refresh_dash()
                QMessageBox.information(self, "Success", f"Imported {len(df)} transactions!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Import failed: {str(e)}")

    def clean_bank_data(self, df):
        def parse_date(d):
            try:
                return pd.to_datetime(d, dayfirst=True).strftime('%Y-%m-%d')
            except:
                return None
        df['Date'] = df['Date'].apply(parse_date)
        df = df.dropna(subset=['Date'])
        def parse_amount(a):
            a = str(a).strip()
            a = re.sub(r'[^\d.-]', '', a)
            try:
                return float(a)
            except:
                return 0.0
        df['Amount'] = df['Amount'].apply(parse_amount)
        df['Type'] = df['Amount'].apply(lambda x: 'Income' if x > 0 else 'Expense')
        df['Description'] = df['Description'].str.strip()
        return df[['Date', 'Description', 'Amount', 'Type']].dropna()

    def parse_csv(self, path):
        df = pd.read_csv(path, skiprows=10)
        if len(df.columns) >= 4:
            df.columns = ['Date', 'Description', 'ServiceFee', 'Amount', 'Balance'][:len(df.columns)]
        return df

    def parse_pdf(self, path):
        doc = fitz.open(path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        data = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(r'\d{1,2}\s[A-Za-z]{3}\s\d{4}', line):
                date = line.split()[0] + " " + line.split()[1] + " " + line.split()[2]
                desc = []
                i += 1
                while i < len(lines) and not re.match(r'\d{1,2}\s[A-Za-z]{3}\s\d{4}', lines[i]):
                    if any(x in lines[i] for x in ['CR', 'DR', '0.00']):
                        amount_line = lines[i]
                        break
                    desc.append(lines[i])
                    i += 1
                else:
                    continue
                desc = ' '.join(desc).strip()
                amount_match = re.search(r'([+-]?\d+\.\d+)\s*(CR|DR)?', amount_line)
                amount = amount_match.group(1) if amount_match else "0.00"
                data.append([date, desc or "Unknown", amount])
            else:
                i += 1
        return pd.DataFrame(data, columns=['Date', 'Description', 'Amount'])

    def parse_ofx(self, path):
        with open(path, 'r', encoding='latin-1') as f:
            ofx = OfxParser.parse(f)
        txns = ofx.account.statement.transactions
        data = []
        for t in txns:
            date = t.date.strftime('%Y-%m-%d')
            desc = t.memo or "Unknown"
            amount = float(t.amount)
            data.append([date, desc, amount])
        return pd.DataFrame(data, columns=['Date', 'Description', 'Amount'])

    def do_import_bank(self, df):
        conn = get_conn()
        imported = 0
        for _, row in df.iterrows():
            if is_duplicate_transaction(row['Date'], row['Description']):
                continue
            conn.execute(
                "INSERT INTO transactions (date, description, amount, type) VALUES (?, ?, ?, ?)",
                (row['Date'], row['Description'], abs(row['Amount']), row['Type'])
            )
            imported += 1
        conn.commit()
        conn.close()

    # --------------------------------------------------------------
    # BANK ACCOUNTS
    # --------------------------------------------------------------
    def create_bank_accounts(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20,20,20,20)
        add = QPushButton("Add / Import New Account")
        add.clicked.connect(self.import_bank_file)
        lay.addWidget(add)
        self.ba_table = QTableWidget()
        self.ba_table.setColumnCount(6)
        self.ba_table.setHorizontalHeaderLabels(["ID","Name","Number","Type","Balance","Last Sync"])
        self.ba_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.ba_table)
        self.load_bank_accounts()
        return w

    def load_bank_accounts(self):
        try:
            conn = get_conn()
            rows = conn.execute("SELECT * FROM bank_accounts").fetchall()
            conn.close()
            self.ba_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, v in enumerate(row):
                    self.ba_table.setItem(r, c, QTableWidgetItem(str(v)))
        except Exception as e:
            print(f"Bank accounts error: {e}")

    # --------------------------------------------------------------
    # CATEGORIES
    # --------------------------------------------------------------
    def create_categories(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20,20,20,20)
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderLabels(["Name", "Type"])
        lay.addWidget(self.cat_tree)
        self.load_categories()
        return w

    def load_categories(self):
        try:
            self.cat_tree.clear()
            conn = get_conn()
            rows = conn.execute("SELECT id, parent_id, name, type FROM categories").fetchall()
            conn.close()
            items = {}
            for row in rows:
                item = QTreeWidgetItem([row["name"], row["type"]])
                items[row["id"]] = item
                if row["parent_id"]:
                    parent = items.get(row["parent_id"])
                    if parent:
                        parent.addChild(item)
                else:
                    self.cat_tree.addTopLevelItem(item)
        except Exception as e:
            print(f"Categories error: {e}")

    # --------------------------------------------------------------
    # REPORTS
    # --------------------------------------------------------------
    def create_reports(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20,20,20,20)
        exp = QPushButton("Export Transactions to CSV")
        exp.clicked.connect(self.export_csv)
        lay.addWidget(exp)
        self.rep_table = QTableWidget()
        self.rep_table.setColumnCount(4)
        self.rep_table.setHorizontalHeaderLabels(["Date","Desc","Amt","Type"])
        self.rep_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.rep_table)
        self.refresh_report()
        return w

    def refresh_report(self):
        try:
            conn = get_conn()
            rows = conn.execute("SELECT date,description,amount,type FROM transactions ORDER BY date").fetchall()
            conn.close()
            self.rep_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self.rep_table.setItem(r,0,QTableWidgetItem(row["date"]))
                self.rep_table.setItem(r,1,QTableWidgetItem(row["description"]))
                self.rep_table.setItem(r,2,QTableWidgetItem(f"R{row['amount']:.2f}"))
                self.rep_table.setItem(r,3,QTableWidgetItem(row["type"]))
        except Exception as e:
            print(f"Reports error: {e}")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "transactions.csv", "CSV (*.csv)")
        if path:
            try:
                conn = get_conn()
                rows = conn.execute("SELECT date,description,amount,type FROM transactions ORDER BY date").fetchall()
                conn.close()
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Date","Description","Amount","Type"])
                    for r in rows:
                        w.writerow([r["date"], r["description"], r["amount"], r["type"]])
                QMessageBox.information(self, "Done", "Exported!")
            except Exception as e:
                print(f"Export error: {e}")

    # --------------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------------
    def create_settings(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20,20,20,20)
        backup = QPushButton("Backup Database")
        backup.clicked.connect(self.backup_db)
        lay.addWidget(backup)
        return w

    def backup_db(self):
        path, _ = QFileDialog.getExistingDirectory(self, "Select Backup Folder")
        if path:
            try:
                db_path = get_db_path()
                shutil.copy(db_path, os.path.join(path, f"nexledger_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"))
                QMessageBox.information(self, "Done", "Backup created!")
            except Exception as e:
                print(f"Backup error: {e}")

    # --------------------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------------------
    def show_open_company(self): self.tabs.setCurrentIndex(0); self.refresh_company_list()
    def show_dash(self):         self.tabs.setCurrentIndex(1); self.refresh_dash()
    def show_customers(self):    self.tabs.setCurrentIndex(2); self.load_customers()
    def show_vendors(self):      self.tabs.setCurrentIndex(3); self.load_vendors()
    def show_invoices(self):     self.tabs.setCurrentIndex(4); self.load_invoices()
    def show_bills(self):        self.tabs.setCurrentIndex(5); self.load_bills()
    def show_tx(self):           self.tabs.setCurrentIndex(6); self.load_tx()
    def show_bank(self):         self.tabs.setCurrentIndex(7)
    def show_bank_accounts(self): self.tabs.setCurrentIndex(8); self.load_bank_accounts()
    def show_categories(self):   self.tabs.setCurrentIndex(9); self.load_categories()
    def show_reports(self):      self.tabs.setCurrentIndex(10); self.refresh_report()
    def show_settings(self):     self.tabs.setCurrentIndex(11)

    # --------------------------------------------------------------
    # Dialogs
    # --------------------------------------------------------------
class BankImportDialog(QDialog):
    def __init__(self, df, parent):
        super().__init__(parent)
        self.setWindowTitle("Import Preview")
        self.setModal(True)
        self.resize(800, 400)
        lay = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)
        self.table.setRowCount(len(df))
        for r, (_, row) in enumerate(df.iterrows()):
            self.table.setItem(r, 0, QTableWidgetItem(row['Date']))
            self.table.setItem(r, 1, QTableWidgetItem(row['Description']))
            self.table.setItem(r, 2, QTableWidgetItem(f"R{row['Amount']:.2f}"))
            self.table.setItem(r, 3, QTableWidgetItem(row['Type']))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

class InvoiceEditor(QDialog):
    def __init__(self, inv_id, parent):
        super().__init__(parent)
        self.inv_id = inv_id
        self.setWindowTitle("Edit Invoice")
        self.setModal(True)
        self.resize(700, 500)
        lay = QVBoxLayout(self)
        inv = get_conn().execute("SELECT invoice_no,date FROM invoices WHERE id=?", (inv_id,)).fetchone()
        lay.addWidget(QLabel(f"<b>Invoice {inv['invoice_no']} – {inv['date']}</b>"))
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Description","Qty","Price","Line Total",""])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)
        add = QPushButton("Add Line")
        add.clicked.connect(self.add_row)
        lay.addWidget(add)
        export = QPushButton("Export PDF")
        export.clicked.connect(self.export_pdf)
        lay.addWidget(export)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.load_items()
        self.table.cellChanged.connect(self.recalc)

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r,0,QTableWidgetItem(""))
        self.table.setItem(r,1,QTableWidgetItem("1"))
        self.table.setItem(r,2,QTableWidgetItem("0.00"))
        self.table.setItem(r,3,QTableWidgetItem("0.00"))
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(lambda: self.table.removeRow(self.table.row(del_btn)))
        self.table.setCellWidget(r,4,del_btn)

    def recalc(self, row, col):
        try:
            qty = float(self.table.item(row,1).text() or 0)
            price = float(self.table.item(row,2).text() or 0)
            self.table.item(row,3).setText(f"{qty*price:.2f}")
        except: pass

    def load_items(self):
        try:
            items = get_conn().execute("SELECT description,qty,price FROM invoice_items WHERE invoice_id=?", (self.inv_id,)).fetchall()
            self.table.setRowCount(len(items))
            for r, it in enumerate(items):
                self.table.setItem(r,0,QTableWidgetItem(it["description"]))
                self.table.setItem(r,1,QTableWidgetItem(str(it["qty"])))
                self.table.setItem(r,2,QTableWidgetItem(f"{it['price']:.2f}"))
                self.table.setItem(r,3,QTableWidgetItem(f"{it['qty']*it['price']:.2f}"))
                del_btn = QPushButton("Delete")
                del_btn.clicked.connect(lambda _, rr=r: self.table.removeRow(rr))
                self.table.setCellWidget(r,4,del_btn)
        except Exception as e:
            print(f"Load items error: {e}")

    def save(self):
        total = 0.0
        lines = []
        for r in range(self.table.rowCount()):
            desc = self.table.item(r,0).text().strip()
            if not desc: continue
            qty   = float(self.table.item(r,1).text() or 0)
            price = float(self.table.item(r,2).text() or 0)
            line  = qty*price
            total += line
            lines.append((desc, qty, price))
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM invoice_items WHERE invoice_id=?", (self.inv_id,))
            for d,q,p in lines:
                cur.execute("INSERT INTO invoice_items (invoice_id,description,qty,price) VALUES (?,?,?,?)",
                            (self.inv_id, d, q, p))
            cur.execute("UPDATE invoices SET total=? WHERE id=?", (total, self.inv_id))
            conn.commit()
            conn.close()
            self.accept()
        except Exception as e:
            print(f"Save invoice error: {e}")

    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"invoice_{self.inv_id}.pdf", "PDF (*.pdf)")
        if not path: return
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            doc = SimpleDocTemplate(path, pagesize=A4)
            elements = []
            styles = getSampleStyleSheet()
            elements.append(Paragraph(f"<b>INVOICE {self.inv_id}</b>", styles['Title']))
            elements.append(Spacer(1, 12))
            inv = get_conn().execute("SELECT invoice_no, date, due_date, total, status FROM invoices WHERE id=?", (self.inv_id,)).fetchone()
            elements.append(Paragraph(f"Date: {inv['date']} | Due: {inv['due_date']} | Status: {inv['status']}", styles['Normal']))
            elements.append(Spacer(1, 20))
            items = get_conn().execute("SELECT description, qty, price, qty*price as line FROM invoice_items WHERE invoice_id=?", (self.inv_id,)).fetchall()
            data = [["Description", "Qty", "Price", "Line Total"]]
            for i in items:
                data.append([i['description'], str(i['qty']), f"R{i['price']:.2f}", f"R{i['line']:.2f}"])
            data.append(["", "", "TOTAL", f"R{inv['total']:.2f}"])
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#007bff')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('ALIGN', (1,-1), (-1,-1), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('BACKGROUND', (-2,-1), (-1,-1), colors.HexColor('#f0f0f0')),
            ]))
            elements.append(table)
            doc.build(elements)
            QMessageBox.information(self, "Success", f"PDF saved: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"PDF export failed: {e}")

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = NexLedgerPro()
    win.show()
    sys.exit(app.exec())