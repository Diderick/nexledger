# pro/reports.py
from PyQt6.QtWidgets import QMessageBox

from shared.db import get_conn


def export_vat201(self, period: str):  # e.g. "2025-11"
    conn = get_conn()
    rows = conn.execute("""
        SELECT vat_type, SUM(vat_amount) as vat, SUM(total_amount) as total
        FROM vat_transactions 
        WHERE tax_period = ?
        GROUP BY vat_type
    """, (period,)).fetchall()

    output = {
        "period": period,
        "output_vat": 0.0,
        "input_vat": 0.0,
        "payable": 0.0
    }
    for r in rows:
        if r['vat_type'] == 'Output':
            output['output_vat'] = r['vat']
        else:
            output['input_vat'] = r['vat']
    output['payable'] = output['output_vat'] - output['input_vat']

    # Export JSON (for eFiling)
    path = f"VAT201_{period}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    QMessageBox.information(self, "VAT201 Ready", f"Exported: {path}")