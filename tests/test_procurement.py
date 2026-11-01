"""Deterministic synthetic fixtures test logic, never portfolio findings."""

from __future__ import annotations

from decimal import Decimal
import gzip
import hashlib
import importlib.util
import inspect
import io
import json
from pathlib import Path
import re
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procurement import CANONICAL_COLUMNS, analyze, clean_transactions, load_data  # noqa: E402

NSF = "National Science Foundation"
NRC = "Nuclear Regulatory Commission"


def transaction(key, vendor="VENDOR-A", amount="90.00", date="2024-01-01", agency=NSF, state="NY", award_type="D", award=None):
    return {
        "transaction_id": key, "vendor_id": vendor, "vendor_name": f"Test vendor {vendor or 'missing identity'}",
        "award_id": award if award is not None else f"AWARD-{key}", "action_date": date,
        "agency": agency, "state": state, "award_type": award_type, "obligation": amount,
    }


@pytest.fixture
def raw_transactions():
    return pd.DataFrame([
        transaction("t1", award="AWARD-A"),
        transaction("t2", amount="-10.00", date="2024-02-01", award="AWARD-A"),
        transaction("t3", vendor="VENDOR-B", amount="10.00", date="2025-01-01", state="CA"),
        transaction("t4", vendor="VENDOR-C", amount="6.00", agency=NRC, award_type="B"),
        transaction("t5", vendor="VENDOR-D", amount="4.00", date="2025-01-01", agency=NRC, state="CA", award_type="B"),
        transaction("t6", vendor="VENDOR-E", amount="-5.00"),
        transaction("t7", vendor="VENDOR-Z", amount="0.00", date="2025-01-01", agency=NRC, state="DC"),
        transaction("t8", vendor="", amount="2.00"),
        transaction("t9", vendor=None, amount="3.00", date="2025-01-01", agency=NRC, state="CA"),
    ])


@pytest.fixture
def cleaned(raw_transactions):
    return clean_transactions(raw_transactions)


def test_signed_total_identity_and_award_unit_are_distinct(cleaned):
    data, audit = cleaned
    result = analyze(data)
    assert data.obligation_cents.sum() == 10000
    assert Decimal(str(result["kpi"]["net_obligations"])) == Decimal("100.00")
    assert result["kpi"]["unique_vendors"] == 6
    assert result["kpi"]["total_awards"] == 8
    assert result["kpi"]["transactions"] == 9
    assert result["kpi"]["missing_vendor_rows"] == 2
    assert audit["negative_obligation_rows"] == 2
    assert audit["zero_obligation_rows"] == 1
    assert audit["retained_rows"] == audit["unique_transaction_ids"] == 9
    vendors = result["vendors"].set_index("vendor_id")
    assert "" not in vendors.index
    assert vendors.net_obligations.to_dict() == {
        "VENDOR-A": 80., "VENDOR-B": 10., "VENDOR-C": 6., "VENDOR-D": 4., "VENDOR-E": -5., "VENDOR-Z": 0.,
    }
    assert result["agencies"].net_obligations.sum() == result["trends"].net_obligations.sum() == result["states"].net_obligations.sum() == 100.


