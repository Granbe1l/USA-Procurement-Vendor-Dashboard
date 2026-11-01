"""Bounded in-memory DuckDB with snapshot invalidation and serialized view updates."""
from pathlib import Path
from threading import RLock

import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / 'sql'
FILES = ('01_vendor_totals.sql', '02_abc_classification.sql', '03_abc_summary.sql',
         '04_concentration_hhi.sql', '06_fy_comparison.sql',
         '06_vendor_rank_changes.sql', '07_vendor_name_overlap.sql')


def sql_text(name):
    if name not in FILES and name != '00_setup_view.sql':
        raise ValueError(f'Unknown SQL file: {name}')
    return (SQL_DIR / name).read_text(encoding='utf-8').strip().rstrip(';')


def _connect():
    connection = duckdb.connect(':memory:', config={'memory_limit': '256MB', 'threads': '2'})
    # No disk spill, auto-installed extensions, or runtime database files.
    connection.execute("SET temp_directory = ''")
    connection.execute('SET autoinstall_known_extensions = false')
    connection.execute('SET autoload_known_extensions = false')
    return connection


def _prepare_views(connection):
    connection.execute('CREATE OR REPLACE TEMP VIEW vendor_totals AS ' + sql_text('01_vendor_totals.sql'))
    connection.execute('CREATE OR REPLACE TEMP VIEW abc_classification AS ' + sql_text('02_abc_classification.sql'))


def query_frame(frame, name):
    """Uncached isolated connection for parity tests and small filtered frames."""
    with _connect() as connection:
        connection.register('transactions', frame)
        _prepare_views(connection)
        return connection.execute(sql_text(name)).df()


def _snapshot_signature(path):
    path = Path(path).resolve()
    info = path.stat()
    return str(path), info.st_mtime_ns, info.st_size


@st.cache_resource(max_entries=2, show_spinner=False)
def _snapshot_connection(path, modified, size):
    connection = _connect()
    statement = sql_text('00_setup_view.sql').replace('{DATA_PATH}', path.replace("'", "''"))
    if not path.endswith('.parquet'):
        statement = statement.replace("read_parquet('", "read_csv('")
        # Only alter the reader expression, not SQL casts or date expressions.
        statement = statement.replace("read_csv('" + path.replace("'", "''") + "')",
                                      "read_csv('" + path.replace("'", "''") + "', all_varchar=true)")
    connection.execute(statement.replace('VIEW transactions AS', 'VIEW snapshot_transactions AS'))
    return connection, RLock()


def _where(filters):
    allowed = {'fiscal_year', 'agency', 'state', 'award_type'}
    conditions = []
    for column, values in filters:
        if column not in allowed:
            raise ValueError('Unsupported filter')
        if values is not None:
            escaped = ["'" + str(value).replace("'", "''") + "'" for value in values]
            conditions.append(column + ' IN (' + ','.join(escaped) + ')' if escaped else 'FALSE')
    return ' AND '.join(conditions) or 'TRUE'


@st.cache_data(max_entries=32, show_spinner=False)
def _run_cached(path, modified, size, name, filters):
    connection, lock = _snapshot_connection(path, modified, size)
    with lock:
        connection.execute('CREATE OR REPLACE TEMP VIEW transactions AS SELECT * FROM snapshot_transactions WHERE ' + _where(filters))
        _prepare_views(connection)
        return connection.execute(sql_text(name)).df()


def run_sql_file(name, *, data_path=None, filters=()):
    """Run a whitelisted query; results cache by snapshot version and active filters."""
    sql_text(name)
    if data_path is None:
        folder = ROOT / 'data' / 'processed'
        data_path = folder / ('transactions.parquet' if (folder / 'transactions.parquet').exists() else 'transactions.csv.gz')
    normalized = tuple((column, None if values is None else tuple(values)) for column, values in filters)
    return _run_cached(*_snapshot_signature(data_path), name, normalized)
