# pro/vendors_tab.py
# Professional Vendors module for NexLedger Pro (PyQt6)
# Modeled after modern accounting software:
# - Search, filters, pagination, sorting
# - Vendor editor + inline validation
# - Vendor ledger: bills + payments
# - Outstanding bills KPI
# - CSV export
# - Safe checks when bills/payments tables are missing

import csv
from functools import partial
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView, QDialog,
    QFormLayout, QMessageBox, QComboBox, QTextEdit, QFileDialog,
    QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from shared.db import get_conn_safe

PAGE_SIZE = 25


# ---------------------------------------------------------
# Vendor Editor
# ---------------------------------------------------------
class VendorEditor(QDialog):
    saved = pyqtSignal()

    def __init__(self, vendor_id=None, parent=None):
        super().__init__(parent)
        self.vendor_id = vendor_id
        self.setWindowTitle("Edit Vendor" if vendor_id else "New Vendor")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_name = QLineEdit()
        self.txt_email = QLineEdit()
        self.txt_phone = QLineEdit()
        self.txt_address = QTextEdit()
        self.txt_address.setFixedHeight(70)

        self.err = QLabel("")
        self.err.setStyleSheet("color:red;")
        form.addRow("Name:", self.txt_name)
        form.addRow("Email:", self.txt_email)
        form.addRow("Phone:", self.txt_phone)
        form.addRow("Address:", self.txt_address)
        layout.addLayout(form)
        layout.addWidget(self.err)

        btns = QHBoxLayout()
        save = QPushButton("Save")
        cancel = QPushButton("Cancel")
        save.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        if self.vendor_id:
            self.load_vendor()

    def _show_error(self, msg):
        self.err.setText(msg)

    def load_vendor(self):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            row = conn.execute("SELECT * FROM vendors WHERE id=?", (self.vendor_id,)).fetchone()
            if row:
                self.txt_name.setText(row["name"] or "")
                self.txt_email.setText(row["email"] or "")
                self.txt_phone.setText(row["phone"] or "")
                self.txt_address.setText(row["address"] or "")
        finally:
            conn.close()

    def save(self):
        name = self.txt_name.text().strip()
        if not name:
            self._show_error("Name is required")
            return

        email = self.txt_email.text().strip() or None
        phone = self.txt_phone.text().strip() or None
        addr = self.txt_address.toPlainText().strip() or None

        conn = get_conn_safe()
        if not conn:
            QMessageBox.critical(self, "Error", "Database unavailable")
            return
        try:
            if self.vendor_id:
                conn.execute("""
                    UPDATE vendors SET name=?, email=?, phone=?, address=?
                    WHERE id=?
                """, (name, email, phone, addr, self.vendor_id))
            else:
                conn.execute("""
                    INSERT INTO vendors(name, email, phone, address)
                    VALUES (?,?,?,?)
                """, (name, email, phone, addr))
            conn.commit()
            self.saved.emit()
            self.accept()
        except Exception as e:
            self._show_error(str(e))
        finally:
            conn.close()


