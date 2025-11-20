# bank_import_engine.py
# Extracted from combined file

import csv
import json
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple

DB_PATH = os.environ.get('LEDGER_DB', 'ledger.db')


def get_conn(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str = DB_PATH):
    conn = get_conn(path)
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS raw_bank_feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT,
        imported_at TEXT,
        bank_date TEXT,
        amount NUMERIC,
        currency TEXT,
        payee TEXT,
        reference TEXT,
        metadata TEXT,
        posted INTEGER DEFAULT 0,
        matched_transaction_id INTEGER DEFAULT NULL
    )''')

    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def decimal_round(v) -> Decimal:
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


@dataclass
class RawFeedRow:
    source_file: str
    bank_date: str
    amount: Decimal
    currency: str
    payee: str
    reference: Optional[str]
    metadata: Optional[Dict[str, Any]]


class BankImportEngine:
    def __init__(self, db_path: str = DB_PATH):
        init_db(db_path)
        self.db_path = db_path

    def parse_csv(self, filepath: str, mapping: Dict[str, int] = None, date_format: str = None) -> List[RawFeedRow]:
        rows = []
        with open(filepath, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            headers = next(reader)

            if mapping is None:
                mapping = {}
                hdrs = [h.strip().lower() for h in headers]
                for k in ['date', 'amount', 'payee', 'currency', 'reference']:
                    for i, h in enumerate(hdrs):
                        if k in h:
                            mapping[k] = i
                            break

            for r in reader:
                try:
                    raw_date = r[mapping['date']].strip()

                    if date_format:
                        bank_date = datetime.strptime(raw_date, date_format).date().isoformat()

                        parsed = None
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y']:
                            try:
                                parsed = datetime.strptime(raw_date, fmt)
                                break
                            except:
                                continue
                        if parsed is None:
                            parsed = datetime.fromisoformat(raw_date)
                        bank_date = parsed.date().isoformat()

                    amount = decimal_round(Decimal(r[mapping['amount']].replace(',', '').strip()))
                    payee = r[mapping['payee']] if 'payee' in mapping else ''
                    currency = r[mapping['currency']] if 'currency' in mapping and r[
                        mapping['currency']].strip() else 'ZAR'
                    reference = r[mapping['reference']] if 'reference' in mapping else None

                    rows.append(RawFeedRow(
                        source_file=os.path.basename(filepath),
                        bank_date=bank_date,
                        amount=amount,
                        currency=currency,
                        payee=payee,
                        reference=reference,
                        metadata=None
                    ))
                except Exception as e:
                    print(f"Skipping row due to parse error: {e}")
                    continue
        return rows

    def preview_rows(self, rows: List[RawFeedRow]):
        return [asdict(r) for r in rows]

    def commit_rows(self, rows: List[RawFeedRow]) -> int:
        conn = get_conn(self.db_path)
        cur = conn.cursor()
        count = 0
        for r in rows:
            cur.execute('''INSERT INTO raw_bank_feeds
                (source_file, imported_at, bank_date, amount, currency, payee, reference, metadata, posted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ''', (r.source_file, now_iso(), r.bank_date, float(r.amount), r.currency, r.payee, r.reference,
                  json.dumps(r.metadata or {})))
            count += 1
        conn.commit()
        conn.close()
        return count

    def import_csv_to_raw(self, filepath: str, mapping=None, date_format=None):
        rows = self.parse_csv(filepath, mapping, date_format)
        preview = self.preview_rows(rows)
        count = self.commit_rows(rows)
        return count, preview

    def list_unposted_raw(self, limit=500):
        conn = get_conn(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT * FROM raw_bank_feeds WHERE posted = 0 ORDER BY bank_date LIMIT ?', (limit,))
        data = cur.fetchall()
        conn.close()
        return data
