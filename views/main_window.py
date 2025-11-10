# views/main_window.py
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NexLedger - Dashboard")
        self.setGeometry(300, 100, 800, 600)
        self.setup_ui()

    def setup_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Welcome to NexLedger!"))
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