# ---------------------------------------------------------
# Vendor Ledger
# ---------------------------------------------------------
class VendorLedgerDialog(QDialog):
    def __init__(self, vendor_id, parent=None):
        super().__init__(parent)
        self.vendor_id = vendor_id
        self.setWindowTitle(f"Vendor Ledger - {vendor_id}")
        self.setMinimumSize(700, 500)
        self.build_ui()
        self.load_ledger()

    def build_ui(self):
        lay = QVBoxLayout(self)
        self.lbl_info = QLabel("")
        lay.addWidget(self.lbl_info)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Type", "Ref/ID", "Date", "Amount", "Running Balance"])
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table)

        btns = QHBoxLayout()
        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_csv)
        btns.addStretch()
        btns.addWidget(export)
        lay.addLayout(btns)

    def load_ledger(self):
        conn = get_conn_safe()
        if not conn:
            return

        try:
            cur = conn.cursor()

            # vendor name
            row = cur.execute("SELECT name FROM vendors WHERE id=?", (self.vendor_id,)).fetchone()
            name = row["name"] if row else f"Vendor {self.vendor_id}"
            self.lbl_info.setText(f"Ledger for: {name}")

            items = []

            # bills
            if self._table_exists(conn, "bills"):
                bills = cur.execute("""
                    SELECT id, date, total FROM bills
                    WHERE vendor_id=?
                    ORDER BY date
                """, (self.vendor_id,)).fetchall()
                for b in bills:
                    items.append(("Bill", b["id"], b["date"], b["total"]))

            # payments via transactions
            if self._table_exists(conn, "transactions"):
                pays = cur.execute("""
                    SELECT id, date, amount FROM transactions
                    WHERE description LIKE ?
                    ORDER BY date
                """, (f"%vend:{self.vendor_id}%",)).fetchall()
                for p in pays:
                    items.append(("Payment", p["id"], p["date"], p["amount"]))

            # sort & compute balance
            items.sort(key=lambda x: x[2] or "")
            balance = 0
            self.table.setRowCount(len(items))

            for r, it in enumerate(items):
                typ, ref, date, amt = it
                balance += (amt or 0)
                self.table.setItem(r, 0, QTableWidgetItem(typ))
                self.table.setItem(r, 1, QTableWidgetItem(str(ref)))
                self.table.setItem(r, 2, QTableWidgetItem(str(date)))
                self.table.setItem(r, 3, QTableWidgetItem(f"R{(amt or 0):,.2f}"))
                self.table.setItem(r, 4, QTableWidgetItem(f"R{balance:,.2f}"))

        finally:
            conn.close()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Ledger CSV", "vendor_ledger.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
            w.writerow(headers)
            for r in range(self.table.rowCount()):
                row = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(self.table.columnCount())]
                w.writerow(row)

    def _table_exists(self, conn, name):
        c = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return c.fetchone() is not None


