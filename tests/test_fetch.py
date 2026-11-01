"""Mock the official download protocol; no synthetic file enters production data."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fetch_procurement_data", ROOT / "scripts/fetch_data.py")
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


def zip_bytes(rows=3, *, duplicate=False, member="nested/contracts.csv", missing_header=False):
    csv_buffer = io.StringIO(newline="")
    fields = ["contract_transaction_unique_key", "federal_action_obligation", "action_date", "recipient_name"]
    if missing_header:
        fields.remove("federal_action_obligation")
    writer = csv.DictWriter(csv_buffer, fieldnames=fields)
    writer.writeheader()
    for index in range(rows):
        row = {
            "contract_transaction_unique_key": f"test-{0 if duplicate else index}",
            "federal_action_obligation": "-10.01" if index == 1 else "100.00",
            "action_date": "2024-01-01", "recipient_name": "SYNTHETIC TEST VENDOR",
        }
        writer.writerow({key: value for key, value in row.items() if key in fields})
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, csv_buffer.getvalue())
    return target.getvalue()


class Client:
    def __init__(self, archive=None, before=3, after=3):
        self.archive = zip_bytes() if archive is None else archive
        self.counts = iter([before, after])
        self.calls, self.downloads = [], []

    def json_request(self, method, url, payload=None, retry=False):
        self.calls.append((method, url, payload, retry))
        if url == fetch.COUNT_URL:
            return {"results": {"contracts": next(self.counts), "grants": 0, "loans": 0, "direct_payments": 0, "other": 0}}
        if url == fetch.DOWNLOAD_URL:
            return {"file_name": "contracts.zip", "status_url": "/api/v2/download/status/?file_name=contracts.zip",
                    "file_url": "https://files.usaspending.gov/test/contracts.zip?fixture_signature=not-a-secret"}
        return {"status": "finished"}

    def download(self, url, target):
        self.downloads.append(url)
        target.write_bytes(self.archive)
        return hashlib.sha256(self.archive).hexdigest()


def test_complete_download_keeps_all_1257_rows_with_hash_and_scope(tmp_path):
    client = Client(zip_bytes(rows=1257), before=1257, after=1257)
    metadata_path = fetch.fetch_dataset(tmp_path / "raw", timeout=5, client=client)
    metadata = json.loads(metadata_path.read_text())
    assert metadata["status"] == "complete"
    assert metadata["row_count"] == metadata["raw_row_count"] == metadata["transaction_count_before"] == metadata["transaction_count_after"] == 1257
    assert metadata["source_verification"] == "official_api_download_count_checked"
    raw = metadata_path.parent / metadata["raw_file"]
    assert metadata["raw_sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert metadata["zip_sha256"] == hashlib.sha256(client.archive).hexdigest()
    assert raw.name == "contracts.csv"
    assert "fixture_signature" not in metadata["source_file_url"]
    assert metadata["query"]["filters"] == fetch.build_filters()
    assert len([call for call in client.calls if call[1] == fetch.DOWNLOAD_URL]) == 1
    assert [call[3] for call in client.calls if call[1] == fetch.COUNT_URL] == [True, True]
    assert [call[3] for call in client.calls if call[1] == fetch.DOWNLOAD_URL] == [False]
    with raw.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1257
    assert rows[1]["federal_action_obligation"] == "-10.01"
    assert metadata["retrieval_started_at"] <= metadata["retrieval_finished_at"]


def test_filters_are_contract_transactions_by_awarding_agency_and_fiscal_action_dates():
    filters = fetch.build_filters()
    assert filters["award_type_codes"] == ["A", "B", "C", "D"]
    assert filters["time_period"] == [{"start_date": "2023-10-01", "end_date": "2025-09-30"}]
    assert {agency["name"] for agency in filters["agencies"]} == {"National Science Foundation", "Nuclear Regulatory Commission"}
    assert all(agency["type"] == "awarding" and agency["tier"] == "toptier" for agency in filters["agencies"])


@pytest.mark.parametrize("before,after,rows", [(3, 4, 3), (4, 4, 3)])
def test_count_drift_or_incomplete_archive_records_failure(tmp_path, before, after, rows):
    client = Client(zip_bytes(rows), before=before, after=after)
    with pytest.raises(fetch.FetchError, match="count"):
        fetch.fetch_dataset(tmp_path, timeout=5, client=client)
    records = list(tmp_path.glob("*/metadata.json"))
    assert len(records) == 1
    metadata = json.loads(records[0].read_text())
    assert metadata["status"] == "failed"
    assert metadata.get("source_verification") != "official_api_download_count_checked"


def test_zero_count_does_not_create_substitute_data(tmp_path):
    output = tmp_path / "raw"
    client = Client(before=0)
    with pytest.raises(fetch.FetchError, match="zero contracts"):
        fetch.fetch_dataset(output, client=client)
    assert not output.exists()
    assert not client.downloads


def test_each_new_capture_preserves_previous_snapshot(tmp_path):
    first = fetch.fetch_dataset(tmp_path, client=Client())
    original_metadata = first.read_bytes()
    original_raw = (first.parent / "contracts.csv").read_bytes()
    second = fetch.fetch_dataset(tmp_path, client=Client())
    assert first.parent != second.parent
    assert first.read_bytes() == original_metadata
    assert (first.parent / "contracts.csv").read_bytes() == original_raw


@pytest.mark.parametrize("url", [
    "http://files.usaspending.gov/contracts.zip", "https://evil.example/contracts.zip",
    "https://files.usaspending.gov.evil.example/contracts.zip", "https://user:password@files.usaspending.gov/file.zip",
    "https://files.usaspending.gov:444/file.zip", "https://files.usaspending.gov/file.zip#fragment",
])
def test_download_urls_must_remain_official_https(url):
    with pytest.raises(fetch.FetchError):
        fetch.validate_source_url(url)


@pytest.mark.parametrize("member", ["../contracts.csv", "/contracts.csv", "C:/contracts.csv", "..\\contracts.csv"])
def test_zip_archive_paths_cannot_escape_output(tmp_path, member):
    archive = tmp_path / "download.zip"
    archive.write_bytes(zip_bytes(member=member))
    with pytest.raises(fetch.FetchError, match="unsafe archive path"):
        fetch.extract_contract_csv(archive, tmp_path)
    assert not (tmp_path / "contracts.csv").exists()


def test_zip_requires_unique_contract_csv_and_unique_transaction_ids(tmp_path):
    archive = tmp_path / "download.zip"
    archive.write_bytes(zip_bytes(missing_header=True))
    with pytest.raises(fetch.FetchError, match="exactly one"):
        fetch.extract_contract_csv(archive, tmp_path)
    archive.write_bytes(zip_bytes(duplicate=True))
    with pytest.raises(fetch.FetchError, match="duplicate transaction key"):
        fetch.extract_contract_csv(archive, tmp_path)


def test_zip_rejects_symlinks_and_expansion_limit(tmp_path, monkeypatch):
    archive = tmp_path / "download.zip"
    info = zipfile.ZipInfo("contracts.csv")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, "../../outside.csv")
    with pytest.raises(fetch.FetchError, match="symbolic link"):
        fetch.extract_contract_csv(archive, tmp_path)
    archive.write_bytes(zip_bytes())
    monkeypatch.setattr(fetch, "MAX_EXTRACTED_BYTES", 10)
    with pytest.raises(fetch.FetchError, match="512 MiB"):
        fetch.extract_contract_csv(archive, tmp_path)


@pytest.mark.parametrize("results", [{"contracts": True}, {"contracts": -1}, {"contracts": "3"}, {"contracts": 3, "grants": 1}])
def test_invalid_or_noncontract_counts_are_rejected(results):
    class CountOnly:
        def json_request(self, *_args, **_kwargs):
            return {"results": results}
    with pytest.raises(fetch.FetchError):
        fetch.get_transaction_count(CountOnly(), fetch.build_filters())


def test_download_job_post_is_not_retried_on_connection_failure():
    class FailingSession:
        headers = {}
        calls = []
        def request(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            raise requests.ConnectionError("Synthetic test failure")
    session = FailingSession()
    with pytest.raises(fetch.FetchError, match="POST was not retried"):
        fetch.APIClient(session).json_request("POST", fetch.DOWNLOAD_URL, payload={}, retry=False)
    assert len(session.calls) == 1
    assert session.calls[0][1]["allow_redirects"] is False
    assert session.calls[0][1]["timeout"] == (10, 60)
    client = fetch.APIClient()
    assert client.session.verify is True
    assert client.session.trust_env is True
