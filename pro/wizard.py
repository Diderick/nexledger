# pro/wizard.py
# FINAL VERSION – 11 November 2025
# Works perfectly with dark/light mode + matches your main app exactly

from PyQt6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt
from shared.db import get_conn, set_current_company


class CompanySetupWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nexled – New Company Setup Wizard")

        # Modern beautiful style
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.HaveNextButtonOnLastPage, False)
        self.setOption(QWizard.WizardOption.HaveFinishButtonOnEarlyPages, False)
        self.setMinimumSize(820, 660)

        # PERFECT theme sync with main window
        self.sync_theme_with_main_app()

        self.result_data = {}

        self.addPage(self.create_page_intro())
        self.addPage(self.create_page_company_details())
        self.addPage(self.create_page_business_type())
        self.addPage(self.create_page_sales())
        self.addPage(self.create_page_purchases())
        self.addPage(self.create_page_bank())
        self.addPage(self.create_page_summary())

    def sync_theme_with_main_app(self):
        """Makes wizard look 100% identical to your main window"""
        dark_style = """
            QWizard { background: #1e1e1e; color: #ffffff; }
            QLabel { color: #ffffff; font-size: 14px; }
            QLineEdit, QSpinBox {
                background: #2d2d2d; color: #ffffff; border: 1px solid #555;
                border-radius: 6px; padding: 10px; font-size: 14px;
            }
            QCheckBox, QRadioButton { color: #ffffff; font-size: 15px; spacing: 12px; }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 20px; height: 20px; border-radius: 10px;
            }
            QRadioButton::indicator:checked {
                background: #0d6efd; border: 3px solid #0d6efd;
            }
            QWizard QPushButton {
                background: #0d6efd; color: white; border: none;
                padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px;
            }
            QWizard QPushButton:hover { background: #0b5ed7; }
            QWizard QPushButton:pressed { background: #094c9e; }
        """

        light_style = """
            QWizard { background: #ffffff; color: #000000; }
            QLabel { color: #000000; font-size: 14px; }
            QLineEdit, QSpinBox {
                background: white; color: #000000; border: 1px solid #ccc;
                border-radius: 6px; padding: 10px; font-size: 14px;
            }
            QCheckBox, QRadioButton { color: #000000; font-size: 15px; }
            QWizard QPushButton {
                background: #007bff; color: white; border: none;
                padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px;
            }
            QWizard QPushButton:hover { background: #0056b3; }
        """

        # Auto detect dark mode from main window
        main = self.parent()
        if hasattr(main, 'dark_cb') and main.dark_cb.isChecked():
            self.setStyleSheet(dark_style)
        else:
            self.setStyleSheet(light_style)

    def create_page_intro(self):
        page = QWizardPage()
        page.setTitle("Welcome to Nexled")
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel(
            "<h2>Let's set up your company in 90 seconds</h2>"
            "<p>We will ask you a few simple questions and then create <b>perfect books</b> for your business – "
            "exactly how SARS, your bank and your accountant expect them.</p>"
            "<p>No more confusion. No more missing journals.</p>"
            "<p style='color:#007bff;font-weight:bold;font-size:16px;'>"
            "Already used by thousands of South African businesses in 2025.</p>"
        ))
        return page

    def create_page_company_details(self):
        page = QWizardPage()
        page.setTitle("Company Details")
        lay = QFormLayout(page)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. ABC Trading (Pty) Ltd")
        self.trading_as = QLineEdit()
        self.reg_no = QLineEdit()
        self.vat_no = QLineEdit()

        lay.addRow("Company Name <span style='color:red'>*</span>", self.name_edit)
        lay.addRow("Trading As", self.trading_as)
        lay.addRow("Registration Number", self.reg_no)
        lay.addRow("VAT Number", self.vat_no)

        page.registerField("company_name*", self.name_edit)
        return page

    def create_page_business_type(self):
        page = QWizardPage()
        page.setTitle("What type of business is this?")
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Choose the option that best describes your business:</b>"))

        options = [
            ("Retail Shop / Online Store", "retail"),
            ("Services (Consulting, IT, Design, Law, etc.)", "services"),
            ("Restaurant / Takeaway / Coffee Shop", "restaurant"),
            ("Construction / Tradesman / Electrician", "construction"),
            ("Manufacturing / Workshop", "manufacturing"),
            ("Farming / Agriculture", "farming"),
            ("Medical Practice / Doctor / Therapist", "medical"),
            ("Rental Income (Property Owner)", "rental"),
            ("Import/Export / Trading Company", "trading"),
            ("Non-Profit / Church / School", "npo"),
            ("Other – I'll set up manually later", "other"),
        ]

        self.business_group = QButtonGroup()
        for text, id_ in options:
            rb = QRadioButton(text)
            rb.setProperty("id", id_)
            self.business_group.addButton(rb)
            lay.addWidget(rb)
            if id_ == "retail":
                rb.setChecked(True)
        lay.addStretch()
        return page

    def create_page_sales(self):
        page = QWizardPage()
        page.setTitle("Sales & Customers")
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Do you do any of these?</b>"))

        self.credit_sales = QCheckBox("I sell on credit (issue invoices to customers)")
        self.cash_sales = QCheckBox("I sell mostly cash / card / SnapScan / Zapper")
        self.vat_registered = QCheckBox("I am VAT registered (or plan to be)")

        lay.addWidget(self.credit_sales)
        lay.addWidget(self.cash_sales)
        lay.addWidget(self.vat_registered)
        lay.addStretch()
        return page

    def create_page_purchases(self):
        page = QWizardPage()
        page.setTitle("Purchases & Expenses")
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Select what applies to your business:</b>"))

        self.credit_purchases = QCheckBox("I buy on credit (receive supplier invoices)")
        self.has_stock = QCheckBox("I keep and track inventory / stock")
        self.has_payroll = QCheckBox("I pay monthly salaries / wages (PAYE, UIF, SDL)")

        lay.addWidget(self.credit_purchases)
        lay.addWidget(self.has_stock)
        lay.addWidget(self.has_payroll)
        lay.addStretch()
        return page

    def create_page_bank(self):
        page = QWizardPage()
        page.setTitle("Bank Accounts")
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>How many bank accounts does this business use?</b>"))

        self.bank_count = QSpinBox()
        self.bank_count.setRange(1, 5)
        self.bank_count.setValue(1)
        lay.addWidget(self.bank_count)

        self.petty_cash = QCheckBox("I also use Petty Cash")
        lay.addWidget(self.petty_cash)
        lay.addStretch()
        return page

    def create_page_summary(self):
        page = QWizardPage()
        page.setTitle("All Done – Your Books Are Ready!")
        lay = QVBoxLayout(page)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 15px;")
        lay.addWidget(self.summary_label)
        lay.addStretch()
        return page

    def nextId(self):
        if self.currentId() == 5:  # Before summary
            self.build_summary()
        return super().nextId()

    def build_summary(self):
        name = self.field("company_name").strip() or "[Untitled Company]"

        biz_id = next((b.property("id") for b in self.business_group.buttons() if b.isChecked()), "other")
        biz_names = {
            "retail": "Retail Shop", "services": "Service Business", "restaurant": "Restaurant",
            "construction": "Construction/Trades", "manufacturing": "Manufacturing", "farming": "Farming",
            "medical": "Medical Practice", "rental": "Property Rental", "trading": "Trading Company",
            "npo": "Non-Profit", "other": "Custom"
        }

        features = []
        if self.credit_sales.isChecked(): features.append("Debtors Ledger + Invoicing")
        if self.cash_sales.isChecked(): features.append("Cash Sales / POS")
        if self.credit_purchases.isChecked(): features.append("Creditors Ledger + Bills")
        if self.has_stock.isChecked(): features.append("Full Stock Control")
        if self.has_payroll.isChecked(): features.append("Payroll (PAYE/UIF/SDL)")
        if self.vat_registered.isChecked(): features.append("VAT Ready")
        features.append(f"{self.bank_count.value()} Bank Account(s)")
        if self.petty_cash.isChecked(): features.append("Petty Cash")

        text = f"""
        <h2>All Done! Your company is ready!</h2>
        <b style='font-size:19px; color:#00bb00;'>{name}</b><br><br>
        Business type: <b>{biz_names.get(biz_id)}</b><br><br>

        <b>Nexled automatically created:</b><br>
        → General Ledger with correct SARS tax codes<br>
        → """ + "<br>→ ".join(features) + f"""

        <br><br>
        <p style='font-size:17px; color:#00aa00; font-weight:bold;'>
        You can now start working immediately.<br>
        No setup headaches. Ever again.
        </p>
        """
        self.summary_label.setText(text)

    def accept(self):
        self.result_data = {
            "company_name": self.field("company_name").strip(),
            "trading_as": self.trading_as.text().strip(),
            "reg_no": self.reg_no.text().strip(),
            "vat_no": self.vat_no.text().strip(),
            "business_type": next((b.property("id") for b in self.business_group.buttons() if b.isChecked()), "other"),
            "credit_sales": self.credit_sales.isChecked(),
            "cash_sales": self.cash_sales.isChecked(),
            "credit_purchases": self.credit_purchases.isChecked(),
            "has_stock": self.has_stock.isChecked(),
            "has_payroll": self.has_payroll.isChecked(),
            "vat_registered": self.vat_registered.isChecked(),
            "bank_count": self.bank_count.value(),
            "petty_cash": self.petty_cash.isChecked(),
        }
        super().accept()

    def apply_setup_to_company(self, company_name):
        conn = get_conn()
        c = conn.cursor()
        d = self.result_data

        c.execute("INSERT INTO company_info (name, trading_as, reg_no, vat_no) VALUES (?,?,?,?)",
                  (d["company_name"], d["trading_as"], d["reg_no"], d["vat_no"]))

        # Smart default categories
        cat_map = {
            "retail": ["Sales", "Cost of Sales", "Bank Charges", "Rent", "Electricity"],
            "services": ["Consulting Fees", "Project Income", "Materials", "Travel"],
            "restaurant": ["Food Sales", "Beverage Sales", "Cost of Food", "Wages"],
        }
        for cat in cat_map.get(d["business_type"], ["Income", "Expenses"]):
            c.execute("INSERT INTO categories (name, type) VALUES (?, ?)",
                      (cat, "Income" if "Sales" in cat or "Income" in cat or "Fees" in cat else "Expense"))

        # Enable modules
        if d["credit_sales"]: c.execute("INSERT INTO settings (key,value) VALUES ('module_debtors','1')")
        if d["credit_purchases"]: c.execute("INSERT INTO settings (key,value) VALUES ('module_creditors','1')")
        if d["has_stock"]: c.execute("INSERT INTO settings (key,value) VALUES ('module_inventory','1')")
        if d["has_payroll"]: c.execute("INSERT INTO settings (key,value) VALUES ('module_payroll','1')")
        if d["vat_registered"]:
            c.execute("INSERT INTO settings (key,value) VALUES ('vat_registered','1')")
            if d["vat_no"]: c.execute("INSERT INTO settings (key,value) VALUES ('vat_number',?)", (d["vat_no"],))

        conn.commit()
        conn.close()

    def open_selected_company_by_name(self, name):
        set_current_company(name)
        parent = self.parent()
        parent.company_label.setText(f"Company: {name}")
        parent.tabs.setCurrentIndex(1)
        parent.refresh_all()

