# shared/theme.py
# CENTRAL THEME – ALL SCREENS USE THIS – 12 November 2025

import json
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
SETTINGS_FILE = ROOT_DIR / "settings.json"

def is_dark_mode() -> bool:
    """Return True if dark mode is enabled in settings.json, else False (default light)"""
    if not SETTINGS_FILE.exists():
        return False  # DEFAULT = LIGHT
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            return bool(data.get("dark_mode", False))
    except:
        return False

def set_dark_mode(enabled: bool):
    """Save theme preference"""
    data = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except:
            pass
    data["dark_mode"] = bool(enabled)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def toggle_dark_mode():
    """Flip and save"""
    set_dark_mode(not is_dark_mode())

def get_widget_style() -> str:
    """Return full CSS for current theme"""
    if is_dark_mode():
        return """
            * { background: #1e1e1e; color: #ffffff; font-family: "Segoe UI", sans-serif; }
            QLabel { color: #ffffff; font-size: 14px; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox {
                background: #2d2d2d; color: #ffffff; border: 1px solid #555;
                border-radius: 8px; padding: 12px; font-size: 14px;
            }
            QLineEdit:focus, QTextEdit:focus { border: 2px solid #0d6efd; }
            QCheckBox, QRadioButton { color: #ffffff; font-size: 15px; }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px; height: 18px; border-radius: 9px; border: 2px solid #555;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background: #0d6efd; border: 2px solid #0d6efd;
            }
            QPushButton {
                background: #0d6efd; color: white; border: none;
                border-radius: 8px; padding: 12px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background: #0b5ed7; }
            QPushButton:pressed { background: #094c9e; }
            QWizard, QDialog, QMainWindow { background: #1e1e1e; }
            QScrollArea { background: transparent; border: none; }
        """
    else:
        return """
            * { background: #ffffff; color: #000000; font-family: "Segoe UI", sans-serif; }
            QLabel { color: #000000; font-size: 14px; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox {
                background: white; color: #000000; border: 1px solid #ccc;
                border-radius: 8px; padding: 12px; font-size: 14px;
            }
            QLineEdit:focus, QTextEdit:focus { border: 2px solid #007bff; }
            QCheckBox, QRadioButton { color: #000000; font-size: 15px; }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px; height: 18px; border-radius: 9px; border: 2px solid #ccc;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background: #007bff; border: 2px solid #007bff;
            }
            QPushButton {
                background: #007bff; color: white; border: none;
                border-radius: 8px; padding: 12px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background: #0056b3; }
            QWizard, QDialog, QMainWindow { background: #ffffff; }
            QScrollArea { background: transparent; border: none; }
        """