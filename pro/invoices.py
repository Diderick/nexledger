def calculate_vat(self, subtotal):
    if not is_vat_registered():
        return 0.0
    return round(subtotal * 0.15, 2)

def generate_invoice_pdf(self):
    # ... existing
    vat = self.calculate_vat(subtotal)
    total = subtotal + vat

    # Add to PDF
    self.draw_text(f"VAT (15%): R{vat:,.2f}")
    self.draw_text(f"Total: R{total:,.2f}", bold=True)

    # Log to VAT ledger
    self.log_vat_transaction('Output', vat, total, self.invoice_date[:7])