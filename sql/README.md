# SQL query order

These files run in DuckDB 1.4.3. All amounts are signed integer cents until presentation. The pandas implementation in `procurement.py` remains the reference.

For standalone execution, open an in-memory DuckDB connection, replace `{DATA_PATH}` in `00_setup_view.sql` with the escaped path to the prepared Parquet snapshot, and execute it. Register the first two dependencies without their trailing semicolons:

```python
from pathlib import Path
import duckdb

root = Path.cwd()  # run from the repository root
connection = duckdb.connect(':memory:')
setup = (root / 'sql/00_setup_view.sql').read_text()
path = str((root / 'data/processed/transactions.parquet').resolve()).replace("'", "''")
connection.execute(setup.replace('{DATA_PATH}', path))
for name, view in [('01_vendor_totals.sql', 'vendor_totals'),
                   ('02_abc_classification.sql', 'abc_classification')]:
    query = (root / 'sql' / name).read_text().strip().rstrip(';')
    connection.execute(f'CREATE TEMP VIEW {view} AS ' + query)
print(connection.execute((root / 'sql/04_concentration_hhi.sql').read_text()).df())
connection.close()
```

Alternatively, `src.db.run_sql_file(name)` manages setup, dependencies, filtering, bounded caches, and CSV.gz compatibility. It uses in-memory connections only; no `.db` files or disk spill are created. Relative project paths resolve from the module location. Cache keys include the snapshot path, mtime, size, and active filters; a lock serializes shared view updates across sessions.

- `01`: signed recipient totals per agency and FY.
- `02`: complete ABC vendor rows, both `scope='agency'` and `scope='combined'`; zero/negative nets remain Unclassified.
- `03`: ABC class counts and shares. Count shares include nonpositive-net recipients; value shares use the positive-net denominator.
- `04`: agency-year positive-net HHI, top-1/top-10 shares, Category A counts and value shares; signed totals/missing-ID rows remain separate.
- `06_fy_comparison`: signed annual totals, absolute/relative changes, and new/dropped identified recipients. First observed FY has no comparison. A zero previous total gives a null percentage.
- `06_vendor_rank_changes`: current/previous rank for recipients in either year's top 10, ordered by signed net and UEI. A missing rank means absence.
- `07`: latest names normalized for whitespace and case, shared by multiple UEIs. This is an approximation, not corporate-parent consolidation.

`05_competition.sql` is intentionally absent: the current cleaned schema has no competition field. Raw official fields have not been inspected because no source snapshot is available. No competition labels are inferred.

`vendor_concentration.sql` is the preserved earlier SQLite case study. Its results are checked against DuckDB and pandas; it remains an independent compatibility reference.
