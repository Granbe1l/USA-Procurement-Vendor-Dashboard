"""Procurement dashboard with one-time official snapshot initialization."""
from __future__ import annotations

import html
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from procurement import analyze, load_data
from src.db import run_sql_file, sql_text
from src.presentation import display_frame, vendor_labels
from src.insights import build_findings
from snapshot_bootstrap import ensure_snapshot

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PROCUREMENT_DATA_DIR", ROOT / "data" / "processed"))
DATA_PATH = DATA_DIR / ("transactions.parquet" if (DATA_DIR / "transactions.parquet").is_file()
                       else "transactions.csv.gz")
NAVIGATION = ["Overview", "ABC Classification", "Vendor Analysis", "Fiscal-Year Comparison", "Concentration & SQL"]
COLORS = {"A": "#D5A84B", "B": "#4F91E8", "C": "#49BDB3", "Unclassified": "#B793D9"}
BLUE, GOLD, MUTED = "#4F91E8", "#D5A84B", "#9BABBE"

st.set_page_config(page_title="NSF & NRC | Vendor Concentration", layout="wide")
st.markdown("""<style>
.block-container {max-width: 1600px; padding: 4rem 2.1rem 3rem;}
[data-testid="stSidebar"] {background-color: #101B2D; border-right: 1px solid #293A51;}
[data-testid="stSidebar"] label[data-baseweb="radio"] {padding: .35rem .55rem; border-radius: 8px;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {background: #1E3450;}
[data-testid="stSidebar"] label[data-baseweb="radio"]:focus-within {outline: 1px solid #4F91E8; outline-offset: 2px;}
[data-testid="stAlert"] p {color: #F3F6FC;}
h1, h2, h3, p, label {font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;}
[data-testid="stMain"] h1 {font-size: 2rem; font-weight: 680; letter-spacing: -.035em; overflow-wrap: anywhere;}
[data-testid="stMain"] h2 {font-size: 1.32rem;} [data-testid="stMain"] h3 {font-size: 1.05rem;}
.brand {font-size: .93rem; font-weight: 750; letter-spacing: .12em; color: #F3F6FC; margin: .3rem 0 0;}
.brand-sub {font-size: .61rem; letter-spacing: .16em; color: #9BABBE; margin: .2rem 0 1.8rem;}
.subtitle {color: #9BABBE; margin-top: -.5rem; margin-bottom: 1.1rem; font-size: .95rem;}
.kpi-card {background: #142239; border: 1px solid #293A51; border-radius: 12px; padding: 1rem 1.05rem; min-height: 145px; margin-bottom: .8rem;}
.kpi-label {color: #9BABBE; font-size: .72rem; letter-spacing: .025em; font-weight: 600; margin-bottom: .65rem;}
.kpi-value {font-size: 1.9rem; font-weight: 700; letter-spacing: -.035em; line-height: 1.15; color: #F3F6FC;}
.kpi-value.gold {color: #D5A84B;}
.kpi-context {font-size: .8rem; line-height: 1.5; color: #9BABBE; margin-top: .7rem;}
.kpi-glyph {float: right; color: #4F91E8; font-size: .78rem;}
.chart-title {font-size: .92rem; font-weight: 650; color: #F3F6FC; margin-bottom: .15rem;}
.chart-description {font-size: .82rem; color: #B9C8DA; line-height: 1.5; margin-bottom: .3rem;}
.empty-chart {min-height: 215px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; color: #9BABBE; font-size: .79rem; padding: 1rem;}
.empty-chart span {font-size: .68rem; color: #73859C; margin-top: .5rem; max-width: 260px;}
.finding {border-left: 2px solid #D5A84B; padding: .1rem 0 .1rem .8rem; margin: .5rem 0 1rem; color: #F3F6FC; font-size: .86rem;}
.finding small {display: block; color: #9BABBE; font-size: .85rem; line-height: 1.6; margin-top: .3rem;}
.footer {font-size: .67rem; color: #73859C; border-top: 1px solid #293A51; margin-top: 1.5rem; padding-top: 1rem;}
.mobile-data-view {display:none;}
.mobile-record {border:1px solid #293A51; border-radius:12px; padding:.9rem 1rem; background:#142239; margin:.55rem 0;}
.mobile-record-title {font-size:.9rem; font-weight:700; color:#F3F6FC; overflow-wrap:anywhere; margin-bottom:.55rem;}
.mobile-record-field {display:grid; grid-template-columns:minmax(0, 42%) minmax(0, 58%); gap:.6rem; padding:.4rem 0; border-top:1px solid #293A51; font-size:.8rem;}
.mobile-record-label {color:#AFC0D5; overflow-wrap:anywhere;}
.mobile-record-value {color:#F3F6FC; text-align:right; overflow-wrap:anywhere; font-variant-numeric:tabular-nums;}
.mobile-more {border:1px solid #293A51; border-radius:10px; padding:.7rem; margin:.5rem 0; color:#D5A84B;}
.mobile-record-count {color:#AFC0D5; font-size:.78rem; margin:.5rem 0;}
@media(max-width: 700px) {
.block-container {padding: 3.6rem 1rem 2rem;}
[data-testid="stMain"] h1 {font-size: 1.65rem;}
.kpi-card {min-height: 125px;} .kpi-value {font-size: 1.7rem;}
.mobile-data-view {display:block;}
[class*="st-key-desktop_table_"] {display:none;}
}
</style>""", unsafe_allow_html=True)


