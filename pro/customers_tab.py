# pro/customers_tab.py
# Professional Customers module for NexLedger Pro (PyQt6)
# - Search, filters, pagination, sorting
# - Customer add/edit with validation and inline errors
# - Double-click to edit
# - Customer ledger (invoices & payments) quick-open
# - Export customer statement (CSV)
# - Safe DB checks (tables may not exist yet)

import csv
from functools import partial
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QLineEdit, QHeaderView, QDialog, QFormLayout,
    QMessageBox, QComboBox, QTextEdit, QSizePolicy, QSpinBox, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from shared.db import get_conn_safe

PAGE_SIZE = 25


# -----------------------------
# Customer Editor Dialog
# -----------------------------
class CustomerEditor(QDialog):
    saved = pyqtSignal()

    def __init__(self, customer_id=None, parent=None):
        super().__init__(parent)
        self.customer_id = customer_id
        self.setWindowTitle("Edit Customer" if customer_id else "New Customer")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setStretch(0, 0)  # header
        layout.setStretch(1, 0)  # KPI row
        layout.setStretch(2, 1)  # table (fills space)
        layout.setStretch(3, 0)  # pager
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 1)
        form = QFormLayout()

        self.txt_name = QLineEdit()
        self.txt_email = QLineEdit()
        self.txt_phone = QLineEdit()
        self.txt_address = QTextEdit()
        self.txt_address.setFixedHeight(70)

        # inline error labels
        self.err_label = QLabel("")
        self.err_label.setStyleSheet("color: red;")

        form.addRow("Name:", self.txt_name)
        form.addRow("Email:", self.txt_email)
        form.addRow("Phone:", self.txt_phone)
        form.addRow("Address:", self.txt_address)
        layout.addLayout(form)
        layout.addWidget(self.err_label)

        btns = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self.save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        if self.customer_id:
            self.load_customer()

    def load_customer(self):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            cur = conn.cursor()
            # safe read
            cur.execute("SELECT * FROM customers WHERE id=?", (self.customer_id,))
            row = cur.fetchone()
            if row:
                self.txt_name.setText(row["name"] or "")
                self.txt_email.setText(row["email"] or "")
                self.txt_phone.setText(row["phone"] or "")
                self.txt_address.setText(row["address"] or "")
        finally:
            try:
                conn.close()
            except:
                pass

    def _show_error(self, text: str):
        self.err_label.setText(text)

    def save(self):
        name = self.txt_name.text().strip()
        email = self.txt_email.text().strip()
        phone = self.txt_phone.text().strip()
        address = self.txt_address.toPlainText().strip()

        if not name:
            self._show_error("Name is required")
            return
        if email and not self._validate_email(email):
            self._show_error("Invalid email address")
            return
        if phone and not self._validate_phone(phone):
            self._show_error("Invalid phone number")
            return

        conn = get_conn_safe()
        if not conn:
            QMessageBox.critical(self, "Error", "Database not ready")
            return
        try:
            cur = conn.cursor()
            if self.customer_id:
                cur.execute("""
                    UPDATE customers SET name=?, email=?, phone=?, address=?
                    WHERE id=?
                """, (name, email or None, phone or None, address or None, self.customer_id))
            else:
                cur.execute("""
                    INSERT INTO customers(name, email, phone, address)
                    VALUES (?,?,?,?)
                """, (name, email or None, phone or None, address or None))
            conn.commit()
            self.saved.emit()
            self.accept()
        except Exception as e:
            self._show_error(f"Save failed: {e}")
        finally:
            try:
                conn.close()
            except:
                pass

    def _validate_email(self, email: str) -> bool:
        return ("@" in email) and ("." in email)

    def _validate_phone(self, phone: str) -> bool:
        s = phone.replace(" ", "").replace("-", "")
        return s.isdigit() or (s.startswith("+") and s[1:].isdigit())


