"""Independent SQLite analysis of a cleaned, filtered transaction population."""
from pathlib import Path
import sqlite3

import pandas as pd

QUERY = Path(__file__).resolve().parent / 'sql' / 'vendor_concentration.sql'


def compare_concentration(frame):
    """Return agency-year metrics; undefined positive-value measures stay null."""
    columns = ['agency', 'fiscal_year', 'vendor_id', 'obligation_cents']
    with sqlite3.connect(':memory:') as connection:
        frame[columns].to_sql('transactions', connection, index=False)
        return pd.read_sql_query(QUERY.read_text(), connection)
