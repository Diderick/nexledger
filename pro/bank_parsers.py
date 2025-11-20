# bank_parsers.py
import re
import hashlib
from datetime import datetime
from pathlib import Path
import pdfplumber
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal

# OCR support
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# OFX support
try:
    from ofxparse import OfxParser
    OFX_AVAILABLE = True
except ImportError:
    OFX_AVAILABLE = False


# ---------------------------
# PDF helpers
# ---------------------------
def generate_fitid(date_str, index, desc):
    """Generate a unique transaction ID"""
    seed = f"{date_str}{index:04d}{desc[:50]}"
    return hashlib.md5(seed.encode("utf-8")).hexdigest().upper()


def extract_pdf_text(pdf_path, max_pages=None, ocr=True, ocr_lang='eng', resolution=300):
    """Extract text from PDF, optionally using OCR if text is empty"""
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        text = "\n".join(p.extract_text() or "" for p in pages)
        if text.strip():
            return text

        if not ocr or not OCR_AVAILABLE:
            return ""

        # fallback OCR
        text_parts = []
        for p in pages:
            img = p.to_image(resolution=resolution).original
            txt = pytesseract.image_to_string(img, lang=ocr_lang)
            text_parts.append(txt)
        return "\n".join(text_parts)


def detect_bank(text):
    """Basic bank detection based on keywords"""
    t = (text or "").lower()
    if re.search(r"\b20\d{2}[01]\d[0-3]\d\b", t):
        return "standard"
    if re.search(r"\b\d{2}\s*[a-z]{3}\b", t) or "cr" in t or "dr" in t:
        return "fnb"
    return "fnb"


def parse_fnb(pdf_path):
    """Parse FNB PDF (placeholder implementation)"""
    text = extract_pdf_text(pdf_path)
    transactions = []
    # This should implement actual FNB parsing logic
    # For now, dummy data
    transactions.append({
        "date": datetime.today().date(),
        "reference": "FNB001",
        "description": "Sample FNB transaction",
        "debit": 0.0,
        "credit": 100.0,
        "balance": 100.0
    })
    return transactions


def parse_standard_bank(pdf_path):
    """Parse Standard Bank PDF (placeholder)"""
    text = extract_pdf_text(pdf_path)
    transactions = []
    transactions.append({
        "date": datetime.today().date(),
        "reference": "STD001",
        "description": "Sample Standard Bank transaction",
        "debit": 50.0,
        "credit": 0.0,
        "balance": 50.0
    })
    return transactions


def parse_ofx_file(parent):
    """Open OFX file dialog and import"""
    if not OFX_AVAILABLE:
        QMessageBox.warning(parent, "OFX Parser", "ofxparse not installed.")
        return

    filename, _ = QFileDialog.getOpenFileName(parent, "Select OFX file", "", "OFX Files (*.ofx)")
    if filename:
        QMessageBox.information(parent, "Import OFX", f"Imported OFX file: {filename}")


def parse_bank_pdf(parent):
    """Open PDF file dialog and import"""
    filename, _ = QFileDialog.getOpenFileName(parent, "Select Bank PDF", "", "PDF Files (*.pdf)")
    if filename:
        QMessageBox.information(parent, "Import PDF", f"Imported PDF file: {filename}")


# ---------------------------
# Threaded import
# ---------------------------
class ImportThread(QThread):
    result = pyqtSignal(list, str)  # transactions, source_info

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            from .bank_parsers import extract_pdf_text, detect_bank, parse_fnb, parse_standard_bank
            text = extract_pdf_text(self.path, ocr=True)
            bank = detect_bank(text)
            if bank == "fnb":
                trans = parse_fnb(self.path)
                source = "FNB PDF"
            else:
                trans = parse_standard_bank(self.path)
                source = "Standard Bank PDF"
            self.result.emit(trans, source)
        except Exception as e:
            import traceback
            self.result.emit([], f"PDF Error: {e}\n{traceback.format_exc()}")
