"""Capture Streamlit screenshots from the bundled official snapshot."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path("artifacts/review-screenshots")
out.mkdir(parents=True, exist_ok=True)
metadata = json.loads(Path("data/processed/metadata.json").read_text())
assert metadata.get("status") == "complete"
assert metadata.get("source_verification") == "official_api_download_count_checked"
assert Path("data/processed/transactions.parquet").is_file()

def capture_sections(page, slug: str, viewport: dict, metadata: dict) -> None:
    """Capture each segment of Streamlit's internal scrolling main area."""
    # Streamlit uses an inner scrolling element. Locate the element that
    # actually scrolls rather than assuming stMain itself is scrollable.
    scroll = page.locator('[data-testid="stMain"]').first.evaluate_handle("""root => {
        const nodes = [root, ...root.querySelectorAll('*')];
        const candidates = nodes.filter(el => {
            const style = getComputedStyle(el);
            return el.scrollHeight > el.clientHeight + 80
                && el.clientHeight > 200
                && ['auto', 'scroll'].includes(style.overflowY);
        });
        candidates.sort((a, b) => (b.clientHeight * b.clientWidth) - (a.clientHeight * a.clientWidth));
        return candidates[0] || root;
    }""")
    dims = scroll.evaluate("""el => ({
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        overflowY: getComputedStyle(el).overflowY,
        testId: el.getAttribute('data-testid')
    })""")
    assert dims["clientHeight"] > 0
    assert dims["scrollHeight"] >= dims["clientHeight"]
    step = max(1, dims["clientHeight"] - 120)
    last = max(0, dims["scrollHeight"] - dims["clientHeight"])
    positions = list(range(0, last + 1, step))
    if positions[-1] != last:
        positions.append(last)
    actual_positions = []
    for idx, y in enumerate(positions):
        actual = scroll.evaluate("(el, y) => { el.scrollTop = y; return el.scrollTop; }", y)
        page.wait_for_timeout(500)
        actual = scroll.evaluate("(el) => el.scrollTop")
        actual_positions.append(actual)
        if abs(actual - y) > 5:
            raise AssertionError(f"{slug}: scroll did not reach {y}; actual {actual}")
        page.screenshot(
            path=str(out / f"{slug}-part{idx + 1:02d}.png"),
            animations="disabled",
        )
    if last > 0 and len(set(actual_positions)) < 2:
        raise AssertionError(f"{slug}: captured only one effective scroll position")
    (out / f"{slug}.json").write_text(json.dumps({
        "viewport": viewport,
        "scroll_container": dims,
        "requested_scroll_positions": positions,
        "actual_scroll_positions": actual_positions,
        "snapshot": metadata["retrieval_finished_at"],
        "url": page.url,
    }, indent=2))
    scroll.evaluate("(el) => { el.scrollTop = 0; }")
    # Capture real rendered Plotly charts individually; the viewport screenshots
    # can clip the bottom of a chart in Streamlit's scroll container.
    charts = page.locator('[data-testid="stPlotlyChart"]')
    for chart_index in range(min(charts.count(), 6)):
        chart = charts.nth(chart_index)
        chart.scroll_into_view_if_needed(timeout=15000)
        page.wait_for_timeout(600)
        chart.screenshot(
            path=str(out / f"{slug}-chart{chart_index + 1:02d}.png"),
            animations="disabled",
            timeout=30000,
        )



with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, viewport in [
        ("desktop", {"width": 1440, "height": 1000}),
        ("mobile", {"width": 390, "height": 844}),
    ]:
        page = browser.new_page(viewport=viewport, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8501", wait_until="networkidle", timeout=90000)
        page.get_by_text("NSF & NRC Vendor Concentration", exact=True).first.wait_for(timeout=90000)
        page.get_by_text("Key Findings", exact=True).first.wait_for(timeout=90000)
        capture_sections(page, f"overview-{name}", viewport, metadata)
        if name == "desktop":
            # Real browser download from the official 5,020-row snapshot, not a
            # simulated DataFrame export or a fixture.
            page.get_by_text("Source & calculations", exact=True).first.click()
            button = page.get_by_role("button", name="Download filtered transactions")
            button.wait_for(timeout=30000)
            with page.expect_download(timeout=30000) as event:
                button.click()
            download = event.value
            assert download.suggested_filename == "procurement_transactions_filtered.csv"
            with open(download.path(), newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                assert "obligation_cents" in (reader.fieldnames or [])
                rows = sum(1 for _ in reader)
            assert rows == metadata["row_count"] == 5020, f"Browser CSV contains {rows} rows"
            print(f"PASS browser CSV download: {rows} official transactions")
        if name == "desktop":
            for label, slug in [
                ("ABC Classification", "abc"),
                ("Fiscal-Year Comparison", "fiscal-year"),
                ("Concentration & SQL", "concentration-sql"),
            ]:
                page.get_by_text(label, exact=True).first.click()
                page.wait_for_timeout(2500)
                capture_sections(page, f"{slug}-{name}", viewport, metadata)
        if errors:
            raise AssertionError(f"{name} browser errors: {errors}")
        page.close()
    browser.close()
print(f"Captured {len(list(out.glob('*.png')))} screenshot segments with official snapshot.")