def test_abc_uses_positive_signed_vendor_nets_and_reconciles(cleaned):
    result = analyze(cleaned[0])
    vendors = result["vendors"].set_index("vendor_id")
    assert vendors.category.to_dict() == {
        "VENDOR-A": "A", "VENDOR-B": "B", "VENDOR-C": "B", "VENDOR-D": "C", "VENDOR-E": "Unclassified", "VENDOR-Z": "Unclassified",
    }
    positives = vendors[vendors.net_obligations > 0]
    assert positives.share.sum() == pytest.approx(1.)
    assert positives.cumulative_share.is_monotonic_increasing
    assert positives.cumulative_share.iloc[-1] == pytest.approx(1.)
    assert result["kpi"]["positive_vendor_value"] == 100.
    assert result["kpi"]["category_a_share"] == pytest.approx(.8)
    assert vendors.loc[["VENDOR-E", "VENDOR-Z"], "share"].isna().all()
    assert vendors.loc[["VENDOR-E", "VENDOR-Z"], "cumulative_share"].isna().all()
    distribution = result["distribution"].set_index("category")
    assert distribution.vendor_count.to_dict() == {"A": 1, "B": 2, "C": 1, "Unclassified": 2}
    assert distribution.loc[["A", "B", "C"], "value_share"].to_dict() == {"A": .8, "B": .16, "C": .04}
    assert distribution.vendor_share.sum() == pytest.approx(1.)
    assert pd.isna(distribution.loc["Unclassified", "value_share"])
    # Missing IDs add +5 while identified nonpositive nets add -5: neither enters the positive denominator.
    assert result["kpi"]["net_obligations"] == 100.


def test_tied_vendor_values_share_class_and_keep_true_running_cumulative():
    raw = pd.DataFrame([transaction(str(index), vendor=f"V{index}", amount=str(amount))
                        for index, amount in enumerate([50, 20, 20, 8, 2])])
    data, _ = clean_transactions(raw)
    expected = {"V0": "A", "V1": "A", "V2": "A", "V3": "B", "V4": "C"}
    vendors = analyze(data)["vendors"].set_index("vendor_id")
    assert vendors.category.to_dict() == expected
    assert vendors.cumulative_share.tolist() == pytest.approx([.5, .7, .9, .98, 1.])
    # Original row ordering and display names cannot decide which tied vendor crosses a boundary.
    reordered = analyze(data.sample(frac=1, random_state=41))["vendors"].set_index("vendor_id")
    pd.testing.assert_frame_equal(vendors, reordered)


@pytest.mark.parametrize("amounts,classes,share", [
    ([99, 1], ["A", "C"], .99),
    ([100], ["A"], 1.),
    ([0, -5], ["Unclassified", "Unclassified"], None),
    ([80, 15, 5], ["A", "B", "C"], .8),
])
def test_extreme_and_exact_threshold_groups(amounts, classes, share):
    data, _ = clean_transactions(pd.DataFrame([
        transaction(str(i), vendor=f"V{i}", amount=str(amount)) for i, amount in enumerate(amounts)
    ]))
    result = analyze(data)
    assert result["vendors"].category.tolist() == classes
    assert result["kpi"]["category_a_share"] == share


def test_decimal_cent_arithmetic_and_invalid_money_are_audited():
    rows = [transaction("a", amount="0.10"), transaction("b", amount="0.20"), transaction("c", amount="-0.30")]
    rows += [transaction("invalid", amount="0.001"), transaction("nan", amount="NaN"), transaction("inf", amount="Infinity")]
    data, audit = clean_transactions(pd.DataFrame(rows))
    assert data.obligation_cents.tolist() == [10, 20, -30]
    assert analyze(data)["kpi"]["net_obligations"] == 0.
    assert analyze(data)["vendors"].category.tolist() == ["Unclassified"]
    assert audit["quarantine_reasons"]["invalid_obligation"] == 3
    assert audit["initial_rows"] == audit["quarantined_rows"] + audit["retained_rows"]


def test_duplicates_are_by_transaction_not_award_or_vendor():
    raw = pd.DataFrame([
        transaction("a"), transaction("a"), transaction("b"), transaction("b", amount="2"),
        transaction("c", award="SHARED"), transaction("d", award="SHARED"), transaction(None),
    ])
    data, audit = clean_transactions(raw)
    assert set(data.transaction_id) == {"a", "c", "d"}
    assert audit["identical_duplicate_rows_removed"] == 1
    assert audit["conflicting_transaction_ids"] == 1
    assert audit["quarantine_reasons"]["conflicting_transaction_id"] == 2
    assert audit["quarantine_reasons"]["missing_transaction_id"] == 1
    assert analyze(data)["kpi"]["total_awards"] == 2
    assert audit["initial_rows"] == audit["identical_duplicate_rows_removed"] + audit["quarantined_rows"] + len(data)


