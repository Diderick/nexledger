# pro/bank_feeds_tab.py
# MERGED FINAL – Bank Feeds (CSV / PDF / OFX) – 13 Nov 2025 (Merged OFX fixes + original GUI)

import csv
import re
import os
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QFileDialog, QProgressBar, QHeaderView,
    QAbstractItemView, QDialog, QVBoxLayout as DialogLayout, QDialogButtonBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from shared.db import get_conn, is_duplicate_transaction, log_audit
from shared.theme import is_dark_mode

# Optional libraries
try:
    import fitz  # PyMuPDF
    HAS_PDF_FITZ = True
except Exception:
    HAS_PDF_FITZ = False

try:
    import pdfplumber
    HAS_PDF_PLP = True
except Exception:
    HAS_PDF_PLP = False

try:
    from ofxparse import OfxParser
    HAS_OFXPARSE = True
except Exception:
    HAS_OFXPARSE = False


# --------------------------
# Helper: widget style (moved outside classes)
# --------------------------
def get_widget_style():
    dark = is_dark_mode()
    bg = "#2d2d2d" if dark else "#ffffff"
    text = "#ffffff" if dark else "#000000"
    border = "#444" if dark else "#ddd"
    return f"""
        QDialog {{ background: {bg}; color: {text}; }}
        QTableWidget {{ background: {bg}; color: {text}; gridline-color: {border}; }}
        QHeaderView::section {{ background: #0078d4; color: white; padding: 10px; }}
        QCheckBox {{ color: {text}; }}
    """