def money(value: float | None, *, compact: bool = True) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "−" if value < 0 else ""
    value = abs(float(value))
    if compact:
        for threshold, suffix in [(1e9, "B"), (1e6, "M"), (1e3, "K")]:
            if value >= threshold:
                return f"{sign}${value / threshold:,.2f}{suffix}"
    return f"{sign}${value:,.2f}"


def count(value: int | None) -> str:
    return "—" if value is None else f"{int(value):,}"


def percent(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:.1%}"


def chart_style(fig: go.Figure, height: int = 285) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, Segoe UI, sans-serif", "color": "#9BABBE", "size": 10},
        height=height, margin={"l": 0, "r": 0, "t": 10, "b": 0},
        legend={"orientation": "h", "y": 1.12, "font": {"size": 10}},
        hoverlabel={"bgcolor": "#1E3450", "font_color": "#F3F6FC"},
    )
    fig.update_xaxes(gridcolor="#23344B", zerolinecolor="#354459", title_font_size=10)
    fig.update_yaxes(gridcolor="#23344B", zerolinecolor="#354459", title_font_size=10)
    return fig


def chart_heading(title: str, description: str) -> None:
    st.markdown(f'<div class="chart-title">{html.escape(title)}</div>'
                f'<div class="chart-description">{html.escape(description)}</div>', unsafe_allow_html=True)


def empty_chart(message: str = "No verified data available", detail: str = "Load a local source snapshot to view this analysis.") -> None:
    st.markdown(f'<div class="empty-chart">{html.escape(message)}'
                f'<span>{html.escape(detail)}</span></div>', unsafe_allow_html=True)


def plot(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


@st.cache_data(max_entries=2, show_spinner=False)
def read_snapshot(path: str, modified: int) -> pd.DataFrame:
    return load_data(path)


@st.cache_data(max_entries=8, show_spinner=False)
def calculate(data: pd.DataFrame, years, agencies, states, award_types) -> dict:
    return analyze(data, years=years, agencies=agencies, states=states, award_types=award_types)


@st.cache_resource(show_spinner="Loading official USAspending snapshot. First deployment can take a few minutes.")
def initialize_snapshot(path: str) -> dict:
    try:
        return ensure_snapshot(Path(path))
    except Exception:
        # Cache a safe error outcome too: changing pages must not resubmit jobs.
        return {"status": "error", "fetched": False,
                "error": "Official source initialization could not complete. Please retry the official download."}


def read_json(name: str) -> dict:
    content = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"{name} must contain a JSON object.")
    return content


# The shared process cache prevents repeated downloads across pages and sessions.
# A user retry explicitly clears this resource; analytics caches remain intact.
request_key = f"snapshot_load_requested:{DATA_DIR}"
status_key = f"snapshot_load_status:{DATA_DIR}"
auto_fetch = os.environ.get("PROCUREMENT_AUTO_FETCH", "0") != "0"
requested_load = st.session_state.pop(request_key, False)
bootstrap_status = st.session_state.get(status_key)
bundle_missing = (not DATA_PATH.is_file() or any(not (DATA_DIR / name).is_file()
                                              for name in ("metadata.json", "quality.json")))
if requested_load or (bundle_missing and auto_fetch):
    bootstrap_status = initialize_snapshot(str(DATA_DIR))
    st.session_state[status_key] = bootstrap_status

metadata, quality = {}, {}
frame, load_error = pd.DataFrame(), None
if DATA_PATH.exists():
    try:
        missing_companions = [name for name in ("metadata.json", "quality.json")
                              if not (DATA_DIR / name).is_file()]
        if missing_companions:
            raise ValueError("The local snapshot is incomplete: missing " + ", ".join(missing_companions) +
                             ". Restore the complete prepared snapshot before interpreting its values.")
        metadata, quality = read_json("metadata.json"), read_json("quality.json")
        checksum_key = "parquet_sha256" if DATA_PATH.suffix == ".parquet" else "processed_sha256"
        if metadata.get(checksum_key):
            with DATA_PATH.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != metadata[checksum_key]:
                raise ValueError("The prepared snapshot checksum does not match its metadata.")
        if metadata.get("status", "complete") != "complete":
            raise ValueError("The snapshot metadata does not describe a completed capture.")
        frame = read_snapshot(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)
        if quality.get("retained_rows") is not None and int(quality["retained_rows"]) != len(frame):
            raise ValueError("The snapshot row count does not match its cleaning audit.")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        load_error = str(exc)