def test_federal_fiscal_year_boundary_and_agency_scope():
    raw = pd.DataFrame([transaction(str(index), date=value) for index, value in enumerate([
        "2023-09-30", "2023-10-01", "2024-09-30", "2024-10-01", "2025-09-30", "2025-10-01", "invalid",
    ])] + [transaction("other", agency="Other Agency")])
    data, audit = clean_transactions(raw)
    assert data.set_index("transaction_id").fiscal_year.to_dict() == {"1": 2024, "2": 2024, "3": 2025, "4": 2025}
    assert audit["quarantine_reasons"]["out_of_fiscal_year_scope"] == 2
    assert audit["quarantine_reasons"]["invalid_action_date"] == 1
    assert audit["quarantine_reasons"]["agency_out_of_scope"] == 1
    wrong_year = pd.DataFrame([{**transaction("wrong"), "fiscal_year": "2025"}])
    data, audit = clean_transactions(wrong_year)
    assert data.empty
    assert audit["quarantine_reasons"]["inconsistent_fiscal_year"] == 1


def test_vendor_identity_is_not_name_and_missing_award_kpi_is_unknown(raw_transactions):
    raw = raw_transactions.copy()
    raw.loc[0, "vendor_name"] = "Earlier display name"
    raw.loc[1, "vendor_name"] = "Later display name"
    raw.loc[2, "vendor_name"] = "Later display name"
    raw.loc[0, "award_id"] = ""
    data, _ = clean_transactions(raw)
    result = analyze(data)
    assert result["kpi"]["unique_vendors"] == 6
    assert result["kpi"]["total_awards"] is None
    assert result["vendors"].set_index("vendor_id").loc["VENDOR-A", "vendor_name"] == "Later display name"
    assert result["vendors"].set_index("vendor_id").loc["VENDOR-B", "vendor_name"] == "Later display name"


def test_filters_recalculate_every_output_and_empty_selection(cleaned):
    data, _ = cleaned
    result = analyze(data, years=[2024], agencies=[NSF], states=["NY"], award_types=["D"])
    assert result["kpi"]["net_obligations"] == 77.
    assert result["kpi"]["transactions"] == 4
    assert result["kpi"]["unique_vendors"] == 2
    assert result["kpi"]["category_a_share"] == 1.
    assert set(result["vendors"].vendor_id) == {"VENDOR-A", "VENDOR-E"}
    assert result["agencies"].agency.tolist() == [NSF]
    assert result["trends"].fiscal_year.tolist() == [2024]
    assert result["states"].state.tolist() == ["NY"]
    assert result["agencies"].net_obligations.sum() == result["trends"].net_obligations.sum() == 77.
    for keyword in ("years", "agencies", "states", "award_types"):
        empty = analyze(data, **{keyword: []})
        assert empty["kpi"]["transactions"] == 0
        assert empty["kpi"]["net_obligations"] == 0.
        assert empty["kpi"]["category_a_share"] is None
        assert all(empty[name].empty for name in ("vendors", "trends", "agencies", "states"))
    assert analyze(data)["kpi"] == analyze(data, years=None, agencies=None, states=None, award_types=None)["kpi"]


