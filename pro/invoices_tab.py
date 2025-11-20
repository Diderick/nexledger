# pro/invoices_tab.py
# Professional Invoices module for NexLedger Pro (PyQt6)
# Full-featured invoice list + editor modeled after modern accounting software

import csv
from functools import partial
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QLineEdit, QHeaderView, QDialog, QFormLayout,
    QMessageBox, QComboBox, QTextEdit, QSizePolicy, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QFont

from shared.db import get_conn_safe

PAGE_SIZE = 20


# -----------------------------
# Invoice Editor
# -----------------------------
class InvoiceEditor(QDialog):
    saved = pyqtSignal()

    def __init__(self, invoice_id=None, parent=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.setWindowTitle("Edit Invoice" if invoice_id else "New Invoice")
        self.setMinimumSize(760, 600)
        self._build_ui()
        if invoice_id:
            self._load_invoice()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.date_edit = QLineEdit(QDate.currentDate().toString("yyyy-MM-dd"))
        self.customer_combo = QComboBox()
        self._load_customers()
        self.notes = QTextEdit()
        self.notes.setFixedHeight(80)

        form.addRow("Date:", self.date_edit)
        form.addRow("Customer:", self.customer_combo)
        form.addRow("Notes:", self.notes)
        layout.addLayout(form)

        # Line items
        self.items = QTableWidget()
        self.items.setColumnCount(5)
        self.items.setHorizontalHeaderLabels(["Description", "Qty", "Unit Price", "VAT%", "Total"])
        self.items.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.items)

        btn_row = QHBoxLayout()
        add_line = QPushButton("Add Line")
        add_line.clicked.connect(self._add_line)
        btn_row.addWidget(add_line)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Totals
        totals_row = QHBoxLayout()
        self.lbl_sub = QLabel("Sub-total: R0.00")
        self.lbl_vat = QLabel("VAT: R0.00")
        self.lbl_total = QLabel("Total: R0.00")
        for l in (self.lbl_sub, self.lbl_vat, self.lbl_total):
            l.setFont(QFont("", 11, QFont.Weight.DemiBold))
            totals_row.addWidget(l)
        totals_row.addStretch()
        layout.addLayout(totals_row)

        # Save / Cancel
        btns = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(save); btns.addWidget(cancel)
        layout.addLayout(btns)

        # recalc when table edits happen
        self.items.cellChanged.connect(self._on_item_changed)

    def _load_customers(self):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            rows = conn.execute("SELECT id, name FROM customers ORDER BY name").fetchall()
            for r in rows:
                self.customer_combo.addItem(r["name"], r["id"])
        finally:
            try: conn.close()
            except: pass

    def _add_line(self):
        r = self.items.rowCount()
        self.items.insertRow(r)
        self.items.setItem(r, 0, QTableWidgetItem(""))
        self.items.setItem(r, 1, QTableWidgetItem("1"))
        self.items.setItem(r, 2, QTableWidgetItem("0.00"))
        self.items.setItem(r, 3, QTableWidgetItem("15"))
        self.items.setItem(r, 4, QTableWidgetItem("0.00"))

    def _on_item_changed(self, row, col):
        # recalc total for the line and overall totals
        try:
            qty = float(self.items.item(row, 1).text()) if self.items.item(row, 1) else 0
            price = float(self.items.item(row, 2).text()) if self.items.item(row, 2) else 0
            vat_pct = float(self.items.item(row, 3).text()) if self.items.item(row, 3) else 0
            line_total = qty * price * (1 + vat_pct / 100)
            self.items.blockSignals(True)
            self.items.setItem(row, 4, QTableWidgetItem(f"{line_total:.2f}"))
            self.items.blockSignals(False)
        except Exception:
            pass
        self._recalc_totals()

    def _recalc_totals(self):
        sub = 0.0
        vat = 0.0
        for r in range(self.items.rowCount()):
            try:
                qty = float(self.items.item(r, 1).text())
                price = float(self.items.item(r, 2).text())
                vat_pct = float(self.items.item(r, 3).text())
                line_net = qty * price
                sub += line_net
                vat += line_net * (vat_pct / 100)
            except Exception:
                pass
        total = sub + vat
        self.lbl_sub.setText(f"Sub-total: R{sub:,.2f}")
        self.lbl_vat.setText(f"VAT: R{vat:,.2f}")
        self.lbl_total.setText(f"Total: R{total:,.2f}")
        return sub, vat, total

    def _load_invoice(self):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            cur = conn.cursor()
            inv = cur.execute("SELECT * FROM invoices WHERE id=?", (self.invoice_id,)).fetchone()
            if not inv:
                return
            self.date_edit.setText(inv["date"])
            idx = self.customer_combo.findData(inv["customer_id"])
            if idx >= 0:
                self.customer_combo.setCurrentIndex(idx)
            self.notes.setPlainText(inv["notes"] or "")
            # load items
            items = cur.execute("SELECT description, qty, price, vat FROM invoice_items WHERE invoice_id=?", (self.invoice_id,)).fetchall()
            for it in items:
                r = self.items.rowCount()
                self.items.insertRow(r)
                self.items.setItem(r, 0, QTableWidgetItem(it["description"]))
                self.items.setItem(r, 1, QTableWidgetItem(str(it["qty"])))
                self.items.setItem(r, 2, QTableWidgetItem(str(it["price"])))
                self.items.setItem(r, 3, QTableWidgetItem(str(it["vat"])))
                self.items.setItem(r, 4, QTableWidgetItem(str(it["qty"] * it["price"] * (1 + it["vat"]/100))))
            self._recalc_totals()
        finally:
            try: conn.close()
            except: pass

    def _save(self):
        conn = get_conn_safe()
        if not conn:
            QMessageBox.critical(self, "Error", "Database not available")
            return
        try:
            cur = conn.cursor()
            sub, vat, total = self._recalc_totals()
            date = self.date_edit.text()
            cust = self.customer_combo.currentData()
            notes = self.notes.toPlainText()

            if self.invoice_id:
                cur.execute("UPDATE invoices SET customer_id=?, date=?, notes=?, total=?, status=? WHERE id=?",
                            (cust, date, notes, total, 'Sent', self.invoice_id))
                cur.execute("DELETE FROM invoice_items WHERE invoice_id=?", (self.invoice_id,))
            else:
                cur.execute("INSERT INTO invoices (customer_id, date, notes, total, status) VALUES (?,?,?,?, 'Draft')",
                            (cust, date, notes, total))
                self.invoice_id = cur.lastrowid

            for r in range(self.items.rowCount()):
                desc = self.items.item(r, 0).text() if self.items.item(r, 0) else ""
                qty = float(self.items.item(r, 1).text()) if self.items.item(r, 1) else 0
                price = float(self.items.item(r, 2).text()) if self.items.item(r, 2) else 0
                vat_pct = float(self.items.item(r, 3).text()) if self.items.item(r, 3) else 0
                cur.execute("INSERT INTO invoice_items (invoice_id, description, qty, price, vat) VALUES (?,?,?,?,?)",
                            (self.invoice_id, desc, qty, price, vat_pct))

            conn.commit()
            self.saved.emit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
        finally:
            try: conn.close()
            except: pass