with st.sidebar:
    st.markdown('<div class="brand">Dashboard</div>'
                '<div class="brand-sub">NSF &amp; NRC · VENDOR CONCENTRATION</div>', unsafe_allow_html=True)
    page = st.radio("Navigation", NAVIGATION, label_visibility="collapsed")
    st.divider()
    st.markdown("**Filter snapshot**")
    if not frame.empty:
        year_options = sorted(frame.fiscal_year.dropna().astype(int).unique().tolist())
        selected_years = st.multiselect("Fiscal year", year_options, placeholder="All fiscal years")
        agency_options = sorted(frame.agency.dropna().astype(str).unique().tolist())
        selected_agencies = st.multiselect("Agency", agency_options, placeholder="All agencies")
        with st.expander("Additional filters"):
            state_options = sorted(frame.state.dropna().astype(str).unique().tolist())
            type_options = sorted(frame.award_type.dropna().astype(str).unique().tolist())
            selected_states = st.multiselect("Recipient state", state_options, placeholder="All states")
            selected_types = st.multiselect("Award type", type_options, placeholder="All types",
                                             format_func=lambda code: {"A": "A · BPA call", "B": "B · Purchase order", "C": "C · Delivery order", "D": "D · Definitive contract"}.get(code, code))
        st.caption("Clear a filter to include all values.")
    else:
        selected_years, selected_agencies, selected_states, selected_types = [], [], [], []
        st.caption("Filters become available after the snapshot loads.")

result = None
if not frame.empty:
    try:
        result = calculate(
            frame, tuple(selected_years) or None, tuple(selected_agencies) or None,
            tuple(selected_states) or None, tuple(selected_types) or None,
        )
    except (ValueError, KeyError, TypeError) as exc:
        load_error = str(exc)

page_titles = {
    "Overview": ("NSF & NRC Vendor Concentration", "FY2024–2025 · Signed obligations, vendor concentration & ABC classification"),
    "ABC Classification": ("Vendor ABC Classification", "Value concentration, boundaries & classification detail"),
    "Vendor Analysis": ("Vendor Analysis", "Recipient-level net obligations & award context"),
    "Fiscal-Year Comparison": ("Fiscal-Year Comparison", "Annual net obligations by fiscal year and agency"),
    "Concentration & SQL": ("Concentration & SQL", "Query-backed concentration, identities and fiscal-year comparisons"),
}
st.title(page_titles[page][0])
st.markdown(f'<div class="subtitle">{page_titles[page][1]}</div>', unsafe_allow_html=True)
if not frame.empty:
    available_years = selected_years or sorted(frame.fiscal_year.dropna().astype(int).unique().tolist())
    period = ", ".join(f"FY {year}" for year in available_years)
    snapshot = metadata.get("retrieval_finished_at") or metadata.get("retrieved_at") or metadata.get("snapshot_datetime")
    source_label = str(metadata.get("source") or "Source metadata unavailable")
    st.caption(f"{period} · {source_label}" +
               (f" · Retrieved {snapshot}" if snapshot else " · Retrieval time not recorded"))
else:
    st.caption("Requested scope: NSF and NRC contract transactions · FY 2024–2025 · Snapshot not available")
if not frame.empty and metadata.get("source_verification") not in {"official_api_download_count_checked", "verified"}:
    st.warning("Source provenance is unverified. Confirm the snapshot metadata and archive before presenting these values as official-source findings.")
if load_error:
    st.error(f"The local snapshot could not be analyzed: {load_error}")

kpi = result["kpi"] if result else {}
loaded = result is not None
has_rows = loaded and bool(kpi.get("transactions", 0))


filtered_frame = frame
for field, values in [("fiscal_year", selected_years), ("agency", selected_agencies),
                      ("state", selected_states), ("award_type", selected_types)]:
    if values and not filtered_frame.empty:
        filtered_frame = filtered_frame.loc[filtered_frame[field].isin(values)]


def sql_result(name: str) -> pd.DataFrame:
    filters = tuple((field, tuple(values) if values else None) for field, values in [
        ("fiscal_year", selected_years), ("agency", selected_agencies),
        ("state", selected_states), ("award_type", selected_types)])
    return run_sql_file(name, data_path=DATA_PATH, filters=filters)


TABLE_SEQUENCE = 0


def table(data: pd.DataFrame, columns=None) -> None:
    """Keep a full desktop table and show readable field/value cards on phones."""
    global TABLE_SEQUENCE
    TABLE_SEQUENCE += 1
    shown = display_frame(data, columns)
    with st.container(key=f"desktop_table_{TABLE_SEQUENCE}"):
        st.dataframe(shown, hide_index=True, width="stretch", column_config={
            label: st.column_config.TextColumn(label, width="large") for label in shown.columns})

    if shown.empty:
        st.markdown('<div class="mobile-data-view mobile-record-count">No rows for these filters.</div>',
                    unsafe_allow_html=True)
        return

    # Avoid rendering hundreds of cards on a phone; keep the complete table on desktop.
    preview = shown.head(12)
    cards = []
    for _, row in preview.iterrows():
        # "Scope" repeats in comparison results and is not a useful card heading.
        heading_col = next((col for col in ("Vendor", "Agency", "Shared normalized name",
                                            "Recipient UEI", "Fiscal year", "ABC class")
                            if col in shown.columns and str(row[col]) != "—"), shown.columns[0])
        heading = html.escape(str(row[heading_col]))
        fields = "".join(
            '<div class="mobile-record-field"><span class="mobile-record-label">' +
            html.escape(str(col)) + '</span><span class="mobile-record-value">' +
            html.escape(str(value)) + '</span></div>'
            for col, value in row.items() if col != heading_col
        )
        cards.append(f'<article class="mobile-record"><div class="mobile-record-title">{heading}</div>{fields}</article>')
    more = (f'<div class="mobile-record-count">Showing 12 of {len(shown):,} rows. '
            'Use a desktop screen to browse the complete table.</div>'
            if len(shown) > 12 else '')
    st.markdown('<div class="mobile-data-view">' + "".join(cards) + more + '</div>',
                unsafe_allow_html=True)