def test_raw_official_aliases_required_headers_and_missing_geography(raw_transactions):
    raw = raw_transactions.rename(columns={
        "transaction_id": "contract_transaction_unique_key", "vendor_id": "recipient_uei",
        "vendor_name": "recipient_name", "award_id": "award_unique_key", "agency": "awarding_agency_name",
        "state": "recipient_state_code", "award_type": "contract_award_type", "obligation": "federal_action_obligation",
    })
    raw["contract_award_type"] = raw.contract_award_type.map({"D": "DEFINITIVE CONTRACT", "B": "PURCHASE ORDER"})
    data, audit = clean_transactions(raw)
    assert analyze(data)["kpi"]["net_obligations"] == 100.
    assert audit["column_mapping"]["vendor_id"] == "recipient_uei"
    with pytest.raises(ValueError, match="obligation"):
        clean_transactions(raw.drop(columns="federal_action_obligation"))
    without_geo, audit = clean_transactions(raw.drop(columns="recipient_state_code"))
    assert without_geo.state.eq("").all()
    assert "state" in audit["missing_optional_columns"]
    assert analyze(without_geo)["states"].state.tolist() == [""]


def test_processed_gzip_round_trip_preserves_ids_and_cents(cleaned, tmp_path):
    data, _ = cleaned
    data.loc[0, "transaction_id"] = "000001"
    data.loc[0, "vendor_id"] = "000000000001"
    path = tmp_path / "transactions.csv.gz"
    data.to_csv(path, index=False, compression="gzip")
    loaded = load_data(path)
    assert loaded.loc[0, "transaction_id"] == "000001"
    assert loaded.loc[0, "vendor_id"] == "000000000001"
    assert loaded.obligation_cents.tolist() == data.obligation_cents.tolist()
    assert analyze(loaded)["kpi"] == analyze(data)["kpi"]


def test_empty_frame_with_valid_headers():
    data, audit = clean_transactions(pd.DataFrame(columns=CANONICAL_COLUMNS))
    assert data.empty
    assert audit["initial_rows"] == audit["retained_rows"] == 0
    result = analyze(data)
    assert result["kpi"]["net_obligations"] == 0.
    assert result["kpi"]["unique_vendors"] == result["kpi"]["total_awards"] == result["kpi"]["transactions"] == 0
    assert result["kpi"]["category_a_share"] is None
    assert result["vendors"].empty


def test_official_agency_case_and_whitespace_normalize_without_guessing():
    raw = pd.DataFrame([
        transaction("nsf", agency="  NATIONAL   SCIENCE FOUNDATION  "),
        transaction("nrc", agency="nuclear regulatory commission"),
        transaction("unknown", agency="NSF"),
    ])
    data, audit = clean_transactions(raw)
    assert data.set_index("transaction_id").agency.to_dict() == {"nsf": NSF, "nrc": NRC}
    assert audit["quarantine_reasons"]["agency_out_of_scope"] == 1