# -----------------------------
# Invoices Tab
# -----------------------------
class InvoicesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = 0
        self.build_ui()
        self.refresh()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12,12,12,12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Invoices</h2>")
        header.addWidget(title)
        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search invoices by customer, id or notes…")
        self.search.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Draft", "Sent", "Overdue", "Paid"])
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.filter_combo)

        add_btn = QPushButton("+ New Invoice")
        add_btn.clicked.connect(self._new_invoice)
        header.addWidget(add_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        header.addWidget(export_btn)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Customer", "Date", "Status", "Total", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemDoubleClicked.connect(self._row_open)
        layout.addWidget(self.table)

        # Pager
        pager = QHBoxLayout()
        self.btn_prev = QPushButton("Previous")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next = QPushButton("Next")
        self.btn_next.clicked.connect(self._next_page)
        self.lbl_page = QLabel("Page: 1")
        pager.addStretch(); pager.addWidget(self.btn_prev); pager.addWidget(self.lbl_page); pager.addWidget(self.btn_next)
        layout.addLayout(pager)

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

    def _new_invoice(self):
        dlg = InvoiceEditor(None, self)
        dlg.saved.connect(self.refresh)
        dlg.exec()

    def _row_open(self, item):
        try:
            row = item.row()
            id_item = self.table.item(row, 0)
            if id_item:
                inv_id = int(id_item.text())
                dlg = InvoiceEditor(inv_id, self)
                dlg.saved.connect(self.refresh)
                dlg.exec()
        except Exception as e:
            print("Open invoice failed:", e)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Invoices", "invoices.csv", "CSV Files (*.csv)")
        if not path:
            return
        conn = get_conn_safe()
        if not conn:
            return
        try:
            cur = conn.cursor()
            rows = cur.execute("SELECT i.id, c.name as customer, i.date, i.status, i.total FROM invoices i LEFT JOIN customers c ON c.id=i.customer_id ORDER BY i.date DESC").fetchall()
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["ID","Customer","Date","Status","Total"])
                for r in rows:
                    w.writerow([r['id'], r['customer'], r['date'], r['status'], f"{r['total']:.2f}"])
            QMessageBox.information(self, "Exported", f"Invoices exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        finally:
            try: conn.close()
            except: pass

    def refresh(self):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            cur = conn.cursor()
            search = f"%{self.search.text().strip()}%"
            status = self.filter_combo.currentText()

            where = "1=1"
            params = []
            if status != "All":
                where = "status = ?"
                params.append(status)

            where = f"WHERE {where} AND (i.id LIKE ? OR c.name LIKE ? OR i.notes LIKE ? OR i.date LIKE ?)"
            params = params + [search, search, search, search]

            count_sql = f"SELECT COUNT(1) as cnt FROM invoices i LEFT JOIN customers c ON c.id=i.customer_id {where}"
            total = cur.execute(count_sql, params).fetchone()[0]

            offset = self.page * PAGE_SIZE
            limit = PAGE_SIZE

            sql = f"""
                SELECT i.id, c.name as customer, i.date, i.status, i.total
                FROM invoices i
                LEFT JOIN customers c ON c.id=i.customer_id
                {where}
                ORDER BY i.date DESC
                LIMIT ? OFFSET ?
            """

            rows = cur.execute(sql, params + [limit, offset]).fetchall()

            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                inv_id = row['id']
                self.table.setItem(r, 0, QTableWidgetItem(str(inv_id)))
                self.table.setItem(r, 1, QTableWidgetItem(str(row['customer'] or '(Unknown)')))
                self.table.setItem(r, 2, QTableWidgetItem(str(row['date'])))

                # Status with color badge
                status_item = QTableWidgetItem(str(row['status']))
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if row['status'] == 'Draft':
                    status_item.setBackground(Qt.GlobalColor.lightGray)
                elif row['status'] == 'Sent':
                    status_item.setBackground(Qt.GlobalColor.yellow)
                elif row['status'] == 'Overdue':
                    status_item.setBackground(Qt.GlobalColor.red)
                elif row['status'] == 'Paid':
                    status_item.setBackground(Qt.GlobalColor.green)
                self.table.setItem(r, 3, status_item)

                self.table.setItem(r, 4, QTableWidgetItem(f"R{(row['total'] or 0):,.2f}"))

                # Actions: Edit, Send, Mark Paid
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(0,0,0,0)
                btn_edit = QPushButton('Edit')
                btn_send = QPushButton('Send')
                btn_pay = QPushButton('Mark Paid')
                btn_edit.clicked.connect(partial(self._open_editor_by_id, inv_id))
                btn_send.clicked.connect(partial(self._send_invoice, inv_id))
                btn_pay.clicked.connect(partial(self._mark_paid, inv_id))
                h.addWidget(btn_edit); h.addWidget(btn_send); h.addWidget(btn_pay)
                self.table.setCellWidget(r, 5, w)

            self.lbl_page.setText(f"Page: {self.page+1} / {max(1, (total-1)//PAGE_SIZE + 1)}")

        except Exception as e:
            print('[InvoicesTab] refresh failed:', e)
        finally:
            try: conn.close()
            except: pass

    # helpers
    def _open_editor_by_id(self, inv_id):
        dlg = InvoiceEditor(inv_id, self)
        dlg.saved.connect(self.refresh)
        dlg.exec()

    def _send_invoice(self, inv_id):
        # stub: set status to Sent (real implementation: email + PDF)
        conn = get_conn_safe()
        if not conn:
            return
        try:
            conn.execute("UPDATE invoices SET status='Sent' WHERE id=?", (inv_id,))
            conn.commit()
            QMessageBox.information(self, 'Sent', f'Invoice {inv_id} marked as Sent')
            self.refresh()
        finally:
            try: conn.close()
            except: pass

    def _mark_paid(self, inv_id):
        conn = get_conn_safe()
        if not conn:
            return
        try:
            conn.execute("UPDATE invoices SET status='Paid' WHERE id=?", (inv_id,))
            conn.commit()
            QMessageBox.information(self, 'Paid', f'Invoice {inv_id} marked as Paid')
            self.refresh()
        finally:
            try: conn.close()
            except: pass

# End of InvoicesTab