# ---------------------------------------------------------
# Vendors Tab (Main)
# ---------------------------------------------------------
class VendorsTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = 0
        self.build_ui()
        self.refresh()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Vendors</h2>")
        header.addWidget(title)
        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, email or phone…")
        self.search.textChanged.connect(self._search_changed)
        header.addWidget(self.search)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Has Outstanding", "Top 10 Recently Used"])
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.filter_combo)

        add_btn = QPushButton("+ Add Vendor")
        add_btn.clicked.connect(self.add_vendor)
        header.addWidget(add_btn)

        for i in range(header.count()):
            w = header.itemAt(i).widget()
            if w:
                w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout.addLayout(header)

        # KPIs
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)

        self.kpi_total = self._kpi("Total Vendors", "0")
        self.kpi_outstanding = self._kpi("Outstanding Bills", "R0.00")
        self.kpi_month_exp = self._kpi("Expenses (30 days)", "R0.00")

        for k in (self.kpi_total, self.kpi_outstanding, self.kpi_month_exp):
            k.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            k.setMinimumHeight(80)
            kpi_row.addWidget(k)

        layout.addLayout(kpi_row)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Email", "Phone", "Outstanding", "Actions"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self._double_click_edit)
        layout.addWidget(self.table)

        # Pager
        pager = QHBoxLayout()
        self.btn_prev = QPushButton("Prev")
        self.btn_next = QPushButton("Next")
        self.lbl_page = QLabel("Page: 1")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        pager.addStretch()
        pager.addWidget(self.btn_prev)
        pager.addWidget(self.lbl_page)
        pager.addWidget(self.btn_next)
        layout.addLayout(pager)

    def _double_click_edit(self, item):
        try:
            row = item.row()
            cid_item = self.table.item(row, 0)
            if cid_item:
                cid = int(cid_item.text())
                self.edit_customer(cid)
        except Exception as e:
            print("Double click edit failed:", e)

    def _kpi(self, title, value):
        box = QFrame()
        box.setStyleSheet("border:1px solid #ccc; border-radius:6px; padding:8px;")
        v = QVBoxLayout(box)
        lbl1 = QLabel(title)
        lbl1.setStyleSheet("color:#777;")
        lbl1.setFont(QFont("", 9))
        v.addWidget(lbl1)
        lbl2 = QLabel(value)
        lbl2.setFont(QFont("", 18, QFont.Weight.Bold))
        v.addWidget(lbl2)
        box.value = lbl2
        return box

    # -------------------
    # CRUD
    # -------------------
    def add_vendor(self):
        dlg = VendorEditor(None, self)
        dlg.saved.connect(self.refresh)
        dlg.exec()

    def edit_vendor(self, vid):
        dlg = VendorEditor(vid, self)
        dlg.saved.connect(self.refresh)
        dlg.exec()

    # -------------------
    # Paging
    # -------------------
    def _search_changed(self):
        self.page = 0
        self.refresh()

    def prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.refresh()

    def next_page(self):
        self.page += 1
        self.refresh()

    # -------------------
    # Refresh
    # -------------------
    def refresh(self):
        conn = get_conn_safe()
        if not conn:
            return

        try:
            cur = conn.cursor()

            search = f"%{self.search.text().strip()}%"
            filter_mode = self.filter_combo.currentText()

            # filter
            base_where = "1=1"
            if filter_mode == "Has Outstanding" and self._exists(conn, "bills"):
                base_where = "(SELECT IFNULL(SUM(total),0) FROM bills WHERE vendor_id = vendors.id AND status != 'Paid') > 0"

            # search
            where = f"WHERE {base_where} AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"

            params = [search, search, search]

            # count
            cnt = cur.execute(f"SELECT COUNT(1) FROM vendors {where}", params).fetchone()[0]

            offset = self.page * PAGE_SIZE
            limit = PAGE_SIZE

            # load vendors
            sql = f"""
                SELECT
                    id, name, email, phone,
                    CASE
                        WHEN EXISTS(SELECT 1 FROM sqlite_master WHERE name='bills')
                        THEN (
                            SELECT IFNULL(SUM(total),0)
                            FROM bills WHERE vendor_id = vendors.id AND status != 'Paid'
                        )
                        ELSE 0
                    END AS outstanding
                FROM vendors
                {where}
                ORDER BY name ASC
                LIMIT ? OFFSET ?
            """

            params2 = params + [limit, offset]
            rows = cur.execute(sql, params2).fetchall()

            # fill table
            self.table.setRowCount(len(rows))
            total_out = 0

            for r, row in enumerate(rows):
                vid = row["id"]
                total_out += (row["outstanding"] or 0)

                self.table.setItem(r, 0, QTableWidgetItem(str(vid)))
                self.table.setItem(r, 1, QTableWidgetItem(row["name"] or ""))
                self.table.setItem(r, 2, QTableWidgetItem(row["email"] or ""))
                self.table.setItem(r, 3, QTableWidgetItem(row["phone"] or ""))
                self.table.setItem(r, 4, QTableWidgetItem(f"R{(row['outstanding'] or 0):,.2f}"))

                # actions
                btn_edit = QPushButton("Edit")
                btn_led = QPushButton("Ledger")
                btn_edit.clicked.connect(partial(self.edit_vendor, vid))
                btn_led.clicked.connect(partial(self.open_ledger, vid))

                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(0,0,0,0)
                h.addWidget(btn_edit)
                h.addWidget(btn_led)
                self.table.setCellWidget(r, 5, w)

            # KPIs
            self.kpi_total.value.setText(str(cnt))
            self.kpi_outstanding.value.setText(f"R{total_out:,.2f}")

            # Last 30 days expenses
            if self._exists(conn, "bills"):
                thirty = cur.execute("""
                    SELECT IFNULL(SUM(total),0) FROM bills
                    WHERE date >= date('now','-30 day')
                """).fetchone()[0]
            else:
                thirty = 0

            self.kpi_month_exp.value.setText(f"R{thirty:,.2f}")

            # page label
            self.lbl_page.setText(f"Page: {self.page+1} / {max(1,(cnt-1)//PAGE_SIZE+1)}")

        except Exception as e:
            print("[VendorsTab] refresh failed:", e)

        finally:
            conn.close()

    def open_ledger(self, vid):
        dlg = VendorLedgerDialog(vid, self)
        dlg.exec()

    def _exists(self, conn, table):
        r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return r.fetchone() is not None