def prepare_module():
    spec = importlib.util.spec_from_file_location("prepare_procurement_data", ROOT / "scripts/prepare_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("suffix", [".csv", ".csv.gz", ".json", ".json.gz"])
def test_raw_readers_preserve_row_counts_and_identifiers(raw_transactions, tmp_path, suffix):
    module = prepare_module()
    path = tmp_path / ("raw" + suffix)
    raw = raw_transactions.copy()
    raw.loc[0, "transaction_id"] = "000001"
    if ".csv" in suffix:
        raw.to_csv(path, index=False)
    else:
        opener = gzip.open if suffix.endswith(".gz") else open
        with opener(path, "wt", encoding="utf-8") as handle:
            json.dump(raw.to_dict("records"), handle)
    loaded = module.read_raw(path)
    assert len(loaded) == 9
    assert loaded.loc[0, "transaction_id"] == "000001"
    assert analyze(clean_transactions(loaded)[0])["kpi"]["net_obligations"] == 100.


def test_raw_csv_projects_supported_headers_without_dropping_rows(raw_transactions, tmp_path):
    module = prepare_module()
    raw = raw_transactions.copy()
    raw["unneeded_large_description"] = "NOT USED IN ANALYSIS"
    path = tmp_path / "official-style.csv"
    raw.to_csv(path, index=False)
    loaded = module.read_raw(path)
    assert len(loaded) == len(raw)
    assert "unneeded_large_description" not in loaded.columns
    duplicate_header = tmp_path / "duplicate-headers.csv"
    duplicate_header.write_text("transaction_id,transaction_id,obligation\na,b,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate|Duplicate|berulang|duplikat"):
        module.read_raw(duplicate_header)


@pytest.mark.parametrize("out_of_scope", [False, True])
def test_prepare_cannot_publish_empty_raw_or_fully_quarantined_source(tmp_path, out_of_scope):
    module = prepare_module()
    path = tmp_path / "raw.csv"
    raw = pd.DataFrame([transaction("outside", date="2020-01-01")]) if out_of_scope else pd.DataFrame(columns=CANONICAL_COLUMNS)
    raw.to_csv(path, index=False)
    output = tmp_path / "processed"
    with pytest.raises(ValueError, match="empty|Empty|kosong|0|No.*rows"):
        module.prepare(path, output_dir=output)
    assert not output.exists()


def test_prepare_verifies_checksum_preserves_raw_and_repeats(raw_transactions, tmp_path):
    module = prepare_module()
    raw = tmp_path / "transactions.json.gz"
    with gzip.open(raw, "wt", encoding="utf-8") as handle:
        json.dump(raw_transactions.to_dict("records"), handle)
    original = raw.read_bytes()
    metadata = {
        "raw_sha256": hashlib.sha256(original).hexdigest(), "row_count": 9,
        "source": "SYNTHETIC UNIT FIXTURE ONLY", "source_verification": "synthetic_test_fixture",
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    output = tmp_path / "processed"
    data, audit, result = module.prepare(raw, path, output)
    assert raw.read_bytes() == original
    assert audit["retained_rows"] == 9
    assert json.loads((output / "summary.json").read_text()) == result["kpi"]
    assert json.loads((output / "metadata.json").read_text())["raw_sha256"] == metadata["raw_sha256"]
    assert analyze(load_data(output / "transactions.csv.gz"))["kpi"] == result["kpi"]
    assert module.prepare(raw, path, output)[2]["kpi"] == result["kpi"]
    assert raw.read_bytes() == original
    for altered, message in [({"raw_sha256": "0" * 64}, "Checksum SHA-256"), ({"row_count": 10}, "Jumlah baris")]:
        path.write_text(json.dumps({**metadata, **altered}), encoding="utf-8")
        invalid_output = tmp_path / "invalid"
        with pytest.raises(ValueError, match=message):
            module.prepare(raw, path, invalid_output)
        assert not invalid_output.exists()
    for field in ("raw_row_count", "transaction_count_before", "transaction_count_after"):
        path.write_text(json.dumps({**metadata, field: 10}), encoding="utf-8")
        with pytest.raises(ValueError, match="Jumlah baris"):
            module.prepare(raw, path, tmp_path / "invalid")
    for status in ("failed", "in_progress"):
        path.write_text(json.dumps({**metadata, "status": status}), encoding="utf-8")
        with pytest.raises(ValueError, match="belum lengkap|complete|status|gagal"):
            module.prepare(raw, path, tmp_path / "invalid")


def card_values(app):
    return [value for element in app.markdown
            for value in re.findall(r'<div class="kpi-value(?: gold)?">(.*?)</div>', element.value)]


def test_missing_data_keeps_dashboard_shell_without_fabricating_kpis(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "0")
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(tmp_path / "missing"))
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    pages = ["Overview", "ABC Classification", "Vendor Analysis", "Fiscal-Year Comparison", "Concentration & SQL"]
    assert app.radio[0].options == pages
    for page in pages:
        app.radio[0].set_value(page).run(timeout=30)
        assert not app.exception
        assert not app.get("plotly_chart")
        assert any("official procurement snapshot is not available" in warning.value for warning in app.warning)
        assert card_values(app) == ["—"] * 4


def test_dashboard_all_pages_and_synchronized_global_filters(cleaned, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "0")
    data, audit = cleaned
    data.to_csv(tmp_path / "transactions.csv.gz", index=False, compression="gzip")
    (tmp_path / "quality.json").write_text(json.dumps(audit), encoding="utf-8")
    (tmp_path / "metadata.json").write_text(json.dumps({
        "source": "SYNTHETIC UNIT FIXTURE ONLY", "source_verification": "synthetic_test_fixture",
    }), encoding="utf-8")
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert card_values(app) == ["$100.00", "6", "8", "80.0%"]
    for page in app.radio[0].options:
        app.radio[0].set_value(page).run(timeout=30)
        assert not app.exception
    app.radio[0].set_value("Overview").run(timeout=30)
    app.multiselect[0].set_value([2024])
    app.multiselect[1].set_value([NSF])
    app.multiselect[2].set_value(["NY"])
    app.multiselect[3].set_value(["D"])
    app.run(timeout=30)
    assert not app.exception
    assert card_values(app) == ["$77.00", "2", "3", "100.0%"]
    for page in ("ABC Classification", "Vendor Analysis", "Fiscal-Year Comparison"):
        app.radio[0].set_value(page).run(timeout=30)
        assert not app.exception
        assert card_values(app) == ["$77.00", "2", "3", "100.0%"]
    app.multiselect[2].set_value(["CA"])
    app.run(timeout=30)
    assert not app.exception
    assert card_values(app) == ["$0.00", "0", "0", "—"]
    assert any("No transactions match" in message.value for message in app.info)


@pytest.fixture
def source_panel_bundle(raw_transactions, tmp_path, monkeypatch):
    raw = pd.concat([
        raw_transactions, raw_transactions.iloc[[0]],
        pd.DataFrame([transaction("invalid-money", amount="not an amount")]),
    ], ignore_index=True)
    data, quality = clean_transactions(raw)
    metadata = {
        "source": "SYNTHETIC UNIT FIXTURE ONLY — imported test source",
        "source_verification": "synthetic_test_fixture",
        "retrieval_finished_at": "2026-10-31T09:10:11+00:00",
        "row_count": 11,
        "fixture_notice": "No official-source result is claimed by this test fixture.",
    }
    data.to_csv(tmp_path / "transactions.csv.gz", index=False, compression="gzip")
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "quality.json").write_text(json.dumps(quality), encoding="utf-8")
    monkeypatch.setenv("PROCUREMENT_AUTO_FETCH", "0")
    monkeypatch.setenv("PROCUREMENT_DATA_DIR", str(tmp_path))
    return data, metadata, quality, tmp_path