def mobile_comparison_cards(data: pd.DataFrame, kind: str) -> None:
    """Show compact records on phones and retain the full table on wider screens."""
    from html import escape

    shown = display_frame(data)
    st.markdown("""
    <style>
    .mobile-comparison-cards { display: none; }
    @media (max-width: 640px) {
      .st-key-annual-comparison-table [data-testid="stDataFrame"],
      .st-key-rank-comparison-table [data-testid="stDataFrame"] { display: none; }
      .mobile-comparison-cards { display: grid; gap: 12px; margin: 6px 0 18px; }
      .mobile-comparison-card { padding: 14px; border: 1px solid rgba(140,150,170,.28);
        border-radius: 12px; background: rgba(120,135,160,.07); overflow-wrap: anywhere; }
      .mobile-comparison-card h4 { font-size: 15px; margin: 0 0 10px; }
      .mobile-comparison-card dl { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1.2fr);
        gap: 7px 12px; margin: 0; font-size: 13px; }
      .mobile-comparison-card dt { color: #aab4c6; }
      .mobile-comparison-card dd { margin: 0; text-align: right; font-weight: 600; }
    }
    </style>
    """, unsafe_allow_html=True)
    if data.empty:
        st.info("No records for the selected filters.")
        return
    if kind == "annual":
        fields = ["Net obligations (USD)", "Change (USD)", "Change (%)",
                  "New recipients", "Dropped recipients"]
    else:
        fields = ["Recipient UEI", "Previous rank", "Current rank",
                  "Rank improvement", "Previous net (USD)", "Current net (USD)"]
    cards = []
    for _, row in shown.iterrows():
        scope = row.get("Scope", "—")
        agency = row.get("Agency", "—")
        agency = "All agencies" if agency == "—" else agency
        year = row.get("Fiscal year", "—")
        heading = f"{agency} · FY{year}" if kind == "annual" else f"{agency} · FY{year}"
        details = "".join(
            f"<dt>{escape(label)}</dt><dd>{escape(str(row[label]))}</dd>"
            for label in fields if label in shown.columns
        )
        cards.append(f'<article class="mobile-comparison-card"><h4>{escape(heading)}</h4>'
                     f'<dl><dt>Scope</dt><dd>{escape(str(scope))}</dd>{details}</dl></article>')
    st.markdown('<div class="mobile-comparison-cards">' + "".join(cards) + '</div>',
                unsafe_allow_html=True)


def render_kpis() -> None:
    awards_available = loaded and kpi.get("total_awards") is not None
    cards = [
        ("NET OBLIGATIONS", money(kpi.get("net_obligations")), "Signed federal obligations · USD", "$", False),
        ("UNIQUE VENDORS", count(kpi.get("unique_vendors")), "Valid recipient identifiers", "◈", False),
        ("UNIQUE AWARDS" if awards_available else "TRANSACTIONS", count(kpi.get("total_awards") if awards_available else kpi.get("transactions")),
         "Distinct complete award identifiers" if awards_available else "Rows · award count unavailable", "≡", False),
        ("CATEGORY A VALUE SHARE", percent(kpi.get("category_a_share")), "Share of positive-net vendor value", "A", True),
    ]
    for column, (label, value, context, glyph, gold) in zip(st.columns(4), cards):
        column.markdown(
            f'<div class="kpi-card"><div class="kpi-label"><span class="kpi-glyph">{glyph}</span>{label}</div>'
            f'<div class="kpi-value{" gold" if gold else ""}">{value}</div>'
            f'<div class="kpi-context">{context}</div></div>', unsafe_allow_html=True,
        )


def pareto_chart(limit: int = 25, height: int = 300) -> None:
    if not has_rows:
        empty_chart("No vendor distribution to display")
        return
    vendors = result["vendors"]
    eligible = vendors[vendors["category"].isin(["A", "B", "C"])]
    if eligible.empty:
        empty_chart("No positive-net vendors", "ABC requires a positive value denominator and valid vendor identifiers.")
        return
    shown = eligible.head(limit)
    scale = st.selectbox("Pareto scale", ["Linear", "Logarithmic"], key=f"pareto_scale_{page}")
    st.caption("Bars: individual recipient obligations · Line: cumulative share of all positive-net recipients.")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=list(range(1, len(shown) + 1)), y=shown.net_obligations,
        marker_color=[COLORS[x] for x in shown.category], name="Vendor net obligations",
        customdata=shown[["vendor_name", "category", "share", "vendor_id"]].to_numpy(),
        hovertemplate="%{customdata[0]} · %{customdata[3]}<br>%{y:$,.2f}<br>Category %{customdata[1]}<br>Share %{customdata[2]:.2%}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=list(range(1, len(shown) + 1)), y=shown.cumulative_share * 100,
        name="Cumulative value", mode="lines", line={"color": "#F3F6FC", "width": 2},
        hovertemplate="Vendor rank %{x}<br>Cumulative value: %{y:.2f}%<extra></extra>",
    ), secondary_y=True)
    fig.add_hline(y=80, line_color=GOLD, line_dash="dot", line_width=1, secondary_y=True)
    fig.add_hline(y=95, line_color=BLUE, line_dash="dot", line_width=1, secondary_y=True)
    fig.update_xaxes(title_text="Vendor rank · largest net obligation first", dtick=5 if len(shown) > 10 else 1)
    fig.update_yaxes(title_text="Net obligations · USD" + (" (log scale)" if scale == "Logarithmic" else ""),
                     type="log" if scale == "Logarithmic" else "linear", tickprefix="$", secondary_y=False)
    fig.update_yaxes(range=[0, 105], title_text="Cumulative %", secondary_y=True)
    fig.update_layout(legend={"orientation": "h", "y": 1.18, "x": 0}, margin={"l": 8, "r": 12, "t": 42, "b": 12})
    plot(chart_style(fig, height))
    st.caption(f"Showing {len(shown):,} of {len(eligible):,} positive-net vendors. Cumulative share uses all "
               f"{len(eligible):,} vendors ({money(kpi.get('positive_vendor_value'), compact=False)}); dotted lines mark 80% / 95%.")


