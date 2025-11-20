# ui_enhancements.py
# UI Enhancements for NexLedger Pro — Animations, Chart Styling, Invoice PDF, Report PDF
# Use alongside shared/theme.py and the existing PyQt6 app.

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, QRect
from PyQt6.QtWidgets import QWidget, QFileDialog, QMessageBox
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rcanvas
from reportlab.lib.units import mm
from reportlab.lib import colors
import sqlite3
import os
from shared.theme import is_dark_mode, EMERALD, GOLD, EMERALD_LIGHT
from shared.db import get_conn
from datetime import datetime

# -----------------------------
# Sidebar animation
# -----------------------------

def animate_sidebar(frame: QWidget, expand: bool, duration: int = 300):
    """Smoothly expand or collapse a sidebar QFrame.
    frame: the QFrame instance
    expand: True to expand to its stored "target_width", False to collapse to 0
    duration: milliseconds

    Requires that the frame has an integer property "target_width" set (or pass current width).
    """
    target = getattr(frame, 'target_width', frame.width() or 230)
    start = 0 if expand else target
    end = target if expand else 0
    anim = QPropertyAnimation(frame, b"minimumWidth")
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
    anim.start()
    # keep reference so Python GC doesn't kill the animation
    frame._sidebar_anim = anim
    return anim


# -----------------------------
# Matplotlib theme helper
# -----------------------------

def apply_matplotlib_theme():
    """Apply Gold & Emerald style to matplotlib global rcParams for consistent charts."""
    dark = is_dark_mode()
    if dark:
        mpl.rcParams.update({
            'figure.facecolor': '#0A0F0A',
            'axes.facecolor': '#0A0F0A',
            'axes.edgecolor': '#F6F6F6',
            'axes.labelcolor': '#F6F6F6',
            'xtick.color': '#F6F6F6',
            'ytick.color': '#F6F6F6',
            'text.color': '#F6F6F6',
            'grid.color': '#333333',
            'axes.prop_cycle': mpl.cycler('color', [EMERALD, EMERALD_LIGHT, GOLD, '#F1D06E', '#00A878'])
        })
    else:
        mpl.rcParams.update({
            'figure.facecolor': '#FFFFFF',
            'axes.facecolor': '#FFFFFF',
            'axes.edgecolor': '#003F2A',
            'axes.labelcolor': '#003F2A',
            'xtick.color': '#003F2A',
            'ytick.color': '#003F2A',
            'text.color': '#003F2A',
            'grid.color': '#EAEAEA',
            'axes.prop_cycle': mpl.cycler('color', [EMERALD, EMERALD_LIGHT, GOLD, '#F1D06E', '#00A878'])
        })


def style_canvas_for_small(chart_canvas: FigureCanvas):
    """Apply thin axes and tight layout to a given FigureCanvas instance."""
    fig = chart_canvas.figure
    for ax in fig.axes:
        ax.tick_params(axis='x', which='major', labelsize=9)
        ax.tick_params(axis='y', which='major', labelsize=9)
        ax.grid(True, linestyle=':', linewidth=0.5)
    fig.tight_layout()
    chart_canvas.draw()


# -----------------------------
# Invoice PDF generator (simple, branded)
# -----------------------------

def generate_invoice_pdf(invoice_id: int, out_path: str | None = None):
    """Generate a simple branded invoice PDF using reportlab.
    Requires invoices and invoice_items tables from db.py schema.
    Returns path to generated PDF or raises exception.
    """
    conn = get_conn()
    cur = conn.cursor()
    inv = cur.execute("SELECT i.*, c.name as customer_name, c.address as customer_address FROM invoices i LEFT JOIN customers c ON c.id = i.customer_id WHERE i.id=?", (invoice_id,)).fetchone()
    if not inv:
        raise ValueError("Invoice not found")
    items = cur.execute("SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()

    if out_path is None:
        out_dir = os.getcwd()
        out_path = os.path.join(out_dir, f"invoice_{invoice_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")

    c = rcanvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    # Header - company
    c.setFillColor(colors.HexColor(EMERALD))
    c.rect(0, height-80, width, 80, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(30, height-50, f"NexLedger Pro")
    c.setFont("Helvetica", 10)
    c.drawString(30, height-65, f"Invoice #: {inv['id']}      Date: {inv['date']}")

    # Customer
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, height-110, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(30, height-125, inv.get('customer_name') or '(Unknown)')
    if inv.get('customer_address'):
        c.drawString(30, height-140, str(inv.get('customer_address')))

    # Table header
    y = height-180
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor(EMERALD))
    c.drawString(30, y, "Description")
    c.drawString(380, y, "Qty")
    c.drawString(430, y, "Unit")
    c.drawString(500, y, "Total")
    c.setFillColor(colors.black)

    y -= 18
    c.setFont("Helvetica", 9)
    total = 0
    for it in items:
        desc = it.get('description') or ''
        qty = it.get('qty') or 0
        price = it.get('price') or 0
        line_total = (qty or 0) * (price or 0)
        c.drawString(30, y, str(desc)[:60])
        c.drawRightString(450, y, f"{qty:.2f}")
        c.drawRightString(500, y, f"{price:.2f}")
        c.drawRightString(560, y, f"{line_total:.2f}")
        y -= 16
        total += line_total
        if y < 80:
            c.showPage(); y = height-80

    # Totals
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(560, y-6, f"Subtotal: {total:.2f}")
    c.drawRightString(560, y-24, f"VAT: {inv.get('vat',0):.2f}")
    c.drawRightString(560, y-42, f"Total: {inv.get('total', total):.2f}")

    # Footer
    c.setFont("Helvetica", 9)
    c.drawString(30, 40, "Thank you for your business!")
    c.save()
    conn.close()
    return out_path


# -----------------------------
# Report PDF exporter (renders a simple tabular report)
# -----------------------------

def export_report_pdf(title: str, headers: list, rows: list, out_path: str | None = None):
    """Export a generic report (headers + list-of-rows) to a branded PDF."""
    if out_path is None:
        out_path = os.path.join(os.getcwd(), f"report_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")

    c = rcanvas.Canvas(out_path, pagesize=landscape(A4))
    w, h = landscape(A4)

    # Header
    c.setFillColor(colors.HexColor(EMERALD))
    c.rect(0, h-60, w, 60, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, h-40, title)

    # Table start
    x = 30
    y = h-90
    c.setFont("Helvetica-Bold", 10)
    col_x = [x]
    col_width = (w - 60) / len(headers) if headers else (w - 60)
    for i, head in enumerate(headers):
        c.drawString(x + (i * col_width) + 4, y, str(head))
    y -= 18
    c.setFont("Helvetica", 9)
    for r in rows:
        for i, cell in enumerate(r):
            tx = str(cell)
            c.drawString(x + (i * col_width) + 4, y, tx[:int(col_width/6)])
        y -= 14
        if y < 40:
            c.showPage(); y = h-60
    c.save()
    return out_path


# -----------------------------
# Helper: Open generated file (platform open)
# -----------------------------

def open_file(path: str):
    try:
        if os.name == 'nt':
            os.startfile(path)
        elif os.name == 'posix':
            os.system(f'xdg-open "{path}"')
        else:
            os.system(f'open "{path}"')
    except Exception as e:
        print('Open file failed', e)


# -----------------------------
# Example bindings for main UI
# -----------------------------
# In your main window you can wire:
# anim = animate_sidebar(self.sidebar, expand=True)
# apply_matplotlib_theme()
# generate_invoice_pdf(12)
# export_report_pdf('Trial Balance', ['Account','Debit','Credit'], rows)

