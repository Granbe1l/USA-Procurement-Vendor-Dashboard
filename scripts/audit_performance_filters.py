"""Audit performance and filter/SQL consistency on the bundled verified snapshot.

No fixture or generated observations are used in this script.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import time

from streamlit.testing.v1 import AppTest
from procurement import analyze, load_data
from src.db import run_sql_file

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / "data" / "processed"
meta = json.loads((directory / "metadata.json").read_text())
quality = json.loads((directory / "quality.json").read_text())
assert meta["status"] == "complete"
assert meta["source_verification"] == "official_api_download_count_checked"
path = directory / "transactions.parquet"
assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["parquet_sha256"]

start = time.perf_counter()
frame = load_data(path)
load_seconds = time.perf_counter() - start
assert len(frame) == meta["row_count"] == quality["retained_rows"]
assert not frame.empty
assert set(frame.fiscal_year.unique()) == {2024, 2025}

scenarios = [
    ("all", {}),
    ("NSF FY2024", {"agency": ["National Science Foundation"], "fiscal_year": [2024]}),
    ("NRC FY2025", {"agency": ["Nuclear Regulatory Commission"], "fiscal_year": [2025]}),
]
state = frame.state.dropna().astype(str).value_counts().index[0]
award_type = frame.award_type.dropna().astype(str).value_counts().index[0]
scenarios.extend([
    ("recipient state", {"state": [state]}),
    ("award type", {"award_type": [award_type]}),
    ("combined filters", {"agency": ["National Science Foundation"], "fiscal_year": [2025], "state": [state]}),
])
results = []
for label, filters in scenarios:
    subset = frame
    for column, values in filters.items():
        subset = subset.loc[subset[column].isin(values)]
    start = time.perf_counter()
    expected = analyze(subset)
    pandas_seconds = time.perf_counter() - start
    start = time.perf_counter()
    sql = run_sql_file("06_fy_comparison.sql", data_path=path, filters=tuple(
        (column, tuple(filters[column]) if column in filters else None)
        for column in ["fiscal_year", "agency", "state", "award_type"]
    ))
    sql_seconds = time.perf_counter() - start
    sql_total = float(sql.loc[sql.scope.eq("combined"), "net_obligations"].sum()) if len(sql) else 0.0
    pandas_total = float(expected["kpi"]["net_obligations"])
    assert abs(sql_total - pandas_total) <= .02, (label, sql_total, pandas_total)
    assert len(subset) == expected["kpi"]["transactions"]
    results.append({"scenario": label, "rows": len(subset), "pandas_seconds": round(pandas_seconds, 3),
                    "sql_seconds": round(sql_seconds, 3), "signed_obligations": round(sql_total, 2)})

app_start = time.perf_counter()
app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
initial_render_seconds = time.perf_counter() - app_start
assert not app.exception, str(app.exception)
assert len(app.sidebar.multiselect) == 4, "Expected FY, agency, state, award type controls"
assert len(app.sidebar.multiselect[0].options) == 2
app.sidebar.multiselect[0].set_value([2024]).run()
assert not app.exception, str(app.exception)
app.sidebar.multiselect[1].set_value(["National Science Foundation"]).run()
assert not app.exception, str(app.exception)
app.sidebar.multiselect[0].set_value([]).run()
app.sidebar.multiselect[1].set_value([]).run()
assert not app.exception, str(app.exception)
for page in ["ABC Classification", "Vendor Analysis", "Fiscal-Year Comparison", "Concentration & SQL"]:
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, (page, str(app.exception))
max_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
report = {
    "source": meta["source"], "retrieval_finished_at": meta["retrieval_finished_at"],
    "snapshot_rows": len(frame), "load_seconds": round(load_seconds, 3),
    "initial_apptest_seconds": round(initial_render_seconds, 3),
    "max_process_rss_mb_linux": round(max_rss_mb, 1),
    "scenarios": results,
    "limitations": [
        "CI AppTest startup is not a Streamlit Community Cloud cold-start measurement.",
        "Linux max RSS covers this audit process, including pandas, SQL and AppTest.",
        "Filter scenarios compare SQL and pandas signed totals, not every visible chart pixel.",
    ],
}
output = ROOT / "artifacts" / "performance-filter-audit.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