def distribution_chart() -> None:
    if not has_rows:
        empty_chart("No classified vendors to display")
        return
    distribution = result["distribution"]
    distribution = distribution[distribution.vendor_count.gt(0)]
    if distribution.empty:
        empty_chart("No valid vendor identifiers")
        return
    fig = px.pie(distribution, names="category", values="vendor_count", hole=.7,
                 color="category", color_discrete_map=COLORS,
                 category_orders={"category": ["A", "B", "C", "Unclassified"]})
    fig.update_traces(textinfo="percent", textfont_size=11,
                      hovertemplate="Category %{label}<br>%{value:,} vendors<br>%{percent} of valid vendors<extra></extra>")
    fig.add_annotation(text=f"<b>{int(distribution.vendor_count.sum()):,}</b><br>vendors", showarrow=False,
                       font={"color": "#F3F6FC", "size": 15})
    fig.update_layout(showlegend=True, legend={"orientation": "h", "y": -.05, "x": .5, "xanchor": "center"})
    plot(chart_style(fig, 300))
    st.caption("Donut: share of recipient count, NOT share of obligation value. The table separately reports value shares.")
    table(result["distribution"], ["category", "vendor_count", "vendor_share", "value_share"])


def top_vendor_chart(limit: int = 10, height: int = 280) -> None:
    if not has_rows or result["vendors"].empty:
        empty_chart("No vendor ranking to display")
        return
    top = result["vendors"].head(limit).iloc[::-1].copy()
    # Numeric positions allow full names in hover while keeping compact labels readable.
    unique_labels = vendor_labels(result["vendors"])
    labels = []
    for vendor in top.vendor_id:
        label = unique_labels[vendor]
        if " · " in label:
            name, suffix = label.rsplit(" · ", 1)
            label = (name[:23] + "…" if len(name) > 24 else name) + " · " + suffix
        elif len(label) > 36:
            label = label[:34] + "…"
        labels.append(label)
    fig = go.Figure(go.Bar(
        x=top.net_obligations, y=list(range(len(top))), orientation="h",
        marker_color=[COLORS[x] for x in top.category], customdata=top[["vendor_name", "category", "vendor_id"]].to_numpy(),
        hovertemplate="%{customdata[0]} · %{customdata[2]}<br>%{x:$,.2f}<br>Category %{customdata[1]}<extra></extra>",
    ))
    fig.update_yaxes(tickvals=list(range(len(top))), ticktext=labels)
    fig.update_xaxes(tickprefix="$", title_text="Net obligations · USD")
    fig.update_layout(margin={"l": 12, "r": 12, "t": 12, "b": 12})
    plot(chart_style(fig, max(height, 35 * len(top) + 100)))
    st.caption("Recipients are separate UEIs; shared names include a UEI suffix. Corporate parents are not consolidated. Full names and UEIs are available on hover.")


def trend_chart(height: int = 280) -> None:
    if not has_rows or result["trends"].empty:
        empty_chart("No fiscal-year totals to display")
        return
    trends = result["trends"].copy()
    trends["period"] = trends.fiscal_year.map(lambda value: f"FY {int(value)}")
    fig = px.bar(trends, x="period", y="net_obligations", color_discrete_sequence=[BLUE],
                 labels={"period": "", "net_obligations": "Net obligations · USD"})
    fig.update_traces(hovertemplate="%{x}<br>Net obligations %{y:$,.2f}<extra></extra>")
    fig.update_yaxes(tickprefix="$")
    plot(chart_style(fig, height))
    st.caption("Annual totals only; no monthly or longer-term trend is inferred.")


def agency_chart(height: int = 280) -> None:
    if not has_rows or result["agencies"].empty:
        empty_chart("No agency totals to display")
        return
    agencies = result["agencies"].sort_values(["net_obligations", "agency"], ascending=[False, True]).head(6).iloc[::-1]
    labels = [name if len(str(name)) <= 28 else str(name)[:26] + "…" for name in agencies.agency]
    fig = go.Figure(go.Bar(x=agencies.net_obligations, y=list(range(len(agencies))), orientation="h",
                           marker_color=BLUE, customdata=agencies.agency,
                           hovertemplate="%{customdata}<br>%{x:$,.2f}<extra></extra>"))
    fig.update_yaxes(tickvals=list(range(len(agencies))), ticktext=labels)
    fig.update_xaxes(tickprefix="$", title_text="Net obligations · USD")
    plot(chart_style(fig, height))
    st.caption(f"Showing {len(agencies)} agencies within the current filters.")