def test_source_panel_counts_and_exports_match_their_declared_populations(source_panel_bundle, monkeypatch):
    from streamlit.delta_generator import DeltaGenerator
    from streamlit.testing.v1 import AppTest

    data, metadata, quality, _ = source_panel_bundle
    downloads = {}
    original = DeltaGenerator.download_button
    signature = inspect.signature(original)

    def capture(self, *args, **kwargs):
        arguments = signature.bind(self, *args, **kwargs).arguments
        downloads[arguments["file_name"]] = arguments["data"]
        return original(self, *args, **kwargs)
    monkeypatch.setattr(DeltaGenerator, "download_button", capture)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert any("Source provenance is unverified" in item.value for item in app.warning)
    assert len([item for item in app.expander if item.label == "Source & calculations"]) == 1
    assert not app.get("json")
    for page in app.radio[0].options:
        app.radio[0].set_value(page).run(timeout=30)
        assert not app.exception
        panels = [item for item in app.expander if item.label == "Source & calculations"]
        assert len(panels) == 1
        assert panels[0].proto.expanded is False
        assert not app.get("json")
    app.radio[0].set_value("Overview").run(timeout=30)
    app.multiselect[0].set_value([2024])
    app.multiselect[1].set_value([NSF])
    app.multiselect[2].set_value(["NY"])
    app.multiselect[3].set_value(["D"])
    downloads.clear()
    app.run(timeout=30)
    assert not app.exception
    assert card_values(app) == ["$77.00", "2", "3", "100.0%"]
    text = "\n".join(item.value for item in [*app.markdown, *app.caption])
    assert "4 filtered transactions / 9 full-snapshot transactions" in text
    assert "11 raw = 1 duplicates removed + 1 quarantined + 9 retained" in text
    assert metadata["source"] in text
    assert "Snapshot retrieved: " + metadata["retrieval_finished_at"] in text
    assert "2024-01-01 to 2025-01-01 (full prepared snapshot)" in text
    assert "docs/METHODOLOGY.md" in text and "docs/SOURCES.md" in text
    assert "HISTORICAL DATASET" not in text and "Independent portfolio analysis" not in text
    audit = next(item.value for item in app.dataframe if list(item.value.columns) == ["Stage", "Rows"])
    assert audit.set_index("Stage").Rows.to_dict() == {
        "Raw input": "11", "Exact duplicates removed": "1", "Quarantined": "1", "Retained": "9",
    }
    assert set(downloads) == {"procurement_transactions_filtered.csv", "vendor_abc_summary.csv", "metadata.json", "quality.json"}
    selected = data.loc[data.fiscal_year.eq(2024) & data.agency.eq(NSF) & data.state.eq("NY") & data.award_type.eq("D")]
    exported = pd.read_csv(io.BytesIO(downloads["procurement_transactions_filtered.csv"]), keep_default_na=False)
    assert set(exported.transaction_id) == set(selected.transaction_id) == {"t1", "t2", "t6", "t8"}
    assert exported.obligation_cents.sum() == 7700
    vendor_export = pd.read_csv(io.BytesIO(downloads["vendor_abc_summary.csv"]), keep_default_na=False)
    expected_vendors = analyze(data, years=[2024], agencies=[NSF], states=["NY"], award_types=["D"])["vendors"]
    assert vendor_export.set_index("vendor_id").net_obligations.to_dict() == expected_vendors.set_index("vendor_id").net_obligations.to_dict()
    assert vendor_export.set_index("vendor_id").category.to_dict() == {"VENDOR-A": "A", "VENDOR-E": "Unclassified"}
    assert json.loads(downloads["metadata.json"]) == metadata
    assert json.loads(downloads["quality.json"]) == quality

    # Empty filtered exports retain their schema while the full-source audit remains unchanged.
    app.multiselect[2].set_value(["CA"])
    app.run(timeout=30)
    assert not app.exception
    assert pd.read_csv(io.BytesIO(downloads["procurement_transactions_filtered.csv"])).empty
    assert pd.read_csv(io.BytesIO(downloads["vendor_abc_summary.csv"])).empty
    assert json.loads(downloads["quality.json"])["retained_rows"] == 9