# --------------------------
# Thread: Importing/parsing worker
# --------------------------
class BankFeedImportThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            ext = Path(self.file_path).suffix.lower()
            if ext == '.csv':
                transactions = self.parse_csv()
            elif ext == '.pdf':
                transactions = self.parse_pdf()
            elif ext == '.ofx':
                transactions = self.parse_ofx()
            else:
                self.error.emit("Unsupported file type")
                return

            self.finished.emit(transactions)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error.emit(f"{e}\n\n{tb}")

    # --------------------------
    def parse_csv(self):
        transactions = []
        with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Try to detect dialect and header
            try:
                sample = f.read(4096)
                f.seek(0)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            # If no recognized header, fallback to positional
            for row in reader:
                # try common header names
                date_raw = row.get('Date') or row.get('date') or row.get('Transaction Date') or row.get('Value Date') or next(iter(row.values()), '')
                desc = row.get('Description') or row.get('Narrative') or row.get('Memo') or row.get('Payee') or ''
                amount_raw = row.get('Amount') or row.get('Amt') or row.get('Value') or row.get('Credit') or row.get('Debit') or ''
                date = self.parse_date(date_raw)
                amount = self.parse_amount(amount_raw)
                txn_type = 'Income' if amount > 0 else 'Expense'
                transactions.append({'date': date, 'description': desc.strip(), 'amount': amount, 'type': txn_type})
        return transactions

    # --------------------------
    def parse_pdf(self):
        text = ""
        # prefer fitz
        if HAS_PDF_FITZ:
            try:
                doc = fitz.open(self.file_path)
                for page in doc:
                    text += page.get_text()
                doc.close()
            except Exception:
                text = ""
        if not text and HAS_PDF_PLP:
            try:
                with pdfplumber.open(self.file_path) as pdf:
                    for p in pdf.pages:
                        text += p.extract_text() or ""
            except Exception:
                text = ""

        if not text:
            raise ValueError("No text extracted from PDF (missing fitz/pdfplumber?)")

        # split into lines and find rows
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        transactions = []
        i = 0
        # pattern for dates like 12/11/2025 or 20251112 or 12-11-2025
        date_pat = re.compile(r'(\d{2}[/-]\d{2}[/-]\d{2,4}|\d{8}|\d{4}[/-]\d{2}[/-]\d{2})')
        amount_pat = re.compile(r'([+-]?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2}))')
        while i < len(lines):
            line = lines[i]
            if date_pat.search(line):
                # try to extract date first from line
                date_match = date_pat.search(line)
                date_raw = date_match.group(1)
                date = self.parse_date(date_raw)
                # description: collect following lines until we find amount pattern
                desc_parts = [line[:date_match.start()].strip()] if date_match.start() > 0 else []
                j = i + 1
                amt = None
                while j < len(lines):
                    am = amount_pat.search(lines[j])
                    if am:
                        amt = am.group(1)
                        break
                    desc_parts.append(lines[j])
                    j += 1
                description = " ".join([p for p in desc_parts if p]).strip() or "PDF Import"
                amount = self.parse_amount(amt) if amt else 0.0
                txn_type = 'Income' if amount > 0 else 'Expense'
                transactions.append({'date': date, 'description': description, 'amount': amount, 'type': txn_type})
                i = j + 1
            else:
                i += 1
        return transactions

    # --------------------------
    def parse_ofx(self):
        # Prefer ofxparse (robust XML parser) if available
        try:
            if HAS_OFXPARSE:
                with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
                # If contains SGML header, find <OFX> start and parse from there
                start = raw.find('<OFX')
                content = raw[start:] if start != -1 else raw
                # ofxparse expects a file-like object
                from io import StringIO
                ofx = OfxParser.parse(StringIO(content))
                transactions = []
                # ofx.account can be savings or checking; iterate statements
                acct = getattr(ofx, 'account', None)
                if acct and getattr(acct, 'statement', None):
                    stm = acct.statement
                    for txn in stm.transactions:
                        date = txn.date.strftime('%Y-%m-%d') if txn.date else datetime.now().strftime('%Y-%m-%d')
                        amount = float(txn.amount) if txn.amount is not None else 0.0
                        memo = (txn.memo or txn.payee or '').strip()
                        desc = re.sub(r'\s+', ' ', memo)[:200]
                        ttype = 'Income' if amount > 0 else 'Expense'
                        transactions.append({'date': date, 'description': desc, 'amount': amount, 'type': ttype})
                return transactions
        except Exception:
            # fall back to regex parser below
            pass

        # Fallback manual OFX parser (resilient to SGML-ish OFX)
        transactions = []
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # cut to <OFX> if present
            start = content.find('<OFX')
            if start != -1:
                content = content[start:]
            # find STMTTRN blocks
            blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', content, flags=re.DOTALL | re.IGNORECASE)
            for blk in blocks:
                # date patterns: <DTPOSTED>20251112 or <DTPOSTED>20251112120000
                dm = re.search(r'<DTPOSTED>\s*([0-9]{8,14})', blk, re.IGNORECASE)
                am = re.search(r'<TRNAMT>\s*([+-]?\d+[\.,]?\d*)', blk, re.IGNORECASE)
                nm = re.search(r'<NAME>\s*([^<\r\n]+)', blk, re.IGNORECASE)
                mm = re.search(r'<MEMO>\s*([^<\r\n]+)', blk, re.IGNORECASE)
                if not am:
                    continue
                # date
                date_str = dm.group(1) if dm else ''
                date = self.parse_date_ofx(date_str)
                amount = float(am.group(1).replace(',', '.')) if am else 0.0
                name = (nm.group(1).strip() if nm else '') or (mm.group(1).strip() if mm else '')
                desc = re.sub(r'\s+', ' ', name)[:200] or 'OFX Import'
                ttype = 'Income' if amount > 0 else 'Expense'
                transactions.append({'date': date, 'description': desc, 'amount': amount, 'type': ttype})
        except Exception as e:
            raise ValueError(f"OFX parse failed: {e}")
        return transactions

    # --------------------------
    def parse_date(self, date_str: str) -> str:
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        date_str = str(date_str).strip()
        # try multiple formats
        fmts = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y%m%d', '%d%m%Y', '%d.%m.%Y', '%m/%d/%Y']
        for fmt in fmts:
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue
        # if contains 8 digits
        m = re.search(r'(\d{8})', date_str)
        if m:
            try:
                return datetime.strptime(m.group(1), '%Y%m%d').strftime('%Y-%m-%d')
            except:
                pass
        # fallback
        return datetime.now().strftime('%Y-%m-%d')

    def parse_date_ofx(self, dtstr: str) -> str:
        if not dtstr:
            return datetime.now().strftime('%Y-%m-%d')
        # common OFX forms: YYYYMMDD or YYYYMMDDHHMMSS or YYYYMMDDHHMMSS.fff
        m = re.match(r'(\d{4})(\d{2})(\d{2})', dtstr)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime('%Y-%m-%d')
            except:
                pass
        # fallback to generic parsing
        return self.parse_date(dtstr)

    def parse_amount(self, amount_str) -> float:
        if amount_str is None:
            return 0.0
        s = str(amount_str).strip()
        if not s:
            return 0.0
        # remove spaces and thousands separators, keep dot as decimal, handle comma decimals
        # if both comma and dot present, assume comma is thousands, dot decimal; else if only comma, treat as decimal
        s_clean = s.replace(' ', '')
        if s_clean.count('.') > 0 and s_clean.count(',') > 0:
            s_clean = s_clean.replace(',', '')
        elif s_clean.count(',') > 0 and s_clean.count('.') == 0:
            s_clean = s_clean.replace(',', '.')
        s_clean = re.sub(r'[^\d\.-]', '', s_clean)
        try:
            return float(s_clean)
        except Exception:
            return 0.0


