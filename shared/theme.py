# shared/theme.py
# GOLD & EMERALD THEME – FULL SYSTEM UI (COMPLETE)
# Includes:
# - Sidebar styling (light + dark)
# - Menubar & toolbar styling
# - Tabs upgraded
# - Buttons, tables, cards, scrollbars
# - KPI glow panels
# - Inputs with focus gold border
# - Sliders, progress bars, checkboxes
# - Dialogs, Wizards, Main Windows unified

import json
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
SETTINGS_FILE = ROOT_DIR / "settings.json"

def is_dark_mode() -> bool:
    if not SETTINGS_FILE.exists():
        return False
    try:
        with open(SETTINGS_FILE, "r") as f:
            return bool(json.load(f).get("dark_mode", False))
    except:
        return False

def set_dark_mode(enabled: bool):
    data = {}
    if SETTINGS_FILE.exists():
        try:
            data = json.load(open(SETTINGS_FILE))
        except:
            pass
    data["dark_mode"] = bool(enabled)
    json.dump(data, open(SETTINGS_FILE, "w"), indent=2)

def toggle_dark_mode():
    set_dark_mode(not is_dark_mode())

# ------------------------------------------------------
# Colors
# ------------------------------------------------------
EMERALD = "#006847"
EMERALD_LIGHT = "#008F55"
EMERALD_DARK = "#003F2A"
GOLD = "#C9B037"
GOLD_LIGHT = "#F1D06E"
DARK_BG = "#0A0F0A"
LIGHT_BG = "#FFFFFF"
SHADOW = "rgba(0,0,0,0.35)"
SHADOW_LIGHT = "rgba(0,0,0,0.15)"

# ------------------------------------------------------
# CSS Generator – FULL UI COVERAGE
# ------------------------------------------------------

