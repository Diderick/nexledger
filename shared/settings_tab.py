from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QFormLayout
)
from shared.db import get_conn

class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(QLabel("<h2>Application Settings</h2>"))

        form_layout = QFormLayout()

        # VAT Rate
        self.vat_input = QLineEdit()
        self.vat_input.setPlaceholderText("e.g. 15")
        form_layout.addRow("VAT Rate (%)", self.vat_input)

        # UIF Rate
        self.uif_input = QLineEdit()
        self.uif_input.setPlaceholderText("e.g. 1")
        form_layout.addRow("UIF Rate (%)", self.uif_input)

        # Database Settings
        self.db_host = QLineEdit()
        self.db_name = QLineEdit()
        self.db_user = QLineEdit()
        self.db_pass = QLineEdit()
        self.db_pass.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("DB Host", self.db_host)
        form_layout.addRow("DB Name", self.db_name)
        form_layout.addRow("DB User", self.db_user)
        form_layout.addRow("DB Password", self.db_pass)

        layout.addLayout(form_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(save_btn)

        backup_btn = QPushButton("Backup Database")
        backup_btn.clicked.connect(self.backup_db)
        btn_layout.addWidget(backup_btn)

        layout.addLayout(btn_layout)

        layout.addStretch()

    def load_settings(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()

            cur.execute("SELECT key, value FROM settings")
            rows = cur.fetchall()
            conn.close()

            settings_map = {k: v for k, v in rows}

            self.vat_input.setText(settings_map.get("vat_rate", "15"))
            self.uif_input.setText(settings_map.get("uif_rate", "1"))
            self.db_host.setText(settings_map.get("db_host", "localhost"))
            self.db_name.setText(settings_map.get("db_name", "nexledger.db"))
            self.db_user.setText(settings_map.get("db_user", ""))
            self.db_pass.setText(settings_map.get("db_pass", ""))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load settings: {e}")

    def save_settings(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            for key, widget in [
                ("vat_rate", self.vat_input),
                ("uif_rate", self.uif_input),
                ("db_host", self.db_host),
                ("db_name", self.db_name),
                ("db_user", self.db_user),
                ("db_pass", self.db_pass)
            ]:
                cur.execute("""
                    INSERT INTO settings(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """, (key, widget.text()))
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Success", "Settings saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def backup_db(self):
        try:
            from shutil import copyfile
            db_file = self.db_name.text() or "nexledger.db"
            backup_file = db_file.replace(".db", "_backup.db")
            copyfile(db_file, backup_file)
            QMessageBox.information(self, "Backup", f"Database backed up to {backup_file}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Backup failed: {e}")