# --------------------------
# Main BankFeedsTab (GUI from first file)
# --------------------------
class BankFeedsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title = QLabel("<h2>Bank Feeds</h2>")
        header.addWidget(title)
        header.addStretch()

        import_btn = QPushButton("Import File")
        import_btn.clicked.connect(self.import_file)
        import_btn.setStyleSheet("font-weight: bold; padding: 8px 16px;")
        header.addWidget(import_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_data)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Status
        self.status = QLabel("No transactions imported yet")
        layout.addWidget(self.status)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Type", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(48)
        layout.addWidget(self.table)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Bank Statement",
            "", "Bank Files (*.csv *.pdf *.ofx);;CSV (*.csv);;PDF (*.pdf);;OFX (*.ofx)"
        )
        if not path:
            return

        ext = Path(path).suffix.lower()
        if ext not in ['.csv', '.pdf', '.ofx']:
            QMessageBox.warning(self, "Error", "Unsupported file type")
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # Indeterminate

        self.worker = BankFeedImportThread(path)
        self.worker.progress.connect(lambda v: self.progress.setValue(v))
        self.worker.finished.connect(self.import_finished)
        self.worker.error.connect(self.import_error)
        self.worker.start()

    def import_finished(self, transactions):
        self.progress.setVisible(False)
        if not transactions:
            self.status.setText("No transactions found")
            return

        # Show preview dialog
        preview = ImportPreviewDialog(transactions, self)
        if preview.exec() == QDialog.DialogCode.Accepted:
            # selected_transactions attribute filled by dialog
            self.save_transactions(preview.selected_transactions)
        else:
            self.status.setText(f"Preview cancelled: {len(transactions)} transactions")

    def import_error(self, error):
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Import Error", error)
        self.status.setText("Import failed")

    def save_transactions(self, transactions):
        try:
            imported = 0
            with get_conn() as conn:
                cur = conn.cursor()
                for txn in transactions:
                    # use duplicate check helper (which itself uses get_conn internally)
                    if is_duplicate_transaction(txn['date'], txn['description']):
                        continue
                    cur.execute("""
                        INSERT INTO transactions (date, description, amount, type)
                        VALUES (?, ?, ?, ?)
                    """, (txn['date'], txn['description'], txn['amount'], txn['type']))
                    imported += 1
                conn.commit()

            if imported:
                log_audit(f"Imported {imported} transactions")
            self.refresh_data()
            QMessageBox.information(self, "Success", f"Imported {imported} transactions")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def refresh_data(self):
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT t.date, t.description, t.amount, t.type,
                           CASE WHEN t.type = 'Income' THEN 'Imported' ELSE 'Imported' END as status
                    FROM transactions t
                    ORDER BY t.date DESC
                    LIMIT 100
                """)
                rows = cur.fetchall()

            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                date_val = row[0] if row[0] is not None else ""
                desc_val = row[1] if row[1] is not None else ""
                amt_val = float(row[2]) if row[2] is not None else 0.0
                type_val = row[3] if row[3] is not None else ""
                status_val = row[4] if row[4] is not None else ""

                self.table.setItem(r, 0, QTableWidgetItem(str(date_val)))
                self.table.setItem(r, 1, QTableWidgetItem(str(desc_val)))
                amt_item = QTableWidgetItem(f"R{abs(amt_val):,.2f}")
                amt_item.setForeground(Qt.GlobalColor.green if amt_val > 0 else Qt.GlobalColor.red)
                amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
                self.table.setItem(r, 2, amt_item)
                self.table.setItem(r, 3, QTableWidgetItem(str(type_val)))
                self.table.setItem(r, 4, QTableWidgetItem(str(status_val)))

            self.status.setText(f"{len(rows)} transactions loaded")
            self.apply_theme()
        except Exception as e:
            self.status.setText(f"Error: {e}")

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
        self.table.setStyleSheet(style)
        self.setStyleSheet(f"background: {bg}; color: {text};")


# --------------------------
# Import Preview Dialog (keeps original GUI behavior)
# --------------------------
class ImportPreviewDialog(QDialog):
    def __init__(self, transactions, parent=None):
        super().__init__(parent)
        self.transactions = transactions
        self.selected_transactions = []
        self.setWindowTitle("Import Preview")
        self.setFixedSize(800, 600)
        self.setStyleSheet(get_widget_style())

        layout = DialogLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel(f"<h3>Import Preview ({len(transactions)} transactions)</h3>"))

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Type", "Import"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.table.setRowCount(len(transactions))
        for r, txn in enumerate(transactions):
            self.table.setItem(r, 0, QTableWidgetItem(str(txn['date'])))
            self.table.setItem(r, 1, QTableWidgetItem(txn['description']))
            amount = float(txn['amount'])
            amt_item = QTableWidgetItem(f"R{abs(amount):,.2f}")
            amt_item.setForeground(Qt.GlobalColor.green if amount > 0 else Qt.GlobalColor.red)
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(r, 2, amt_item)
            self.table.setItem(r, 3, QTableWidgetItem(txn['type']))

            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, row=r: self.toggle_import(row, state))
            self.table.setCellWidget(r, 4, checkbox)

        layout.addWidget(self.table)

        btns = QDialogButtonBox()
        btns.addButton("Import Selected", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def toggle_import(self, row, state):
        if state == Qt.CheckState.Checked.value:
            # add if not present
            if self.transactions[row] not in self.selected_transactions:
                self.selected_transactions.append(self.transactions[row])
        else:
            self.selected_transactions = [t for t in self.selected_transactions if t != self.transactions[row]]

    def accept(self):
        self.selected_transactions = []
        for r in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(r, 4)
            if checkbox and checkbox.isChecked():
                self.selected_transactions.append(self.transactions[r])
        super().accept()
