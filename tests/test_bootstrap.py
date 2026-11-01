"""Exercise first-run initialization using isolated, explicitly synthetic fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import snapshot_bootstrap as bootstrap  # noqa: E402
from procurement import analyze, load_data  # noqa: E402
from scripts.prepare_data import prepare as real_prepare  # noqa: E402


@pytest.fixture
def official_style_fetch(monkeypatch):
    """Mock the transport only; actual validation/preparation still runs."""
    calls = []

    def fetch(output_dir, timeout=180, **_kwargs):
        calls.append((Path(output_dir), timeout))
        directory = Path(output_dir) / f"synthetic-test-capture-{len(calls)}"
        directory.mkdir(parents=True)
        rows = []
        for key, vendor, value, date, agency, state, award, award_type in [
            ("T1", "TESTVENDOR001", "90.00", "2024-01-01", "NATIONAL SCIENCE FOUNDATION", "NY", "AWARD1", "D"),
            ("T2", "TESTVENDOR001", "-10.00", "2024-02-01", "NATIONAL SCIENCE FOUNDATION", "NY", "AWARD1", "D"),
            ("T3", "TESTVENDOR002", "15.00", "2025-01-01", "NUCLEAR REGULATORY COMMISSION", "CA", "AWARD2", "B"),
            ("T4", "TESTVENDOR003", "5.00", "2025-02-01", "NATIONAL SCIENCE FOUNDATION", "NY", "AWARD3", "D"),
        ]:
            rows.append({
                "contract_transaction_unique_key": key, "recipient_uei": vendor,
                "recipient_name": f"SYNTHETIC UNIT TEST {vendor}", "award_unique_key": award,
                "action_date": date, "awarding_agency_name": agency, "recipient_state_code": state,
                "contract_award_type": award_type, "federal_action_obligation": value,
            })
        raw = directory / "contracts.csv"
        pd.DataFrame(rows).to_csv(raw, index=False)
        metadata = {
            "status": "complete", "source": "USAspending.gov public API",
            "source_verification": "official_api_download_count_checked",
            "raw_file": raw.name, "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            "raw_row_count": 4, "row_count": 4, "transaction_count_before": 4, "transaction_count_after": 4,
            "retrieval_started_at": "2026-10-31T00:00:00+00:00",
            "retrieval_finished_at": "2026-10-31T00:00:01+00:00",
            "fixture_notice": "SYNTHETIC TEST RESPONSE ONLY; not an official downloaded dataset or project finding",
        }
        path = directory / "metadata.json"
        path.write_text(json.dumps(metadata), encoding="utf-8")
        return path

    monkeypatch.setattr(bootstrap, "fetch_dataset", fetch)
    return fetch, calls


def cards(app):
    return [value for element in app.markdown
            for value in re.findall(r'<div class="kpi-value(?: gold)?">(.*?)</div>', element.value)]


def test_initialization_promotes_complete_snapshot_then_reuses_without_fetch(official_style_fetch, tmp_path, monkeypatch):
    _, calls = official_style_fetch
    output = tmp_path / "processed"
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "ready"
    assert result["fetched"] is True
    assert len(calls) == 1
    assert all((output / name).is_file() for name in ["transactions.csv.gz", "metadata.json", "quality.json", "summary.json"])
    data = load_data(output / "transactions.csv.gz")
    assert len(data) == 4
    assert analyze(data)["kpi"]["net_obligations"] == 100.
    assert analyze(data)["kpi"]["category_a_share"] == .8
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["status"] == "complete"
    assert metadata["source_verification"] == "official_api_download_count_checked"
    assert metadata["imported_row_count"] == metadata["raw_row_count"] == metadata["transaction_count_before"] == metadata["transaction_count_after"] == 4
    assert "SYNTHETIC TEST RESPONSE ONLY" in metadata["fixture_notice"]
    second = bootstrap.ensure_snapshot(output)
    assert second["status"] == "ready"
    assert second["fetched"] is False
    assert len(calls) == 1

    # An initialized bundle renders the actual analytic charts, not the missing-data shell.
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "0")
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(output))
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert cards(app) == ["$100.00", "3", "3", "80.0%"]
    assert len(app.get("plotly_chart")) == 5


def test_failed_fetch_does_not_promote_and_can_retry(official_style_fetch, tmp_path, monkeypatch):
    fetch, calls = official_style_fetch
    output = tmp_path / "processed"

    def blocked(*_args, **_kwargs):
        raise bootstrap.FetchError("SYNTHETIC TEST: upstream unavailable")
    monkeypatch.setattr(bootstrap, "fetch_dataset", blocked)
    failure = bootstrap.ensure_snapshot(output)
    assert failure["status"] == "error"
    assert "upstream unavailable" in failure["error"]
    assert not output.exists()
    monkeypatch.setattr(bootstrap, "fetch_dataset", fetch)
    success = bootstrap.ensure_snapshot(output)
    assert success["status"] == "ready"
    assert len(calls) == 1


def test_partial_prepare_failure_preserves_existing_directory(official_style_fetch, tmp_path, monkeypatch):
    output = tmp_path / "processed"
    output.mkdir()
    sentinel = output / "existing-user-file.txt"
    sentinel.write_text("preserve this file", encoding="utf-8")

    def failing_prepare(raw_path, metadata_path, output_dir):
        stage = Path(output_dir)
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "transactions.csv.gz").write_bytes(b"incomplete test output")
        raise ValueError("SYNTHETIC TEST: interrupted preparation")
    monkeypatch.setattr(bootstrap, "prepare", failing_prepare)
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "error"
    assert sentinel.read_text() == "preserve this file"
    assert not (output / "transactions.csv.gz").exists()
    assert not (output / "metadata.json").exists()


@pytest.mark.parametrize("fault", ["raw_sha256", "transaction_count_after"])
def test_checksum_or_source_count_failure_prevents_promotion(official_style_fetch, tmp_path, monkeypatch, fault):
    fetch, _ = official_style_fetch
    output = tmp_path / "processed"

    def corrupt_metadata(*args, **kwargs):
        path = fetch(*args, **kwargs)
        metadata = json.loads(path.read_text())
        metadata[fault] = "0" * 64 if fault == "raw_sha256" else 5
        path.write_text(json.dumps(metadata), encoding="utf-8")
        return path
    monkeypatch.setattr(bootstrap, "fetch_dataset", corrupt_metadata)
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "error"
    assert not output.exists()


@pytest.mark.parametrize("field", ["raw_sha256", "raw_row_count", "transaction_count_before", "transaction_count_after"])
def test_automatic_initialization_requires_each_integrity_proof(official_style_fetch, tmp_path, monkeypatch, field):
    fetch, _ = official_style_fetch

    def missing_proof(*args, **kwargs):
        path = fetch(*args, **kwargs)
        metadata = json.loads(path.read_text())
        metadata.pop(field)
        path.write_text(json.dumps(metadata), encoding="utf-8")
        return path
    monkeypatch.setattr(bootstrap, "fetch_dataset", missing_proof)
    output = tmp_path / "processed"
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "error"
    assert "SHA-256 or source-count evidence" in result["error"]
    assert not output.exists()


@pytest.mark.parametrize("field,value", [
    ("raw_sha256", "x" * 64), ("raw_row_count", True),
    ("transaction_count_before", 0), ("transaction_count_after", -1),
])
def test_integrity_proofs_need_valid_hash_and_positive_integer_counts(official_style_fetch, tmp_path, monkeypatch, field, value):
    fetch, _ = official_style_fetch

    def invalid_proof(*args, **kwargs):
        path = fetch(*args, **kwargs)
        metadata = json.loads(path.read_text())
        metadata[field] = value
        path.write_text(json.dumps(metadata), encoding="utf-8")
        return path
    monkeypatch.setattr(bootstrap, "fetch_dataset", invalid_proof)
    output = tmp_path / "processed"
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "error"
    assert "SHA-256 or source-count evidence" in result["error"]
    assert not output.exists()


def test_prepare_return_value_cannot_bypass_processed_bundle_validation(official_style_fetch, tmp_path, monkeypatch):
    output = tmp_path / "processed"

    def dishonest_prepare(raw_path, metadata_path, output_dir):
        result = real_prepare(raw_path, metadata_path, output_dir)
        # Simulate an interrupted/corrupt writer despite a successful return value.
        (Path(output_dir) / "transactions.csv.gz").write_bytes(b"not a valid gzip")
        return result
    monkeypatch.setattr(bootstrap, "prepare", dishonest_prepare)
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "error"
    assert not output.exists()


def test_ui_caches_failed_bootstrap_across_navigation_and_retries_once(official_style_fetch, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    calls = []
    real_ensure = bootstrap.ensure_snapshot
    def failure(data_dir):
        calls.append(Path(data_dir))
        if len(calls) == 1:
            return {"status": "error", "error": "SYNTHETIC TEST: temporary source failure", "fetched": False}
        return real_ensure(data_dir)
    monkeypatch.setattr(bootstrap, "ensure_snapshot", failure)
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "1")
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert len(calls) == 1
    for page in app.radio[0].options:
        app.radio[0].set_value(page).run(timeout=30)
        assert not app.exception
    assert len(calls) == 1
    app.button(key="retry_official_snapshot").click().run(timeout=30)
    assert not app.exception
    assert len(calls) == 2
    app.radio[0].set_value("Overview").run(timeout=30)
    assert not app.exception
    assert cards(app) == ["$100.00", "3", "3", "80.0%"]
    assert len(app.get("plotly_chart")) == 5
    app.multiselect[0].set_value([2024]).run(timeout=30)
    assert not app.exception
    assert cards(app) == ["$80.00", "1", "1", "100.0%"]
    assert len(calls) == 2
    assert len(official_style_fetch[1]) == 1


def test_failed_atomic_promotion_restores_existing_files(official_style_fetch, tmp_path, monkeypatch):
    output = tmp_path / "processed"
    output.mkdir()
    sentinel = output / "existing-user-file.txt"
    sentinel.write_text("must survive", encoding="utf-8")
    replace = Path.replace

    def fail_staged_replace(source, target):
        if source.name == "processed" and source.parent.name.startswith(".procurement-prepare-"):
            raise OSError("SYNTHETIC TEST: promotion disk failure")
        return replace(source, target)
    monkeypatch.setattr(Path, "replace", fail_staged_replace)
    result = bootstrap.ensure_snapshot(output)
    assert result["status"] == "error"
    assert sentinel.read_text() == "must survive"
    assert list(output.iterdir()) == [sentinel]


def test_ui_disabled_auto_fetch_only_initializes_after_explicit_load(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    calls = []
    def failure(data_dir):
        calls.append(Path(data_dir))
        return {"status": "error", "error": "SYNTHETIC TEST", "fetched": False}
    monkeypatch.setattr(bootstrap, "ensure_snapshot", failure)
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "0")
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert not calls
    app.button(key="load_official_snapshot").click().run(timeout=30)
    assert not app.exception
    assert len(calls) == 1


def test_manual_retry_repairs_existing_incomplete_bundle(official_style_fetch, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    output = tmp_path / "processed"
    output.mkdir()
    partial = output / "transactions.csv.gz"
    partial.write_bytes(b"SYNTHETIC TEST interrupted previous output")
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(output))
    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "0")
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert cards(app) == ["—"] * 4
    assert not official_style_fetch[1]
    app.button(key="retry_official_snapshot").click().run(timeout=30)
    assert not app.exception
    assert cards(app) == ["$100.00", "3", "3", "80.0%"]
    assert len(app.get("plotly_chart")) == 5
    assert len(official_style_fetch[1]) == 1
    backups = list(tmp_path.glob("processed-previous-*"))
    assert len(backups) == 1
    assert (backups[0] / "transactions.csv.gz").read_bytes() == b"SYNTHETIC TEST interrupted previous output"


def test_bootstrap_reuses_parquet_only_and_rejects_corrupt_companion(official_style_fetch, tmp_path):
    output = tmp_path / 'processed'
    assert bootstrap.ensure_snapshot(output)['status'] == 'ready'
    csv = output / 'transactions.csv.gz'
    saved = csv.read_bytes()
    csv.unlink()
    assert bootstrap.ensure_snapshot(output) == {'status': 'ready', 'fetched': False}
    csv.write_bytes(saved + b'corrupt')
    assert not bootstrap._valid_snapshot(output)
    csv.write_bytes(saved)
    parquet = output / 'transactions.parquet'
    parquet.write_bytes(parquet.read_bytes() + b'corrupt')
    assert not bootstrap._valid_snapshot(output)
