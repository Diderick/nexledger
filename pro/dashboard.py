import pyqtgraph as pg
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from shared.db import get_conn, get_conn_raw
from shared.theme import is_dark_mode


class Dashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(5000)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)


        # ———————— CARDS ROW ————————
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        cards_layout.setContentsMargins(0, 0, 0, 0)

        self.card_income = self.create_card("Total Income", "R0.00", "#28a745")
        self.card_expense = self.create_card("Total Expenses", "R0.00", "#dc3545")
        self.card_balance = self.create_card("Net Balance", "R0.00", "#0d6efd")

        for card in (self.card_income, self.card_expense, self.card_balance):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setMinimumHeight(140)
            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)

        # ———————— CHART ————————
        self.chart = pg.PlotWidget()
        self.chart.setBackground('transparent')
        self.chart.showGrid(x=True, y=True, alpha=0.7)
        self.chart.setLabel('left', 'Amount (R)')
        self.chart.setLabel('bottom', 'Date')
        self.chart.setTitle("Income vs Expenses Over Time")

        axis = pg.DateAxisItem(orientation='bottom')
        self.chart.setAxisItems({'bottom': axis})

        layout.addWidget(self.chart, 1)

        QTimer.singleShot(100, self.refresh)

    def create_card(self, title, value, color):
        card = QFrame()
        card.setObjectName("statsCard")
        card.setProperty("color", color)

        # Layout
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(6)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardTitle")
        title_lbl.setStyleSheet("font-size:20px;color:#28a745;font-weight:bold;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Value
        value_lbl = QLabel(value)
        value_lbl.setObjectName("cardValue")
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)

        card_layout.addWidget(title_lbl)
        card_layout.addWidget(value_lbl)
        card_layout.addStretch()

        # ——— Add drop shadow (real elevation effect) ———
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        card.setGraphicsEffect(shadow)

        card.title_label = title_lbl
        card.value_label = value_lbl
        return card

    def format_currency(self, amount: float) -> str:
        if amount == 0:
            return "R0.00"
        sign = "-" if amount < 0 else ""
        return f"{sign}R{abs(amount):,.2f}"

    def refresh(self):
        try:
            conn = get_conn_raw()
            cur = conn.cursor()

            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='Income'")
            income = cur.fetchone()[0] or 0.0

            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='Expense'")
            expense = cur.fetchone()[0] or 0.0

            balance = income - -(expense)

            self.card_income.value_label.setText(self.format_currency(income))
            self.card_income.value_label.setStyleSheet("font-size:28px;color:#28a745;font-weight:bold;")
            self.card_expense.value_label.setText(self.format_currency(expense))
            self.card_expense.value_label.setStyleSheet("font-size:28px;color:#dc3545;font-weight:bold;")
            self.card_balance.value_label.setText(self.format_currency(balance))
            self.card_balance.value_label.setStyleSheet("font-size:28px;color:#007bff;font-weight:bold;")

            cur.execute("""
                SELECT date,
                       COALESCE(SUM(CASE WHEN type='Income' THEN amount ELSE 0 END), 0) as inc,
                       COALESCE(SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END), 0) as exp
                FROM transactions
                WHERE date IS NOT NULL
                GROUP BY date
                ORDER BY date
                LIMIT 30
            """)
            rows = cur.fetchall()
            conn.close()

            self.chart.clear()
            if not rows:
                self.chart.setTitle("No transactions yet")
                return

            dates, income_data, expense_data = [], [], []
            for r in rows:
                try:
                    dt = time.strptime(r["date"], "%Y-%m-%d")
                    dates.append(time.mktime(dt))
                    income_data.append(r["inc"])
                    expense_data.append(r["exp"])
                except:
                    continue

            if not dates:
                self.chart.setTitle("No valid dates")
                return

            self.chart.plot(dates, income_data,
                            pen=pg.mkPen('#28a745', width=4),
                            name="Income", symbol='o', symbolBrush='#28a745')
            self.chart.plot(dates, expense_data,
                            pen=pg.mkPen('#dc3545', width=4),
                            name="Expense", symbol='t', symbolBrush='#dc3545')
            self.chart.addLegend(offset=(10, 10))

            self.apply_theme()

        except Exception as e:
            print("Dashboard refresh error:", e)
            self.chart.setTitle(f"Error: {e}")

    def apply_theme(self):
        dark = is_dark_mode()

        if dark:
            card_style = """
                QFrame#statsCard {
                    background-color: #2b2b2b;
                    border: 1px solid #3a3a3a;
                    border-radius: 16px;
                }
                QLabel#cardTitle {
                    color: #bbbbbb;
                    font-size: 15px;
                    font-weight: 600;
                }
                QLabel#cardValue {
                    color: %COLOR%;
                    font-size: 28px;
                    font-weight: 700;
                    margin-top: 4px;
                }
            """
        else:
            card_style = """
                QFrame#statsCard {
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 16px;
                }
                QLabel#cardTitle {
                    color: #4b5563;
                    font-size: 15px;
                    font-weight: 600;
                }
                QLabel#cardValue {
                    color: %COLOR%;
                    font-size: 28px;
                    font-weight: 700;
                    margin-top: 4px;
                }
            """

        for card in (self.card_income, self.card_expense, self.card_balance):
            color = card.property("color")
            final_style = card_style.replace("%COLOR%", color)
            card.setStyleSheet(final_style)

        # Chart theme
        bg = '#1e1e1e' if dark else '#ffffff'
        text = '#ffffff' if dark else '#000000'
        grid_alpha = 0.3 if dark else 0.7

        self.chart.setBackground(bg)
        self.chart.getAxis('left').setTextPen(text)
        self.chart.getAxis('bottom').setTextPen(text)
        self.chart.setTitle("Income vs Expenses Over Time", color=text)
        self.chart.showGrid(x=True, y=True, alpha=grid_alpha)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_timer.start(5000)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh_timer.stop()