def show_findings() -> None:
    st.subheader("Key Findings")
    if not has_rows:
        st.info("No transactions match these filters." if loaded else
                "Findings will appear when the source snapshot is available.")
        return
    findings = build_findings(sql_result("04_concentration_hhi.sql"), sql_result("06_fy_comparison.sql"))
    if not findings:
        st.info("No positive-net concentration or two-year comparison is defined for this selection.")
    for headline, follow_up, source in findings:
        st.markdown(f'<div class="finding"><b>{html.escape(headline)}</b>'
                    f'<small>{html.escape(follow_up)} · Source: {html.escape(source)}</small></div>',
                    unsafe_allow_html=True)


def render_source_panel(*, expanded: bool = False) -> None:
    repository = "https://github.com/Granbe1l/USA-Procurement-Vendor-Dashboard"
    with st.expander("Source & calculations", expanded=expanded):
        source_col, audit_col = st.columns([1.3, 1])
        with source_col:
            st.markdown("**Source & coverage**")
            st.markdown("[USAspending.gov](https://www.usaspending.gov/) · "
                        "[Official API](https://api.usaspending.gov/docs/)")
            st.write("Target scope: National Science Foundation and Nuclear Regulatory Commission contract transactions; FY 2024–2025.")
            if metadata:
                st.write("Snapshot source: " + str(metadata.get("source") or "Not recorded"))
                captured = metadata.get("retrieval_finished_at") or metadata.get("retrieved_at") or metadata.get("snapshot_datetime")
                st.write("Snapshot retrieved: " + (str(captured) if captured else "Not recorded"))
            else:
                st.caption("Source metadata and retrieval time are not available yet.")
            if not frame.empty:
                dates = pd.to_datetime(frame.action_date, errors="coerce").dropna()
                if len(dates):
                    st.write(f"Observed action dates: {dates.min().date().isoformat()} to {dates.max().date().isoformat()} "
                             "(full prepared snapshot).")
            st.markdown("**Current selection**")
            filter_values = [("Fiscal year", selected_years), ("Agency", selected_agencies),
                             ("Recipient state", selected_states), ("Award type", selected_types)]
            st.write(" · ".join(f"{label}: {', '.join(map(str, values)) if values else 'All'}"
                                for label, values in filter_values))
            if loaded:
                st.caption(f"{len(filtered_frame):,} filtered transactions / {len(frame):,} full-snapshot transactions. "
                           "All metrics, charts and downloads use this selection; ABC is recalculated within it.")
            else:
                st.caption("No transaction snapshot is loaded.")
        with audit_col:
            st.markdown("**Cleaning audit**")
            reconciliation = quality.get("row_reconciliation", {})
            audit_counts = [
                ("Raw input", quality.get("initial_rows", reconciliation.get("raw"))),
                ("Exact duplicates removed", quality.get("identical_duplicate_rows_removed", reconciliation.get("exact_duplicates_removed"))),
                ("Quarantined", quality.get("quarantined_rows", reconciliation.get("quarantined"))),
                ("Retained", quality.get("retained_rows", reconciliation.get("retained"))),
            ]
            if quality:
                st.dataframe(pd.DataFrame([(label, count(value)) for label, value in audit_counts],
                                          columns=["Stage", "Rows"]), hide_index=True, width="stretch")
                values = [value for _, value in audit_counts]
                if all(value is not None for value in values):
                    raw, duplicates, quarantined, retained = map(int, values)
                    st.caption(f"{raw:,} raw = {duplicates:,} duplicates removed + {quarantined:,} quarantined + {retained:,} retained.")
                st.caption("Audit counts describe the full snapshot and do not change with filters. "
                           "Identical copies are removed; conflicting transaction IDs and invalid records are quarantined.")
            else:
                st.caption("Cleaning counts are not available until the snapshot is prepared.")
        st.markdown("**How values are calculated**")
        st.markdown("""
- **Net obligations** = sum of signed transaction obligations (USD), including negative adjustments. These values are commitments, not cash payments.
- **Vendors / awards** = distinct valid recipient / award identifiers. If an award ID is missing in the selection, the card shows transaction count instead.
- **ABC denominator** = sum of positive-net values of identified vendors. Rank vendors by this value; assign each equal-value group using cumulative share **before** it is added: **A <80%**, **B 80–<95%**, **C ≥95%**. A group crossing a boundary stays together; nonpositive-net vendors remain **Unclassified**.
- **Category A share** = Category A value ÷ the positive-net vendor denominator. Vendor-count percentages use the count of all valid vendor IDs instead.
- **Fiscal year** runs October 1–September 30 and is derived from action date; the annual comparison does not establish a longer-term trend.
""")
        if has_rows:
            st.caption(f"Current ABC denominator: {money(kpi.get('positive_vendor_value'), compact=False)}. "
                       f"Net value outside that denominator: {money(kpi.get('excluded_vendor_value'), compact=False)}; "
                       f"transactions missing a vendor ID: {count(kpi.get('missing_vendor_rows'))}.")
        st.markdown("**Interpretation limit:** This agency subset does not represent all U.S. federal procurement. "
                    "ABC describes value concentration, not vendor quality, efficiency or risk.")
        st.markdown(f"[Methodology]({repository}/blob/main/docs/METHODOLOGY.md) · "
                    f"[Source notes]({repository}/blob/main/docs/SOURCES.md) · "
                    f"[Code]({repository})")
        if loaded:
            data_col, vendors_col = st.columns(2)
            data_col.download_button("Download filtered transactions", filtered_frame.to_csv(index=False).encode("utf-8"),
                                     "procurement_transactions_filtered.csv", "text/csv", key="download_filtered_transactions")
            vendors_col.download_button("Download filtered vendor summary", result["vendors"].to_csv(index=False).encode("utf-8"),
                                        "vendor_abc_summary.csv", "text/csv", key="download_filtered_vendors")
        if metadata or quality:
            meta_col, quality_col = st.columns(2)
            if metadata:
                meta_col.download_button("Download metadata · full snapshot", json.dumps(metadata, indent=2).encode("utf-8"),
                                         "metadata.json", "application/json", key="download_full_metadata")
            if quality:
                quality_col.download_button("Download quality audit · full snapshot", json.dumps(quality, indent=2).encode("utf-8"),
                                            "quality.json", "application/json", key="download_full_quality")


