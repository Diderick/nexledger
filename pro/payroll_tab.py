# pro/payroll_tab.py
# FINAL FIXED – 13 November 2025

import csv
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QLabel, QMessageBox, QHeaderView,
    QDateEdit, QFileDialog, QDialog, QFormLayout, QDialogButtonBox,
    QDoubleSpinBox, QTabWidget
)
from PyQt6.QtCore import Qt, QDate
from shared.db import get_conn, log_audit
from shared.theme import is_dark_mode


def getUIF(salary):
    salary = salary/100
    return salary



class PayrollTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        self.refresh_employees()
        self.refresh_runs()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Payroll</h2>")
        header.addWidget(title)

        add_employee_btn = QPushButton("Add Employee")
        add_employee_btn.clicked.connect(self.add_employee)
        header.addWidget(add_employee_btn)

        process_payroll_btn = QPushButton("Run Payroll")
        process_payroll_btn.clicked.connect(self.run_payroll)
        header.addWidget(process_payroll_btn)

        export_btn = QPushButton("Export EMP201")
        export_btn.clicked.connect(self.export_emp201)
        header.addWidget(export_btn)

        layout.addLayout(header)

        # === TABS FOR EMPLOYEES & RUNS ===
        tabs = QTabWidget()
        self.employee_table = QTableWidget()
        self.employee_table.setColumnCount(8)
        self.employee_table.setHorizontalHeaderLabels([
            "ID", "Name", "Tax No", "Salary", "PAYE", "UIF Emp", "UIF Emp'r", "SDL"
        ])
        self.employee_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.runs_table = QTableWidget()
        self.runs_table.setColumnCount(7)
        self.runs_table.setHorizontalHeaderLabels([
            "Run ID", "Date", "Period", "Gross", "Net", "PAYE", "UIF+SDL"
        ])
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        tabs.addTab(self.employee_table, "Employees")
        tabs.addTab(self.runs_table, "Payroll Runs")
        layout.addWidget(tabs)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)

    def refresh_employees(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, tax_number, salary, paye_rate, uif_rate, sdl_rate
                FROM employees
                ORDER BY name
            """)
            rows = cur.fetchall()
            conn.close()

            self.employee_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    item = QTableWidgetItem(str(val) if val is not None else "")
                    if c == 3:  # Salary
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
                    self.employee_table.setItem(r, c, item)

            self.status.setText(f"{len(rows)} employees")
        except Exception as e:
            self.status.setText(f"Error: {e}")

    def refresh_runs(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT pr.id, pr.run_date, pr.period, pr.total_gross, pr.total_net,
                       pr.total_paye, pr.total_uif + pr.total_sdl as total_deductions
                FROM payroll_runs pr
                ORDER BY pr.run_date DESC
            """)
            rows = cur.fetchall()
            conn.close()

            self.runs_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    item = QTableWidgetItem(str(val) if val is not None else "")
                    if c in [3, 4, 5, 6]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
                    self.runs_table.setItem(r, c, item)
        except Exception as e:
            print("Runs refresh error:", e)




    def add_employee(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Employee")
        dialog.setFixedSize(400, 350)
        lay = QFormLayout(dialog)

        name_edit = QLineEdit()
        tax_no_edit = QLineEdit()
        salary_spin = QDoubleSpinBox()
        salary_spin.setRange(0.00, 10000000.00)

        lay.addRow("Name:", name_edit)
        lay.addRow("Tax Number:", tax_no_edit)
        lay.addRow("Monthly Salary:", salary_spin)

        btns = QDialogButtonBox()
        btns.addButton("Add", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        lay.addRow(btns)

        def save():
            name = name_edit.text().strip()
            tax_no = tax_no_edit.text().strip()
            salary = salary_spin.value()
            if not name:
                QMessageBox.warning(dialog, "Error", "Name and salary required.")
                return

            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO employees (name, tax_number, salary, paye_rate, uif_rate, sdl_rate)
                    VALUES (?, ?, ?, 0, ?, 0.01)
                """, (name, tax_no, salary, getUIF(salary)))
                conn.commit()
                conn.close()
                log_audit(f"Added employee: {name}")
                dialog.accept()
                self.refresh_employees()
            except Exception as e:
                QMessageBox.critical(dialog, "Error", str(e))

        btns.accepted.connect(save)
        dialog.exec()



    def run_payroll(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Run Payroll")
        dialog.setFixedSize(400, 200)
        lay = QFormLayout(dialog)

        period_edit = QDateEdit()
        period_edit.setCalendarPopup(True)
        period_edit.setDate(QDate.currentDate())
        lay.addRow("Payroll Date:", period_edit)

        btns = QDialogButtonBox()
        btns.addButton("Process", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        lay.addRow(btns)

        def process():
            period = period_edit.date().toString("yyyy-MM")
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO payroll_runs (run_date, period, total_gross, total_net, total_paye, total_uif, total_sdl)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (period_edit.date().toString("yyyy-MM-dd"), period, 0, 0, 0, 0, 0))
                run_id = cur.lastrowid
                conn.commit()

                total_gross = total_net = total_paye = total_uif = total_sdl = 0
                cur.execute("SELECT * FROM employees")
                employees = cur.fetchall()
                for emp in employees:
                    gross = emp["salary"]
                    paye = gross * 0.2
                    uif_emp = gross * 0.01
                    uif_emp_r = gross * 0.01
                    sdl = gross * 0.01
                    net = gross - paye - uif_emp

                    total_gross += gross
                    total_net += net
                    total_paye += paye
                    total_uif += uif_emp + uif_emp_r
                    total_sdl += sdl

                    cur.execute("""
                        INSERT INTO payroll_items (run_id, employee_id, gross, paye, uif_employee, uif_employer, sdl, net)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (run_id, emp["id"], gross, paye, uif_emp, uif_emp_r, sdl, net))

                cur.execute("""
                    UPDATE payroll_runs SET total_gross=?, total_net=?, total_paye=?, total_uif=?, total_sdl=? 
                    WHERE id=?
                """, (total_gross, total_net, total_paye, total_uif, total_sdl, run_id))
                conn.commit()
                conn.close()

                log_audit(f"Processed payroll for {period}: {len(employees)} employees")
                dialog.accept()
                self.refresh_runs()
                QMessageBox.information(self, "Success", f"Payroll run for {period} completed.")
            except Exception as e:
                QMessageBox.critical(dialog, "Error", str(e))

        btns.accepted.connect(process)
        dialog.exec()

    def export_emp201(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export EMP201", "EMP201.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT pr.period, pr.total_paye, pr.total_uif, pr.total_sdl
                FROM payroll_runs pr
                ORDER BY pr.period DESC
                LIMIT 12
            """)
            rows = cur.fetchall()
            conn.close()

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Period", "PAYE", "UIF", "SDL"])
                for r in rows:
                    writer.writerow([r[0], r[1], r[2], r[3]])
            QMessageBox.information(self, "Exported", f"EMP201 saved: {path}")
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
        self.employee_table.setStyleSheet(style)
        self.runs_table.setStyleSheet(style)
        self.setStyleSheet(f"background: {bg}; color: {text};")