def test_source_panel_does_not_invent_missing_retrieval_time_or_cleaning_counts(source_panel_bundle):
    from streamlit.testing.v1 import AppTest

    _, _, _, directory = source_panel_bundle
    (directory / "metadata.json").write_text("{}", encoding="utf-8")
    (directory / "quality.json").write_text("{}", encoding="utf-8")
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    app.radio[0].set_value("Overview").run(timeout=30)
    assert not app.exception
    text = "\n".join(item.value for item in [*app.markdown, *app.caption])
    assert "Source metadata and retrieval time are not available yet" in text
    assert "Cleaning counts are not available until the snapshot is prepared" in text
    assert "Snapshot retrieved:" not in text
    assert "raw =" not in text
    assert not any(list(item.value.columns) == ["Stage", "Rows"] for item in app.dataframe)
    assert any("Source provenance is unverified" in item.value for item in app.warning)


def test_source_verification_is_read_from_metadata_not_assumed_from_dataset_name(source_panel_bundle):
    from streamlit.testing.v1 import AppTest

    _, metadata, _, directory = source_panel_bundle
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert any("Source provenance is unverified" in item.value for item in app.warning)
    # The flag below simulates successful fetch metadata strictly inside a unit fixture.
    metadata["source_verification"] = "official_api_download_count_checked"
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    app.run(timeout=30)
    assert not app.exception
    assert not any("Source provenance is unverified" in item.value for item in app.warning)
    assert metadata["source"] in "\n".join(item.value for item in [*app.markdown, *app.caption])