if page == "Overview":
    st.write("**Research question:** How concentrated are signed contract obligations among NSF and NRC recipients in FY2024–FY2025? Compare ABC value shares and agency-year HHI to identify records worth examining—not to label recipients as risky.")
    render_kpis()
    st.caption("Snapshot-based analysis · NSF and NRC only · FY2024–FY2025 · Negative adjustments included · Not live data")
    with st.expander("Read this dashboard in 30 seconds"):
        st.markdown("""
**Question:** Are contract obligations concentrated among a small number of recipients?

- **ABC** ranks recipients by positive net obligations. Category A contains the highest-value recipients under the documented cumulative-value rule; it is **not** a quality or risk rating.
- **HHI** summarizes how concentrated positive-net recipient values are within an agency and fiscal year. Compare agencies and years, but do not treat it as proof of anticompetitive behavior.
- **Net obligations** are signed commitments, including reductions and corrections—not cash payments.
- **Scope:** NSF and NRC contract transactions, FY2024–FY2025. This is a fixed official-source snapshot, not live data.
**Start here:** Read Key Findings, then compare the Pareto chart and agency-year HHI. Use the sidebar to narrow the analysis.
""")
    show_findings()
    st.caption("Interpretation: HHI compares concentration of positive-net recipient obligations, not procurement competitiveness or vendor performance. Inspect award records before drawing conclusions.")
    with st.expander("Case study · agency and fiscal-year concentration"):
        if has_rows:
            comparison = sql_result("04_concentration_hhi.sql")
            displayed = comparison.assign(net_obligations=comparison.net_obligation_cents / 100)
            table(displayed, ["agency", "fiscal_year", "net_obligations", "positive_vendors",
                              "category_a_vendors", "category_a_value_share", "top_vendor_share", "top_10_share", "hhi"])
            st.download_button("Download concentration comparison", comparison.to_csv(index=False).encode(),
                               "agency_year_concentration.csv", "text/csv")
        else:
            st.info("Concentration findings require a prepared snapshot.")
        st.caption("HHI = 10,000 × sum of squared positive-net recipient shares. Higher means more concentrated value.")
    with st.expander("How to interpret concentration"):
        st.write("Compare shares rather than agency budgets. HHI and ABC do not measure performance or prove supply risk. Inspect recipients and award adjustments before deciding follow-up. UEIs are not consolidated into corporate parents; two fiscal years support a comparison, not a trend.")
    left, right = st.columns([2, 1])
    with left, st.container(border=True):
        chart_heading("ABC Pareto Analysis", "Vendor-level net obligations · category-colored bars and cumulative share")
        pareto_chart()
    with right, st.container(border=True):
        chart_heading("ABC Vendor Distribution", "Number of identified vendors by classification")
        distribution_chart()
    first, second, third = st.columns(3)
    with first, st.container(border=True):
        chart_heading("Top 10 Vendors", "Largest recipient totals in the selected snapshot")
        top_vendor_chart()
    with second, st.container(border=True):
        chart_heading("Fiscal-Year Comparison", "Annual transaction obligations")
        trend_chart()
    with third, st.container(border=True):
        chart_heading("Agency Distribution", "Agency totals within this dataset")
        agency_chart()

elif page == "ABC Classification":
    render_kpis()
    st.caption("Categories use positive-net vendor value. Boundary rules are available in Source & calculations.")
    with st.container(border=True):
        chart_heading("ABC Pareto Detail", "Cumulative contribution of positive-net vendors")
        limit = st.slider("Vendors shown in Pareto", 10, 100, 40, 10)
        pareto_chart(limit=limit, height=360)
    if has_rows:
        table(result["distribution"])
        table(result["vendors"])