# -----------------------------
# Customer Ledger Dialog
# -----------------------------
class CustomerLedgerDialog(QDialog):
    def __init__(self, customer_id: int, parent=None):
        super().__init__(parent)
        self.customer_id = customer_id
        self.setWindowTitle(f"Customer Ledger - {customer_id}")
        self.setMinimumSize(700, 500)
        self.build_ui()
        self.load_ledger()

    def build_ui(self):
        lay = QVBoxLayout(self)
        self.lbl_info = QLabel("")
        lay.addWidget(self.lbl_info)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Email", "Phone", "Outstanding", "Actions"])
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
            # load customer name
            row = cur.execute("SELECT name FROM customers WHERE id=?", (self.customer_id,)).fetchone()
            name = row["name"] if row else f"Customer {self.customer_id}"
            self.lbl_info.setText(f"Ledger for: {name}")

            # collect invoices and payments (payments may be implemented as transactions)
            items = []
            if self._table_exists(conn, "invoices"):
                invs = cur.execute("SELECT id, date, total FROM invoices WHERE customer_id=? ORDER BY date",
                                   (self.customer_id,)).fetchall()
                for i in invs:
                    items.append(("Invoice", i["id"], i["date"], i["total"]))
            # payments (transactions table) - check table
            if self._table_exists(conn, "transactions"):
                pays = cur.execute(
                    "SELECT id, date, amount, description FROM transactions WHERE description LIKE ? ORDER BY date",
                    (f"%cust:{self.customer_id}%",)).fetchall()
                for p in pays:
                    items.append(("Payment", p["id"], p["date"], p["amount"]))

            # sort by date and compute running balance
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
            try:
                conn.close()
            except:
                pass

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Ledger CSV", "ledger.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # headers
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                writer.writerow(headers)
                for r in range(self.table.rowCount()):
                    row = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in
                           range(self.table.columnCount())]
                    writer.writerow(row)
            QMessageBox.information(self, "Exported", f"Ledger exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _table_exists(self, conn, name: str) -> bool:
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
            return cur.fetchone() is not None
        except Exception:
            return False


# -----------------------------
# Customers Tab
# -----------------------------
class CustomersTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = 0
        self.sort_column = 1
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.build_ui()
        self.refresh()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Customers</h2>")
        header.addWidget(title)
        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, email or phone…")
        self.search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Has Outstanding", "Top 10", "Recently Active (30d)"])
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.filter_combo)

        add_btn = QPushButton("+ Add Customer")
        add_btn.clicked.connect(self.add_customer)
        header.addWidget(add_btn)

        export_btn = QPushButton("Export Statements CSV")
        export_btn.clicked.connect(self.export_all_statements)
        header.addWidget(export_btn)

        # Header should never expand
        for i in range(header.count()):
            w = header.itemAt(i).widget()
            if w:
                w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addLayout(header)

        # KPI Row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.kpi_total_customers = self._create_kpi("Total Customers", "0")
        self.kpi_outstanding = self._create_kpi("Outstanding Balances", "R0.00")
        self.kpi_month_sales = self._create_kpi("Sales (30 days)", "R0.00")

        for k in (self.kpi_total_customers, self.kpi_outstanding, self.kpi_month_sales):
            k.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            kpi_row.addWidget(k)

        # KPI row fixed height
        for i in range(kpi_row.count()):
            w = kpi_row.itemAt(i).widget()
            if w:
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                w.setMinimumHeight(80)
        layout.addLayout(kpi_row)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Email", "Phone", "Outstanding", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.cellClicked.connect(self._handle_table_click)
        self.table.itemDoubleClicked.connect(self._double_click_edit)

        # Table takes remaining space
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setMinimumHeight(350)
        layout.addWidget(self.table)

        # Pagination
        pager = QHBoxLayout()
        self.btn_prev = QPushButton("Previous")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next = QPushButton("Next")
        self.btn_next.clicked.connect(self._next_page)
        self.lbl_page = QLabel("Page: 1")
        pager.addStretch()
        pager.addWidget(self.btn_prev)
        pager.addWidget(self.lbl_page)
        pager.addWidget(self.btn_next)
        # Pager minimal height
        for i in range(pager.count()):
            w = pager.itemAt(i).widget()
            if w:
                w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addLayout(pager)

    def _create_kpi(self, title, value):
        box = QFrame()
        box.setStyleSheet("border:1px solid #ddd; border-radius:6px; padding:8px;")
        lay = QVBoxLayout(box)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color:#777;")
        lbl_title.setFont(QFont("", 9))
        lay.addWidget(lbl_title)
        lbl_value = QLabel(value)
        lbl_value.setFont(QFont("", 18, QFont.Weight.Bold))
        lay.addWidget(lbl_value)
        box.value_label = lbl_value
        return box

    # --------------------------
    # CRUD handlers
    # --------------------------
    def add_customer(self):
        dlg = CustomerEditor(None, self)
        dlg.saved.connect(self.refresh)
        dlg.exec()

    def edit_customer(self, customer_id: int):
        dlg = CustomerEditor(customer_id, self)
        dlg.saved.connect(self.refresh)
        dlg.exec()

    # --------------------------
    # Pagination & search
    # --------------------------
    def _on_search_changed(self):
        self.page = 0
        self.refresh()

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.refresh()

    def _next_page(self):
        self.page += 1
        self.refresh()

    # --------------------------
    # Load data
    # --------------------------
    def refresh(self):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            cur = conn.cursor()

            search = f"%{self.search.text().strip()}%"
            filter_mode = self.filter_combo.currentText()

            base_where = "1=1"
            params = []

            # filter modes
            if filter_mode == "Has Outstanding":
                if self._table_exists(conn, "invoices"):
                    base_where = "(SELECT IFNULL(SUM(total),0) FROM invoices WHERE customer_id = customers.id AND status != 'Paid') > 0"
                else:
                    base_where = "0"
            elif filter_mode == "Top 10":
                # we'll handle ordering later
                pass
            elif filter_mode == "Recently Active (30d)":
                if self._table_exists(conn, "invoices"):
                    base_where = "EXISTS(SELECT 1 FROM invoices WHERE customer_id = customers.id AND date >= date('now','-30 day'))"
                else:
                    base_where = "0"

            # search clause
            search_clause = "(name LIKE ? OR email LIKE ? OR phone LIKE ?)"
            params.extend([search, search, search])

            # final where
            where_sql = f"WHERE {base_where} AND " + search_clause

            # count total
            count_sql = f"SELECT COUNT(1) as cnt FROM customers {where_sql}"
            total = cur.execute(count_sql, params).fetchone()[0]

            # paging
            offset = self.page * PAGE_SIZE
            limit = PAGE_SIZE

            # main query with outstanding calculation (safe)
            sql = f"""
                SELECT id, name, email, phone,
                CASE
                    WHEN EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='invoices')
                    THEN (
                        SELECT IFNULL(SUM(total),0) FROM invoices
                        WHERE customer_id = customers.id AND status != 'Paid'
                    )
                    ELSE 0
                END AS outstanding,
                (
                    SELECT IFNULL(SUM(total),0) FROM invoices
                    WHERE customer_id = customers.id AND status != 'Paid'
                ) AS outstanding
                FROM customers
                {where_sql}
            """

            # ordering
            sql += " ORDER BY name ASC"
            if filter_mode == "Top 10":
                sql = sql.replace("ORDER BY name ASC", "ORDER BY outstanding DESC")

            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = cur.execute(sql, params).fetchall()

            # fill table
            self.table.setRowCount(len(rows))
            total_outstanding = 0
            for r, row in enumerate(rows):
                cid = row["id"]
                total_outstanding += row["outstanding"] or 0
                self.table.setItem(r, 0, QTableWidgetItem(str(cid)))
                self.table.setItem(r, 1, QTableWidgetItem(row["name"] or ""))
                self.table.setItem(r, 2, QTableWidgetItem(row["email"] or ""))
                self.table.setItem(r, 3, QTableWidgetItem(row["phone"] or ""))
                self.table.setItem(r, 4, QTableWidgetItem(f"R{(row['outstanding'] or 0):,.2f}"))

                # actions column (Edit, Ledger)
                btn_edit = QPushButton("Edit")
                btn_edit.clicked.connect(partial(self.edit_customer, cid))
                btn_ledger = QPushButton("Ledger")
                btn_ledger.clicked.connect(partial(self.open_ledger, cid))
                w = QWidget()
                hl = QHBoxLayout(w)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.addWidget(btn_edit)
                hl.addWidget(btn_ledger)
                self.table.setCellWidget(r, 5, w)

            # KPIs
            self.kpi_total_customers.value_label.setText(str(total))
            self.kpi_outstanding.value_label.setText(f"R{total_outstanding:,.2f}")

            # last 30 days sales
            sales = 0
            if self._table_exists(conn, "invoices"):
                sales_row = cur.execute(
                    "SELECT IFNULL(SUM(total),0) as s FROM invoices WHERE date >= date('now','-30 day') AND status != 'Draft'").fetchone()
                sales = sales_row["s"] if sales_row else 0
            self.kpi_month_sales.value_label.setText(f"R{sales:,.2f}")

            # page label
            self.lbl_page.setText(f"Page: {self.page + 1} / {max(1, (total - 1) // PAGE_SIZE + 1)}")

        except Exception as e:
            print("[CustomersTab] refresh failed:", e)
        finally:
            try:
                conn.close()
            except:
                pass

    def _handle_table_click(self, row, col):
        # support copy/paste or future actions
        pass

    def _double_click_edit(self, item):
        try:
            row = item.row()
            cid_item = self.table.item(row, 0)
            if cid_item:
                cid = int(cid_item.text())
                self.edit_customer(cid)
        except Exception as e:
            print("Double click edit failed:", e)

    def open_ledger(self, cid: int):
        dlg = CustomerLedgerDialog(cid, self)
        dlg.exec()

    def export_all_statements(self):
        # export basic statements for all customers as CSV
        path, _ = QFileDialog.getSaveFileName(self, "Export All Statements", "customers_statements.csv",
                                              "CSV Files (*.csv)")
        if not path:
            return
        conn = get_conn_safe()
        if not conn:
            return
        try:
            cur = conn.cursor()
            rows = cur.execute("SELECT id FROM customers ORDER BY name").fetchall()
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["CustomerID", "Name", "StatementCSVPath"])
                for r in rows:
                    cid = r["id"]
                    # create a small CSV per customer in same folder
                    cust_name_row = cur.execute("SELECT name FROM customers WHERE id=?", (cid,)).fetchone()
                    name = cust_name_row["name"] if cust_name_row else str(cid)
                    cust_path = f"{path[:-4]}_cust_{cid}.csv"
                    ledger = CustomerLedgerDialog(cid, self)
                    # reuse ledger logic to produce CSV rows
                    ledger.load_ledger()
                    # write ledger CSV
                    with open(cust_path, "w", newline="", encoding="utf-8") as cf:
                        w2 = csv.writer(cf)
                        # header
                        headers = [ledger.table.horizontalHeaderItem(i).text() for i in
                                   range(ledger.table.columnCount())]
                        w2.writerow(headers)
                        for rr in range(ledger.table.rowCount()):
                            rowvals = [ledger.table.item(rr, c).text() if ledger.table.item(rr, c) else "" for c in
                                       range(ledger.table.columnCount())]
                            w2.writerow(rowvals)
                    writer.writerow([cid, name, cust_path])
            QMessageBox.information(self, "Exported", f"Statements exported to CSV files (index: {path})")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        finally:
            try:
                conn.close()
            except:
                pass

    # --------------------------
    # Utility
    # --------------------------
    def _table_exists(self, conn, name: str) -> bool:
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
            return cur.fetchone() is not None
        except Exception:
            return False

    # --------------------------
    # UI Fixes & Enhancements
    # --------------------------
    def showEvent(self, event):
        """
        Fixes the issue where the GUI loads empty or improperly sized.
        Forces a layout recalculation once the widget becomes visible.
        """
        super().showEvent(event)
        try:
            self.table.resizeColumnsToContents()
            self.table.horizontalHeader().setStretchLastSection(True)
        except Exception:
            pass

# End of CustomersTab