def get_widget_style() -> str:
    if is_dark_mode():
        return f"""
            * {{ background: {DARK_BG}; color: #F6F6F6; font-family: 'Segoe UI'; }}

            /* -------- MENUBAR -------- */
            QMenuBar {{ background: #0F1510; color:white; padding:6px; }}
            QMenuBar::item:selected {{ background:{EMERALD_LIGHT}; }}
            QMenu {{ background:#0f0f0f; border:1px solid {EMERALD_DARK}; }}
            QMenu::item:selected {{ background:{GOLD}; color:black; }}

            /* -------- SIDEBAR -------- */
            #sidebar {{
                background:#0F1510;
                border-right:2px solid {EMERALD_DARK};
                padding:10px;
            }}
            #sidebar QPushButton {{
                background:transparent; border:none; color:white;
                text-align:left; padding:10px 14px; border-radius:8px; font-size:14px;
            }}
            #sidebar QPushButton:hover {{ background:rgba(0,104,71,0.35); }}
            #sidebar QPushButton:pressed {{ background:rgba(201,176,55,0.35); }}

            /* -------- BUTTONS -------- */
            QPushButton {{
                background:{EMERALD}; color:white; border-radius:10px;
                border:1px solid {GOLD}; font-weight:bold; padding:10px 20px;
                box-shadow:0px 2px 6px {SHADOW};
            }}
            QPushButton:hover {{ background:{EMERALD_LIGHT}; box-shadow:0 0 10px {EMERALD_LIGHT}; }}
            QPushButton:pressed {{ background:{EMERALD_DARK}; }}

            /* -------- INPUTS -------- */
            QLineEdit, QTextEdit, QSpinBox, QComboBox {{
                background:#1A1F1A; color:white;
                border-radius:10px; padding:10px; border:1px solid {EMERALD};
                box-shadow:inset 0 0 6px {SHADOW};
            }}
            QLineEdit:focus {{ border:2px solid {GOLD}; }}

            /* -------- TABLES -------- */
            QTableWidget {{ background:#141414; selection-background-color:{EMERALD}; }}
            QHeaderView::section {{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {EMERALD}, stop:1 {EMERALD_LIGHT});
                color:white; padding:6px; border:none; font-weight:bold;
            }}

            /* -------- KPI Cards -------- */
            QFrame#kpi {{
                border-radius:12px; border:1px solid {GOLD};
                background:rgba(0,104,71,0.25);
                box-shadow:0 0 12px {EMERALD_LIGHT};
                padding:10px;
            }}

            /* -------- TABS -------- */
            QTabBar::tab {{
                height:36px; padding:8px 20px;
                background:#111; color:white;
                border-top:3px solid transparent;
            }}
            QTabBar::tab:hover {{ border-top:3px solid {GOLD}; background:#1a1a1a; }}
            QTabBar::tab:selected {{ background:{EMERALD}; border-top:3px solid {GOLD}; }}

            /* -------- SCROLLBAR -------- */
            QScrollBar:vertical {{ width:14px; background:#111; }}
            QScrollBar::handle:vertical {{ background:{EMERALD}; border-radius:6px; }}

            /* -------- CHECKBOX -------- */
            QCheckBox::indicator {{ border:2px solid {GOLD}; width:20px; height:20px; }}
            QCheckBox::indicator:checked {{ background:{EMERALD}; }}

            /* -------- PROGRESSBAR -------- */
            QProgressBar {{ border-radius:8px; text-align:center; }}
            QProgressBar::chunk {{ background:{GOLD}; border-radius:8px; }}

            /* -------- TOOLTIP -------- */
            QToolTip {{ background:{EMERALD}; color:white; border:1px solid {GOLD}; padding:6px; }}
        """

    # ---------------- LIGHT MODE ----------------
    return f"""
        * {{ background:{LIGHT_BG}; color:black; font-family:'Segoe UI'; }}

        /* -------- MENUBAR -------- */
        QMenuBar {{ background:#f8fff9; color:#003F2A; padding:6px; }}
        QMenuBar::item:selected {{ background:{GOLD}; color:black; }}
        QMenu {{ background:white; border:1px solid {GOLD}; }}
        QMenu::item:selected {{ background:{EMERALD_LIGHT}; color:white; }}

        /* -------- SIDEBAR -------- */
        #sidebar {{ background:#f8fff9; border-right:2px solid {GOLD}; padding:10px; }}
        #sidebar QPushButton {{
            background:transparent; border:none; color:#003F2A;
            text-align:left; padding:10px 14px; border-radius:8px;
        }}
        #sidebar QPushButton:hover {{ background:rgba(0,104,71,0.12); }}
        #sidebar QPushButton:pressed {{ background:rgba(201,176,55,0.25); }}

        /* -------- BUTTONS -------- */
        QPushButton {{ background:{EMERALD}; color:white; border-radius:10px;
                       border:1px solid {GOLD}; padding:10px 20px;
                       font-weight:bold; box-shadow:0px 2px 4px {SHADOW_LIGHT}; }}
        QPushButton:hover {{ background:{EMERALD_LIGHT}; }}

        /* -------- INPUTS -------- */
        QLineEdit, QTextEdit, QSpinBox, QComboBox {{
            background:white; border-radius:10px;
            border:1px solid {EMERALD}; padding:10px;
        }}
        QLineEdit:focus {{ border:2px solid {GOLD}; }}

        /* -------- TABLES -------- */
        QTableWidget {{ background:#FAFAFA; selection-background-color:{GOLD}; }}
        QHeaderView::section {{
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {EMERALD}, stop:1 {EMERALD_LIGHT});
            color:white; padding:6px; border:none;
        }}

        /* -------- KPI Cards -------- */
        QFrame#kpi {{
            border-radius:12px; border:1px solid {GOLD};
            background:rgba(0,104,71,0.08);
            box-shadow:0 0 10px {GOLD_LIGHT};
        }}

        /* -------- TABS -------- */
        QTabBar::tab {{
            height:36px; padding:8px 20px;
            background:white; color:#2d2d2d;
            border-top:3px solid transparent;
        }}
        QTabBar::tab:hover {{ border-top:3px solid {GOLD}; background:#e7f9f0; }}
        QTabBar::tab:hover:selected {{ border-top:3px solid {GOLD}; background:#e7f9f0; color: black}}

        QTabBar::tab:selected {{ background:{EMERALD}; color:white; border-top:3px solid {GOLD}; }}

        /* -------- SCROLLBAR -------- */
        QScrollBar:vertical {{ width:14px; background:#eee; }}
        QScrollBar::handle:vertical {{ background:{EMERALD}
"""