elif page == "Vendor Analysis":
    render_kpis()
    with st.container(border=True):
        chart_heading("Vendor Ranking", "Net obligations by valid recipient identifier")
        top_vendor_chart(limit=15, height=410)
    if has_rows and not result["vendors"].empty:
        vendors = result["vendors"]
        names = vendors.set_index("vendor_id").vendor_name.to_dict()
        vendor_id = st.selectbox("Select a vendor", vendors.vendor_id.tolist(),
                                 format_func=lambda value: f"{names[value]} · {value}")
        selected = vendors.loc[vendors.vendor_id.eq(vendor_id)]
        table(selected)
        transactions = filtered_frame.loc[filtered_frame.vendor_id.eq(vendor_id)]
        st.caption("Selected vendor transactions, with global filters applied.")
        table(transactions)
        st.caption("Downloads retain original machine-friendly columns, including integer cents; see docs/DATA_DICTIONARY.md.")

elif page == "Fiscal-Year Comparison":
    render_kpis()
    st.caption("Two fiscal years support a comparison, not a trend. Differences can reflect modifications.")
    if has_rows:
        annual = sql_result("06_fy_comparison.sql")
        combined = annual.loc[annual.scope.eq("combined")]
        comparison_years = combined.loc[combined.previous_year.notna()].sort_values("fiscal_year")
        if not comparison_years.empty:
            latest = comparison_years.iloc[-1]
            first, second, third = st.columns(3)
            first.metric(f"FY{int(latest.fiscal_year)} change vs FY{int(latest.previous_year)}", money(latest.change_usd),
                         percent(latest.change_share) if pd.notna(latest.change_share) else "Prior total is zero")
            second.metric("New recipients", count(latest.new_vendors))
            third.metric("Dropped recipients", count(latest.dropped_vendors))
            st.caption("New/dropped means present/absent by UEI, including nonpositive nets; it does not establish supplier churn.")
        else:
            st.info("Select both fiscal years to compare values and recipient presence.")
        grouped = annual.loc[annual.scope.eq("agency")].copy()
        grouped["period"] = grouped.fiscal_year.map(lambda value: f"FY {int(value)}")
        grouped["label"] = grouped.net_obligations.map(money)
        fig = px.bar(grouped, x="period", y="net_obligations", color="agency", barmode="group", text="label",
                     color_discrete_sequence=[BLUE, GOLD], labels={"net_obligations": "Net obligations · USD", "period": ""})
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(legend={"orientation": "h", "y": -.25})
        plot(chart_style(fig, 370))
        st.subheader("Annual signed obligations")
        with st.container(key="annual-comparison-table"):
            table(annual)
            mobile_comparison_cards(annual, "annual")
        st.subheader("Top-10 recipient rank changes")
        ranks = sql_result("06_vendor_rank_changes.sql")
        with st.container(key="rank-comparison-table"):
            table(ranks)
            mobile_comparison_cards(ranks, "ranks")
        st.caption("Positive rank improvement means moving up. A missing rank means no selected transaction in that year. Top 10 uses signed recipient nets, with UEI breaking ties.")
    else:
        empty_chart("No fiscal-year comparison available")

elif page == "Concentration & SQL":
    render_kpis()
    st.caption("Queries use the same active transaction filters as the pandas views. All connections are in memory.")
    if has_rows:
        labels = {"01_vendor_totals.sql": "Vendor totals", "02_abc_classification.sql": "ABC classification",
                  "03_abc_summary.sql": "ABC summary", "04_concentration_hhi.sql": "Concentration",
                  "06_fy_comparison.sql": "Fiscal-year comparison", "06_vendor_rank_changes.sql": "Rank changes",
                  "07_vendor_name_overlap.sql": "Shared vendor names"}
        chosen = st.selectbox("SQL analysis", list(labels), format_func=labels.get)
        data = sql_result(chosen)
        if "net_obligation_cents" in data:
            data = data.assign(net_obligations=data.net_obligation_cents / 100)
        table(data)
        if chosen == "07_vendor_name_overlap.sql":
            st.caption("Whitespace/case-normalized names are only an approximation. Different UEIs remain separate; this is not corporate-parent consolidation.")
        st.caption("Competition is unavailable: no competition field is retained in the current snapshot schema.")
    else:
        st.info("Load a prepared snapshot to run the SQL analyses.")

if not loaded:
    download_failed = bootstrap_status and bootstrap_status.get("status") == "error"
    if download_failed:
        st.error("The official USAspending snapshot could not be loaded. " +
                 str(bootstrap_status.get("error") or "The official source request failed."))
        st.caption("KPI values and charts remain unavailable until the official snapshot is retrieved successfully.")
    elif not load_error:
        st.warning("The official procurement snapshot is not available yet. KPI values and charts will appear after it is loaded.")
    retry = bool(download_failed or load_error)
    if st.button("Retry official download" if retry else "Load official data",
                 key="retry_official_snapshot" if retry else "load_official_snapshot", type="primary"):
        initialize_snapshot.clear()
        st.session_state.pop(status_key, None)
        st.session_state[request_key] = True
        st.rerun()
    st.markdown("See the [source setup guide](https://github.com/Granbe1l/USA-Procurement-Vendor-Dashboard/blob/main/README.md) for local setup and source access details.")
elif not has_rows:
    st.info("No transactions match these filters. Clear or change the sidebar selections to restore the analysis.")

render_source_panel()

st.markdown('<div class="footer">Candy · Federal Procurement Analysis</div>', unsafe_allow_html=True)