def test_parquet_and_csv_preserve_identical_analysis(raw_transactions, tmp_path):
    module = prepare_module()
    raw = tmp_path / 'raw.csv'
    raw_transactions.to_csv(raw, index=False)
    output = tmp_path / 'processed'
    module.prepare(raw, output_dir=output)
    metadata = json.loads((output / 'metadata.json').read_text())
    csv = load_data(output / 'transactions.csv.gz')
    parquet = load_data(output / 'transactions.parquet')
    pd.testing.assert_frame_equal(csv, parquet)
    assert analyze(csv)['kpi'] == analyze(parquet)['kpi']
    for filename, key in [('transactions.csv.gz', 'processed_sha256'),
                          ('transactions.parquet', 'parquet_sha256')]:
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == metadata[key]


def test_default_start_does_not_fetch_and_parquet_renders_offline(raw_transactions, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import snapshot_bootstrap
    calls = []
    def no_fetch(*args, **kwargs):
        calls.append(True)
        raise AssertionError('Opening the dashboard must not download data')
    monkeypatch.setattr(snapshot_bootstrap, 'ensure_snapshot', no_fetch)
    monkeypatch.delenv('PROCUREMENT_AUTO_FETCH', raising=False)
    monkeypatch.setenv('PROCUREMENT_DATA_DIR', str(tmp_path / 'processed'))
    app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=30)
    assert not app.exception
    assert not calls
    raw = tmp_path / 'raw.csv'
    raw_transactions.to_csv(raw, index=False)
    prepare_module().prepare(raw, output_dir=tmp_path / 'processed')
    # A Parquet-only deployment still works; CSV remains an optional compatibility format.
    (tmp_path / 'processed' / 'transactions.csv.gz').unlink()
    app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=30)
    assert not app.exception
    assert card_values(app) == ['$100.00', '6', '8', '80.0%']
    assert not calls
    path = tmp_path / 'processed' / 'transactions.parquet'
    path.write_bytes(path.read_bytes() + b'corrupt')
    app.run(timeout=30)
    assert not app.exception
    assert any('checksum' in error.value for error in app.error)


def test_sql_choices_readable_tables_and_pareto_scale(source_panel_bundle):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=30)
    assert not app.exception
    texts = [item.value for item in app.main if item.type in {'markdown', 'subheader'}]
    assert texts.index('Key Findings') < next(i for i, value in enumerate(texts) if 'ABC Pareto Analysis' in value)
    before = card_values(app)
    scale = next(item for item in app.selectbox if item.label == 'Pareto scale')
    scale.set_value('Logarithmic').run(timeout=30)
    assert not app.exception
    assert card_values(app) == before
    for page in ['ABC Classification', 'Vendor Analysis', 'Fiscal-Year Comparison', 'Concentration & SQL']:
        app.radio[0].set_value(page).run(timeout=30)
        assert not app.exception
        for item in app.dataframe:
            assert 'obligation_cents' not in item.value.columns
            assert 'net_obligation_cents' not in item.value.columns
            assert 'missing_vendor_rows' not in item.value.columns
    from src.db import FILES
    for name in FILES:
        # AppTest element handles belong to a specific render. Reacquire the
        # SQL selectbox after each rerun, when mobile pagination can change.
        query = next(item for item in app.selectbox if item.label == 'SQL analysis')
        query.set_value(name).run(timeout=30)
        assert not app.exception
        assert app.dataframe, f'No SQL result table for {name}'
        assert not any(item.language == 'sql' for item in app.code)
    app.radio[0].set_value('Overview').run(timeout=30)
    assert card_values(app) == before
