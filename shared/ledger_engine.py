# shared/ledger_engine.py
"""
NexLedger Ledger Engine
-----------------------
Double-entry posting system for:
 - Invoices
 - Bills
 - Cashbook transactions
 - Journals
 - Automatic postings to ledger accounts
 - Trial Balance, P&L, Balance Sheet
"""

from shared.db import db_connection, log_audit


# -----------------------------
# Posting Engine
# -----------------------------

def post_journal_entry(date, reference, memo, lines):
    """
    Post a general journal entry.

    lines = [
        {"account_id": X, "debit": 100},
        {"account_id": Y, "credit": 100},
        ...
    ]
    """

    debit_total = sum(l.get("debit", 0) or 0 for l in lines)
    credit_total = sum(l.get("credit", 0) or 0 for l in lines)

    if round(debit_total, 2) != round(credit_total, 2):
        raise ValueError("Journal entry not balanced (debits != credits).")

    with db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO journal_entries (date, reference, memo)
            VALUES (?, ?, ?)
        """, (date, reference, memo))

        journal_id = cur.lastrowid

        for line in lines:
            cur.execute("""
                INSERT INTO journal_lines (journal_id, account_id, debit, credit)
                VALUES (?, ?, ?, ?)
            """, (
                journal_id,
                line["account_id"],
                line.get("debit", 0) or 0,
                line.get("credit", 0) or 0
            ))

        conn.commit()

    log_audit(f"Posted journal entry #{journal_id}")
    return journal_id


# -----------------------------
# Postings from other modules
# -----------------------------

def post_invoice(invoice_id):
    """
    Creates GL postings for an invoice.
    Debit Accounts Receivable
    Credit Sales + Credit VAT Output
    """
    with db_connection() as conn:
        cur = conn.cursor()

        invoice = cur.execute("""
            SELECT customer_id, date, reference, subtotal, vat, total
            FROM invoices
            WHERE id = ?
        """, (invoice_id,)).fetchone()

        if not invoice:
            raise ValueError("Invoice not found")

        ar = _get_account_id(conn, "1200")     # Accounts Receivable
        sales = _get_account_id(conn, "4000")  # Sales
        vat_output = _get_account_id(conn, "2100")  # VAT Output

        lines = [
            {"account_id": ar, "debit": invoice["total"]},
            {"account_id": sales, "credit": invoice["subtotal"]},
        ]

        if invoice["vat"] > 0:
            lines.append({"account_id": vat_output, "credit": invoice["vat"]})

        return post_journal_entry(
            invoice["date"],
            f"INV-{invoice_id}",
            invoice["reference"],
            lines
        )


def post_bill(bill_id):
    """
    Creates GL postings for a supplier bill.
    Debit Purchases/Expenses
    Debit VAT Input
    Credit Accounts Payable
    """
    with db_connection() as conn:
        cur = conn.cursor()

        bill = cur.execute("""
            SELECT vendor_id, date, reference, subtotal, vat, total
            FROM bills
            WHERE id = ?
        """, (bill_id,)).fetchone()

        if not bill:
            raise ValueError("Bill not found")

        ap = _get_account_id(conn, "2000")       # Accounts Payable
        purchases = _get_account_id(conn, "5000")
        vat_input = _get_account_id(conn, "1400")

        lines = [
            {"account_id": purchases, "debit": bill["subtotal"]},
        ]

        if bill["vat"] > 0:
            lines.append({"account_id": vat_input, "debit": bill["vat"]})

        lines.append({"account_id": ap, "credit": bill["total"]})

        return post_journal_entry(
            bill["date"],
            f"BILL-{bill_id}",
            bill["reference"],
            lines
        )


def post_cashbook_entry(entry_id):
    """
    Cashbook entry → Bank account and a ledger account.
    Debit or Credit depending on debit/credit amounts.
    """
    with db_connection() as conn:
        cur = conn.cursor()

        entry = cur.execute("""
            SELECT date, narration, reference, debit, credit, account
            FROM cash_book WHERE id = ?
        """, (entry_id,)).fetchone()

        if not entry:
            raise ValueError("Cashbook entry not found")

        bank = _get_account_id(conn, "1000")  # Bank

        # Lookup account from entry.account (text)
        ledger_account = _find_account_by_name(conn, entry["account"])
        if not ledger_account:
            raise ValueError(f"Ledger account '{entry['account']}' not found")

        debit = entry["debit"] or 0
        credit = entry["credit"] or 0

        if debit > 0:
            lines = [
                {"account_id": ledger_account, "debit": debit},
                {"account_id": bank, "credit": debit},
            ]
        else:
            lines = [
                {"account_id": bank, "debit": credit},
                {"account_id": ledger_account, "credit": credit},
            ]

        return post_journal_entry(
            entry["date"],
            f"CASH-{entry_id}",
            entry["reference"] or entry["narration"],
            lines
        )


# -----------------------------
# Ledger Queries
# -----------------------------

def get_ledger(account_id, date_from=None, date_to=None):
    """Return all ledger lines + running balance."""
    with db_connection() as conn:
        cur = conn.cursor()

        sql = """
            SELECT jl.id, je.date, je.reference, je.memo,
                   jl.debit, jl.credit
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_id
            WHERE jl.account_id = ?
        """

        params = [account_id]

        if date_from:
            sql += " AND je.date >= ?"
            params.append(date_from)

        if date_to:
            sql += " AND je.date <= ?"
            params.append(date_to)

        sql += " ORDER BY je.date, jl.id"

        rows = cur.execute(sql, params).fetchall()

        balance = 0
        ledger = []
        for r in rows:
            balance += (r["debit"] or 0) - (r["credit"] or 0)
            ledger.append({
                "id": r["id"],
                "date": r["date"],
                "reference": r["reference"],
                "memo": r["memo"],
                "debit": r["debit"],
                "credit": r["credit"],
                "balance": balance
            })

        return ledger


def trial_balance():
    """Return a full trial balance grouped by account type."""
    with db_connection() as conn:
        cur = conn.cursor()

        accounts = cur.execute("SELECT id, code, name, type FROM accounts ORDER BY code").fetchall()

        tb = []
        for acc in accounts:
            total = cur.execute("""
                SELECT 
                    IFNULL(SUM(debit), 0) - IFNULL(SUM(credit), 0) AS bal
                FROM journal_lines WHERE account_id = ?
            """, (acc["id"],)).fetchone()["bal"]

            tb.append({
                "account_code": acc["code"],
                "account_name": acc["name"],
                "type": acc["type"],
                "balance": total
            })

        return tb


# -----------------------------
# Financial Statements
# -----------------------------

def profit_and_loss():
    """Return P&L grouped as Income - COGS - Expenses."""

    tb = trial_balance()

    income = []
    cogs = []
    expenses = []

    for line in tb:
        if line["type"] == "Income":
            income.append(line)
        elif line["account_code"].startswith("5"):  # cost of sales
            cogs.append(line)
        elif line["type"] == "Expense":
            expenses.append(line)

    total_income = sum(l["balance"] for l in income)
    total_cogs = sum(l["balance"] for l in cogs)
    total_expenses = sum(l["balance"] for l in expenses)

    gross_profit = total_income - total_cogs
    net_profit = gross_profit - total_expenses

    return {
        "income": income,
        "cogs": cogs,
        "expenses": expenses,
        "gross_profit": gross_profit,
        "net_profit": net_profit
    }


def balance_sheet():
    """Return Assets = Liabilities + Equity balance sheet."""
    tb = trial_balance()

    assets = []
    liabilities = []
    equity = []

    for line in tb:
        if line["type"] == "Asset":
            assets.append(line)
        elif line["type"] == "Liability":
            liabilities.append(line)
        elif line["type"] == "Equity":
            equity.append(line)

    total_assets = sum(l["balance"] for l in assets)
    total_liabilities = sum(l["balance"] for l in liabilities)
    total_equity = sum(l["balance"] for l in equity)

    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity
    }


# -----------------------------
# Helpers
# -----------------------------

def _get_account_id(conn, code):
    row = conn.execute("SELECT id FROM accounts WHERE code = ?", (code,)).fetchone()
    if not row:
        raise ValueError(f"Account {code} not found")
    return row["id"]


def _find_account_by_name(conn, name):
    row = conn.execute("SELECT id FROM accounts WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    return row["id"] if row else None
