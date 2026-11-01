"""Check actual Streamlit KPI cards against real filtered data and SQL.

Runs only against the bundled count-verified USAspending snapshot.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
from procurement import analyze, load_data
from src.db import run_sql_file

meta = json.loads((ROOT / "data/processed/metadata.json").read_text())
path = ROOT / "data/processed/transactions.parquet"
assert meta["status"] == "complete"
assert meta["source_verification"] == "official_api_download_count_checked"
assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["parquet_sha256"]
frame = load_data(path)
assert len(frame) == meta["row_count"] == 5020

def money(value):
    if value is None:
        return "—"
    sign = "−" if value < 0 else ""
    value = abs(float(value))
    for threshold, suffix in [(1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if value >= threshold:
            return f"{sign}${value / threshold:,.2f}{suffix}"
    return f"{sign}${value:,.2f}"

def check(app, label, filters):
    assert not app.exception, f"{label}: {app.exception}"
    expected = analyze(frame, **filters)
    kpi = expected["kpi"]
    html = "\n".join(str(item.value) for item in app.markdown)
    assert "NET OBLIGATIONS" in html, f"{label}: missing KPI card"
    assert money(kpi["net_obligations"]) in html, f"{label}: incorrect obligation KPI"
    assert f'{kpi["unique_vendors"]:,}' in html, f"{label}: incorrect vendor count"
    a = kpi["category_a_share"]
    assert ("—" if a is None else f"{a:.1%}") in html, f"{label}: incorrect ABC KPI"
    sql_filters = tuple((key, tuple(values) if values is not None else None)
                        for key, values in [
                            ("fiscal_year", filters.get("years")),
                            ("agency", filters.get("agencies")),
                            ("state", filters.get("states")),
                            ("award_type", filters.get("award_types")),
                        ])
    yearly = run_sql_file("06_fy_comparison.sql", data_path=path, filters=sql_filters)
    sql_total = float(yearly.loc[yearly.scope.eq("combined"), "net_obligations"].sum())
    assert abs(sql_total - kpi["net_obligations"]) <= .02, label
    # The dashboard uses this exact filtered population for transaction export.
    filtered = frame
    for field, values in [
        ("fiscal_year", filters.get("years")), ("agency", filters.get("agencies")),
        ("state", filters.get("states")), ("award_type", filters.get("award_types"))
    ]:
        if values:
            filtered = filtered.loc[filtered[field].isin(values)]
    assert len(filtered) == kpi["transactions"]
    assert round(filtered.obligation_cents.sum() / 100, 2) == round(kpi["net_obligations"], 2)
    print(f"PASS {label}: {len(filtered)} official transactions, UI KPI = SQL = filtered export population")

app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
assert len(app.sidebar.multiselect) == 4
check(app, "all", {})

app.sidebar.multiselect[0].set_value([2025]).run()
app.sidebar.multiselect[1].set_value(["National Science Foundation"]).run()
check(app, "NSF FY2025", {"years": [2025], "agencies": ["National Science Foundation"]})

app.sidebar.multiselect[0].set_value([2024]).run()
app.sidebar.multiselect[1].set_value(["Nuclear Regulatory Commission"]).run()
check(app, "NRC FY2024", {"years": [2024], "agencies": ["Nuclear Regulatory Commission"]})

app.sidebar.multiselect[0].set_value([]).run()
app.sidebar.multiselect[1].set_value([]).run()
state = frame.state.dropna().astype(str).value_counts().index[0]
app.sidebar.multiselect[2].set_value([state]).run()
check(app, "state", {"states": [state]})

app.sidebar.multiselect[2].set_value([]).run()
award_type = frame.award_type.dropna().astype(str).value_counts().index[0]
app.sidebar.multiselect[3].set_value([award_type]).run()
check(app, "award type", {"award_types": [award_type]})

app.sidebar.multiselect[3].set_value([]).run()
check(app, "reset", {})
print("Verified real-data KPI, filter, SQL and export-source consistency.")
