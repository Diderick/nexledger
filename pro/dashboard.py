# pro/dashboard.py
"""
Dashboard widget for NexLedger Pro (PyQt6).

Features:
 - KPIs: Bank Balance, Total Income, Total Expenses, Net Profit (period)
 - Charts (matplotlib embedded): Income vs Expenses (monthly), P&L summary
 - Lists: Outstanding invoices, Overdue bills, Top customers
 - Clickable rows for invoices and bills that emit signals
 - Drill-down charts, collapsible panels, filters, cashflow heatmap
 - "What-if" profit simulation (simple)
 - Public method: refresh() to reload data
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSizePolicy, QFrame, QSpacerItem,
    QFileDialog
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

# matplotlib for embedding
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from shared.db import get_conn_safe
from shared.ledger_engine import profit_and_loss, trial_balance
from datetime import datetime, timedelta
import sqlite3
import csv


# ------------------------------
# Small helper widgets
# ------------------------------
class KPIWidget(QFrame):
    def __init__(self, title: str, value: str, subtitle: str = ""):
        super().__init__()
        self.setObjectName("kpi")
        self.setStyleSheet("""
            QFrame#kpi { border: 1px solid #ddd; border-radius: 8px; padding: 10px; background: transparent; }
        """)
        lay = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setStyleSheet("color:#666;")
        self.title.setFont(QFont("", 9))
        lay.addWidget(self.title)

        self.value_lbl = QLabel(value)
        self.value_lbl.setFont(QFont("", 18, QFont.Weight.Bold.value))
        lay.addWidget(self.value_lbl)

        self.subtitle = QLabel(subtitle)
        self.subtitle.setStyleSheet("color:#888; font-size:10px;")
        lay.addWidget(self.subtitle)

    def set(self, value: str, subtitle: str = ""):
        self.value_lbl.setText(value)
        self.subtitle.setText(subtitle)


class MiniChart(QWidget):
    """Simple matplotlib canvas wrapper for small charts"""
    def __init__(self, width=4, height=2.2, dpi=100):
        super().__init__()
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.canvas = FigureCanvas(self.figure)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.canvas)

    def plot_line(self, x, y, label=None, heatmap=False):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if heatmap:
            colors = ["green" if v >= 0 else "red" for v in y]
            ax.bar(x, y, color=colors)
        else:
            ax.plot(x, y, marker='o')
        if label:
            ax.set_title(label)
        ax.grid(True, linestyle=':', linewidth=0.5)
        self.canvas.draw()

    def plot_bar(self, x, y, label=None):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.bar(x, y)
        if label:
            ax.set_title(label)
        ax.grid(True, linestyle=':', linewidth=0.5)
        self.canvas.draw()


# ------------------------------
# Dashboard
# ------------------------------
class Dashboard(QWidget):
    # signals
    open_invoice_requested = pyqtSignal(int)   # invoice_id
    open_bill_requested = pyqtSignal(int)      # bill_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboard")
        self.build_ui()
        try:
            self.refresh()
        except Exception as e:
            print("[Dashboard] Initial refresh error:", e)

    # -------------------------
    # UI construction
    # -------------------------
    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(12)

        # Header: Title + controls
        header = QHBoxLayout()
        title = QLabel("<h2 style='margin:0'>Dashboard</h2>")
        header.addWidget(title)
        header.addStretch()

        # date macro filter
        self.filter_combo = QPushButton("Last 12 Months")
        self.filter_combo.setMenu(None)  # can extend later
        header.addWidget(self.filter_combo)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)

        self.btn_export = QPushButton("Export CSV")
        self.btn_export.clicked.connect(self._export_dashboard_csv)
        header.addWidget(self.btn_export)

        self.btn_print = QPushButton("Print")
        self.btn_print.clicked.connect(self._print_dashboard)
        header.addWidget(self.btn_print)

        outer.addLayout(header)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_bank = KPIWidget("Bank Balance", "R0.00", "Account: Bank Account")
        self.kpi_income = KPIWidget("Total Income (12m)", "R0.00", "")
        self.kpi_expenses = KPIWidget("Total Expenses (12m)", "R0.00", "")
        self.kpi_net = KPIWidget("Net Profit (12m)", "R0.00", "")

        for w in (self.kpi_bank, self.kpi_income, self.kpi_expenses, self.kpi_net):
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            kpi_row.addWidget(w)

        outer.addLayout(kpi_row)

        # Charts + lists area
        mid = QHBoxLayout()
        mid.setSpacing(12)

        # Left: charts
        left = QVBoxLayout()
        left.setSpacing(8)

        # cashflow heatmap
        self.chart_cashflow = MiniChart(width=6, height=2.4)
        left.addWidget(QLabel("<b>Cashflow Forecast (Next 6 Months)</b>"))
        left.addWidget(self.chart_cashflow)

        # income vs expenses
        self.chart_income_expenses = MiniChart(width=6, height=2.6)
        left.addWidget(QLabel("<b>Income vs Expenses (monthly)</b>"))
        left.addWidget(self.chart_income_expenses)

        # pl
        self.chart_pl = MiniChart(width=6, height=2.2)
        left.addWidget(QLabel("<b>Profit & Loss (summary)</b>"))
        left.addWidget(self.chart_pl)

        mid.addLayout(left, 2)

        # Right: lists
        right = QVBoxLayout()
        right.setSpacing(8)

        right.addWidget(QLabel("<b>Outstanding Invoices</b>"))
        # Create tables BEFORE wiring signals
        self.tbl_invoices = QTableWidget()
        self.tbl_invoices.setColumnCount(4)
        self.tbl_invoices.setHorizontalHeaderLabels(["ID", "Customer", "Due Date", "Amount"])
        self.tbl_invoices.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self.tbl_invoices, 1)

        right.addWidget(QLabel("<b>Overdue Bills</b>"))
        self.tbl_bills = QTableWidget()
        self.tbl_bills.setColumnCount(4)
        self.tbl_bills.setHorizontalHeaderLabels(["ID", "Vendor", "Due Date", "Amount"])
        self.tbl_bills.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self.tbl_bills, 1)

        right.addWidget(QLabel("<b>Top Customers (by invoiced total)</b>"))
        self.tbl_customers = QTableWidget()
        self.tbl_customers.setColumnCount(3)
        self.tbl_customers.setHorizontalHeaderLabels(["Customer", "Invoices", "Total"])
        self.tbl_customers.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self.tbl_customers, 1)

        mid.addLayout(right, 1)

        outer.addLayout(mid)

        # footer spacer
        outer.addItem(QSpacerItem(20, 10))

        # Connect signals after creation
        self.tbl_invoices.itemDoubleClicked.connect(self._invoice_row_clicked)
        self.tbl_bills.itemDoubleClicked.connect(self._bill_row_clicked)

    # -------------------------
    # Helpers
    # -------------------------
    def _table_exists(self, conn, name: str) -> bool:
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
            return cur.fetchone() is not None
        except Exception:
            return False

    def _invoice_row_clicked(self, item):
        try:
            row = item.row()
            inv_id_item = self.tbl_invoices.item(row, 0)
            if inv_id_item:
                invoice_id = int(inv_id_item.text())
                self.open_invoice_requested.emit(invoice_id)
        except Exception as e:
            print("[Dashboard] invoice click failed:", e)

    def _bill_row_clicked(self, item):
        try:
            row = item.row()
            bill_id_item = self.tbl_bills.item(row, 0)
            if bill_id_item:
                bill_id = int(bill_id_item.text())
                self.open_bill_requested.emit(bill_id)
        except Exception as e:
            print("[Dashboard] bill click failed:", e)

    # -------------------------
    # Data loading / main refresh
    # -------------------------
    def refresh(self):
        try:
            self._load_kpis()
            self._load_monthly_income_expenses_chart()
            self._load_pl_summary_chart()
            self._load_outstanding_invoices()
            self._load_overdue_bills()
            self._load_top_customers()
            self._load_cashflow_forecast()
        except Exception as e:
            print("[Dashboard] refresh failed:", e)

    def _load_kpis(self):
        # Bank balance — try to fetch from trial_balance by account code 1000 (Bank Account)
        try:
            tb = trial_balance()
            bank_balance = 0.0
            for a in tb:
                if a.get("account_code") == "1000":
                    bank_balance = a.get("balance") or 0.0
                    break
        except Exception:
            bank_balance = 0.0

        # P&L
        try:
            pl = profit_and_loss()
            total_income = sum(i.get("balance", 0) for i in pl.get("income", []))
            total_expenses = sum(e.get("balance", 0) for e in pl.get("expenses", []))
            net_profit = pl.get("net_profit", total_income - total_expenses)
        except Exception:
            total_income = 0.0
            total_expenses = 0.0
            net_profit = 0.0

        self.kpi_bank.set(f"R{bank_balance:,.2f}", "Primary bank account")
        self.kpi_income.set(f"R{total_income:,.2f}", "Trailing 12 months")
        self.kpi_expenses.set(f"R{total_expenses:,.2f}", "Trailing 12 months")
        self.kpi_net.set(f"R{net_profit:,.2f}", "Trailing 12 months")

    def _load_monthly_income_expenses_chart(self):
        conn = get_conn_safe()
        if not conn:
            # draw empty chart placeholders
            months = [(datetime.now() - timedelta(days=30*i)).strftime("%Y-%m") for i in range(11, -1, -1)]
            self.chart_income_expenses.plot_line(months, [0]*12, label="Income vs Expenses")
            return
        try:
            cur = conn.cursor()
            now = datetime.now()
            months = []
            income_series = []
            expense_series = []
            for i in range(11, -1, -1):
                start = (now.replace(day=1) - timedelta(days=30*i)).replace(day=1)
                months.append(start.strftime("%Y-%m"))
                inv_sum = 0.0
                bill_sum = 0.0
                if self._table_exists(conn, "invoices"):
                    r = cur.execute("SELECT IFNULL(SUM(total),0) as s FROM invoices WHERE substr(date,1,7)=? AND status != 'Draft'", (start.strftime("%Y-%m"),)).fetchone()
                    inv_sum = r["s"] if r else 0.0
                if self._table_exists(conn, "bills"):
                    r = cur.execute("SELECT IFNULL(SUM(total),0) as s FROM bills WHERE substr(date,1,7)=?", (start.strftime("%Y-%m"),)).fetchone()
                    bill_sum = r["s"] if r else 0.0
                income_series.append(inv_sum)
                expense_series.append(bill_sum)

            # fallback if all zeros
            if all(v == 0 for v in income_series) and all(v == 0 for v in expense_series):
                income_series = [0]*12
                expense_series = [0]*12

            # plot income minus expenses line for clarity
            net = [i - e for i, e in zip(income_series, expense_series)]
            self.chart_income_expenses.plot_line(months, net, label="Net Income (monthly)")
        except Exception as e:
            print("[Dashboard] income/expenses chart failed:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_pl_summary_chart(self):
        try:
            pl = profit_and_loss()
            income_total = sum(i.get("balance", 0) for i in pl.get("income", []))
            cogs_total = sum(i.get("balance", 0) for i in pl.get("cogs", []))
            expenses_total = sum(i.get("balance", 0) for i in pl.get("expenses", []))

            categories = ["Income", "COGS", "Expenses"]
            values = [income_total, cogs_total, expenses_total]
            self.chart_pl.plot_bar(categories, values, label="P&L Summary")
        except Exception as e:
            print("[Dashboard] P&L chart failed:", e)

    def _load_cashflow_forecast(self):
        conn = get_conn_safe()
        if not conn:
            months = [(datetime.now() + timedelta(days=30*i)).strftime("%Y-%m") for i in range(1,7)]
            self.chart_cashflow.plot_line(months, [0]*6, label="Cashflow Forecast", heatmap=True)
            return
        try:
            cur = conn.cursor()
            # avg invoices per month
            inc = 0.0
            exp = 0.0
            if self._table_exists(conn, "invoices"):
                r = cur.execute("SELECT IFNULL(AVG(m),0) AS avg_inc FROM (SELECT SUM(total) AS m FROM invoices WHERE status != 'Draft' GROUP BY substr(date,1,7) LIMIT 12)").fetchone()
                inc = r["avg_inc"] if r else 0.0
            if self._table_exists(conn, "bills"):
                r = cur.execute("SELECT IFNULL(AVG(m),0) AS avg_exp FROM (SELECT SUM(total) AS m FROM bills GROUP BY substr(date,1,7) LIMIT 12)").fetchone()
                exp = r["avg_exp"] if r else 0.0

            tb = trial_balance()
            opening = next((a.get("balance",0) for a in tb if a.get("account_code") == "1000"), 0)

            months = []
            values = []
            now = datetime.now()
            for i in range(1, 7):
                future = now + timedelta(days=30 * i)
                months.append(future.strftime("%Y-%m"))
                projected = opening + (inc - exp) * i
                values.append(projected)

            self.chart_cashflow.plot_line(months, values, label="Cashflow Forecast", heatmap=True)
        except Exception as e:
            print("[Dashboard] cashflow forecast failed:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_outstanding_invoices(self):
        conn = get_conn_safe()
        if not conn:
            self.tbl_invoices.setRowCount(0)
            return
        try:
            cur = conn.cursor()
            if not self._table_exists(conn, "invoices"):
                self.tbl_invoices.setRowCount(0)
                return
            rows = cur.execute("""
                SELECT i.id, COALESCE(c.name, '(Unknown)') as customer, i.due_date, i.total
                FROM invoices i
                LEFT JOIN customers c ON c.id = i.customer_id
                WHERE i.status != 'Paid' AND i.status != 'Draft'
                ORDER BY i.due_date ASC
                LIMIT 12
            """).fetchall()
            self.tbl_invoices.setRowCount(len(rows))
            for r, rr in enumerate(rows):
                self.tbl_invoices.setItem(r, 0, QTableWidgetItem(str(rr["id"])))
                self.tbl_invoices.setItem(r, 1, QTableWidgetItem(str(rr["customer"] or "")))
                self.tbl_invoices.setItem(r, 2, QTableWidgetItem(str(rr["due_date"] or "")))
                self.tbl_invoices.setItem(r, 3, QTableWidgetItem(f"R{(rr['total'] or 0):,.2f}"))
        except Exception as e:
            print("[Dashboard] load_outstanding_invoices failed:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_overdue_bills(self):
        conn = get_conn_safe()
        if not conn:
            self.tbl_bills.setRowCount(0)
            return
        try:
            cur = conn.cursor()
            if not self._table_exists(conn, "bills"):
                self.tbl_bills.setRowCount(0)
                return
            today = datetime.now().date().isoformat()
            rows = cur.execute("""
                SELECT b.id, COALESCE(v.name,'(Unknown)') as vendor, b.due_date, b.total
                FROM bills b
                LEFT JOIN vendors v ON v.id = b.vendor_id
                WHERE b.status != 'Paid' AND b.due_date < ?
                ORDER BY b.due_date ASC
                LIMIT 12
            """, (today,)).fetchall()
            self.tbl_bills.setRowCount(len(rows))
            for r, rr in enumerate(rows):
                self.tbl_bills.setItem(r, 0, QTableWidgetItem(str(rr["id"])))
                self.tbl_bills.setItem(r, 1, QTableWidgetItem(str(rr["vendor"] or "")))
                self.tbl_bills.setItem(r, 2, QTableWidgetItem(str(rr["due_date"] or "")))
                self.tbl_bills.setItem(r, 3, QTableWidgetItem(f"R{(rr['total'] or 0):,.2f}"))
        except Exception as e:
            print("[Dashboard] load_overdue_bills failed:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_top_customers(self):
        conn = get_conn_safe()
        if not conn:
            self.tbl_customers.setRowCount(0)
            return
        try:
            cur = conn.cursor()
            if not self._table_exists(conn, "invoices"):
                self.tbl_customers.setRowCount(0)
                return
            rows = cur.execute("""
                SELECT COALESCE(c.name,'(Unnamed)') AS name, COUNT(i.id) AS invoices, IFNULL(SUM(i.total),0) AS total
                FROM invoices i
                LEFT JOIN customers c ON c.id = i.customer_id
                GROUP BY c.id
                ORDER BY total DESC
                LIMIT 8
            """).fetchall()
            self.tbl_customers.setRowCount(len(rows))
            for r, rr in enumerate(rows):
                self.tbl_customers.setItem(r, 0, QTableWidgetItem(str(rr["name"] or "(Unnamed)")))
                self.tbl_customers.setItem(r, 1, QTableWidgetItem(str(rr["invoices"] or 0)))
                self.tbl_customers.setItem(r, 2, QTableWidgetItem(f"R{(rr['total'] or 0):,.2f}"))
        except Exception as e:
            print("[Dashboard] load_top_customers failed:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # -------------------------
    # Export & Print
    # -------------------------
    def _export_dashboard_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Dashboard Data", "dashboard.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Bank Balance", self.kpi_bank.value_lbl.text()])
                writer.writerow(["Income (12m)", self.kpi_income.value_lbl.text()])
                writer.writerow(["Expenses (12m)", self.kpi_expenses.value_lbl.text()])
                writer.writerow(["Net Profit (12m)", self.kpi_net.value_lbl.text()])
                writer.writerow([])
                writer.writerow(["Top Customers"])
                for row in range(self.tbl_customers.rowCount()):
                    writer.writerow([
                        self.tbl_customers.item(row,0).text(),
                        self.tbl_customers.item(row,1).text(),
                        self.tbl_customers.item(row,2).text(),
                    ])
            print("Dashboard exported to", path)
        except Exception as e:
            print("Export failed:", e)

    def _print_dashboard(self):
        printer = QPrinter()
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            # Render widget to printer
            self.render(printer)

    # -------------------------
    # What-if simple simulation
    # -------------------------
    def simulate_profit(self, extra_revenue=0.0, extra_expense=0.0):
        try:
            pl = profit_and_loss()
            income = sum(i.get("balance",0) for i in pl.get("income",[])) + extra_revenue
            expenses = sum(e.get("balance",0) for e in pl.get("expenses",[])) + extra_expense
            gross = income - sum(i.get("balance",0) for i in pl.get("cogs",[]))
            net = gross - expenses
            return {"income": income, "expenses": expenses, "net": net}
        except Exception as e:
            print("Simulation failed:", e)
            return {"income":0, "expenses":0, "net":0}

# End of file
