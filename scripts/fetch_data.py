#!/usr/bin/env python3
"""Download complete, real NSF/NRC FY2024–25 contract transactions.

USAspending is a live, revisable source. This fetch does not reproduce or claim
equivalence to the unavailable, historical 5,020-row source ZIP.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin, urlsplit
import zipfile

import requests


API_ORIGIN = "https://api.usaspending.gov"
COUNT_URL = f"{API_ORIGIN}/api/v2/search/spending_by_transaction_count/"
DOWNLOAD_URL = f"{API_ORIGIN}/api/v2/download/transactions/"
ALLOWED_HOSTS = frozenset({"api.usaspending.gov", "files.usaspending.gov"})
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
REQUIRED_CSV_COLUMNS = frozenset(
    {"contract_transaction_unique_key", "federal_action_obligation", "action_date", "recipient_name"}
)
REVISION_LIMITATION = (
    "USAspending data can be revised. Counts before and after download and CSV row "
    "counts are checked, but this is not an immutable historical snapshot and is "
    "not verified as the unavailable original 5,020-row ZIP."
)


class FetchError(RuntimeError):
    """The public data fetch could not be completed or validated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_filters() -> dict:
    """Use transaction action dates, contract award types, and awarding agencies."""
    return {
        "award_type_codes": ["A", "B", "C", "D"],
        "time_period": [{"start_date": "2023-10-01", "end_date": "2025-09-30"}],
        "agencies": [
            {"type": "awarding", "tier": "toptier", "name": "National Science Foundation"},
            {"type": "awarding", "tier": "toptier", "name": "Nuclear Regulatory Commission"},
        ],
    }


def validate_source_url(url: str) -> str:
    """Permit only official public HTTPS endpoints, including on redirects."""
    if not isinstance(url, str):
        raise FetchError("USAspending returned a missing or invalid URL")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise FetchError("USAspending returned an invalid URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in url)
    ):
        raise FetchError("Refusing a URL outside the official USAspending HTTPS hosts")
    return url


def public_url(url: str) -> str:
    """Do not save possible signed query parameters in provenance files."""
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


class APIClient:
    """Keep inherited proxy and CA configuration, and verify TLS normally."""

    def __init__(self, session=None):
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"User-Agent": "FederalProcurementDashboard/1.0", "Accept": "application/json"})
        # Session defaults intentionally preserve trust_env=True and verify=True.

    def _request(self, method: str, url: str, *, payload=None, retry=False, stream=False):
        url = validate_source_url(url)
        attempts = 3 if retry else 1
        for attempt in range(attempts):
            response = None
            try:
                response = self.session.request(
                    method, url, json=payload, stream=stream,
                    timeout=(10, 60), allow_redirects=False,
                )
                # Never follow an unvalidated Location automatically. In particular,
                # a download-job POST is never resubmitted to a redirected endpoint.
                if 300 <= response.status_code < 400:
                    if method != "GET":
                        raise FetchError("Unexpected redirect for a USAspending POST; the request was not repeated")
                    for _ in range(5):
                        redirected_url = validate_source_url(urljoin(url, response.headers.get("Location", "")))
                        if redirected_url == url:
                            raise FetchError("USAspending returned an invalid redirect")
                        response.close()
                        url = redirected_url
                        response = self.session.request(
                            "GET", url, stream=stream, timeout=(10, 60), allow_redirects=False,
                        )
                        if not 300 <= response.status_code < 400:
                            break
                    else:
                        raise FetchError("Too many USAspending redirects")
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt + 1 < attempts:
                        response.close()
                        time.sleep(min(2 ** attempt, 4))
                        continue
                if not 200 <= response.status_code < 300:
                    raise FetchError(
                        f"USAspending HTTP {response.status_code} from {urlsplit(url).hostname}; "
                        "check the environment network policy and service availability"
                    )
                return response
            except requests.RequestException as exc:
                if response is not None:
                    response.close()
                if attempt + 1 >= attempts:
                    suffix = "; download-job POST was not retried" if not retry and method == "POST" else ""
                    raise FetchError(f"USAspending connection failed ({type(exc).__name__}){suffix}") from exc
                time.sleep(min(2 ** attempt, 4))
            except Exception:
                if response is not None:
                    response.close()
                raise
        raise FetchError("USAspending request did not complete")

    def json_request(self, method: str, url: str, payload=None, retry=False) -> dict:
        response = self._request(method, url, payload=payload, retry=retry)
        try:
            if len(response.content) > 2 * 1024 * 1024:
                raise FetchError("USAspending JSON response is unexpectedly large")
            try:
                result = response.json()
            except (ValueError, requests.RequestException) as exc:
                raise FetchError("USAspending returned invalid JSON") from exc
            if not isinstance(result, dict):
                raise FetchError("USAspending JSON response must be an object")
            return result
        finally:
            response.close()

    def download(self, url: str, target: Path) -> str:
        response = self._request("GET", url, retry=True, stream=True)
        digest = hashlib.sha256()
        total = 0
        try:
            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
                try:
                    declared_length = int(declared_length)
                except ValueError as exc:
                    raise FetchError("Download has invalid Content-Length") from exc
                if declared_length < 0 or declared_length > MAX_DOWNLOAD_BYTES:
                    raise FetchError("Download exceeds the 100 MiB safety limit")
            with target.open("xb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise FetchError("Download exceeds the 100 MiB safety limit; no truncated dataset will be used")
                    output.write(chunk)
                    digest.update(chunk)
            if not total:
                raise FetchError("USAspending returned an empty download")
            if declared_length is not None and not response.headers.get("Content-Encoding") and total != declared_length:
                raise FetchError("Download length does not match Content-Length")
            return digest.hexdigest()
        except requests.RequestException as exc:
            raise FetchError(f"ZIP streaming failed ({type(exc).__name__}); the partial download is not usable") from exc
        finally:
            response.close()


def get_transaction_count(client: APIClient, filters: dict) -> int:
    result = client.json_request("POST", COUNT_URL, {"filters": filters}, retry=True)
    categories = result.get("results")
    if not isinstance(categories, dict):
        raise FetchError("Transaction count response has no results object")
    count = categories.get("contracts")
    if type(count) is not int or count < 0:
        raise FetchError("Transaction count response has no valid contracts count")
    for category, value in categories.items():
        if type(value) is not int or value < 0:
            raise FetchError("Transaction count response includes an invalid category count")
        if category != "contracts" and value != 0:
            raise FetchError("Contract-only count unexpectedly includes another award category")
    return count


def extract_contract_csv(zip_path: Path, output_dir: Path) -> tuple[Path, int, str]:
    """Select by official transaction headers and copy a basename, never extractall."""
    import io

    try:
        with zipfile.ZipFile(zip_path) as archive:
            candidates = []
            expanded_size = 0
            for member in archive.infolist():
                name = PurePosixPath(member.filename.replace("\\", "/"))
                if name.is_absolute() or ".." in name.parts or (name.parts and ":" in name.parts[0]):
                    raise FetchError("ZIP contains an unsafe archive path")
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise FetchError("ZIP contains an unsupported symbolic link")
                expanded_size += member.file_size
                if expanded_size > MAX_EXTRACTED_BYTES:
                    raise FetchError("ZIP expands beyond the 512 MiB safety limit")
                if member.is_dir() or name.suffix.lower() != ".csv":
                    continue
                with archive.open(member) as source:
                    reader = csv.reader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))
                    header = next(reader, [])
                if REQUIRED_CSV_COLUMNS.issubset(header):
                    candidates.append(member)
            if len(candidates) != 1:
                raise FetchError(f"Expected exactly one contract transaction CSV with official columns; found {len(candidates)}")
            member = candidates[0]
            target = output_dir / PurePosixPath(member.filename.replace("\\", "/")).name
            if target.name in {"download.zip", "metadata.json"}:
                raise FetchError("Unexpected reserved CSV filename")
            digest = hashlib.sha256()
            size = 0
            with archive.open(member) as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_EXTRACTED_BYTES:
                        raise FetchError("CSV exceeds the 512 MiB safety limit")
                    output.write(chunk)
                    digest.update(chunk)
        row_count = 0
        unique_keys = set()
        with target.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
                raise FetchError("Contract CSV has duplicate columns")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise FetchError("Contract CSV contains a malformed row")
                key = row["contract_transaction_unique_key"].strip()
                if not key or key in unique_keys:
                    raise FetchError("Contract CSV contains a missing or duplicate transaction key")
                unique_keys.add(key)
                row_count += 1
        return target, row_count, digest.hexdigest()
    except (zipfile.BadZipFile, UnicodeError, csv.Error, RuntimeError) as exc:
        if isinstance(exc, FetchError):
            raise
        raise FetchError(f"Invalid contract download ({type(exc).__name__})") from exc


def _job_url(value, fallback: str | None = None) -> str:
    if value is None:
        if fallback is None:
            raise FetchError("Download response is missing its file URL")
        return validate_source_url(fallback)
    if not isinstance(value, str) or not value:
        raise FetchError("Download response includes an invalid URL")
    return validate_source_url(urljoin(API_ORIGIN, value))


def wait_for_download(client: APIClient, job: dict, timeout: float) -> tuple[str, str]:
    file_name = job.get("file_name")
    if not isinstance(file_name, str) or not file_name or Path(file_name).name != file_name or "\\" in file_name:
        raise FetchError("Download job response has an invalid file name")
    status_url = _job_url(job.get("status_url"), f"{API_ORIGIN}/api/v2/download/status/?{urlencode({'file_name': file_name})}")
    file_url = _job_url(job.get("file_url"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.json_request("GET", status_url, retry=True)
        state = status.get("status")
        if state == "finished":
            return _job_url(status.get("file_url"), file_url), file_name
        if state == "failed":
            raise FetchError("USAspending reported that the download job failed")
        if state not in {"ready", "running"}:
            raise FetchError("USAspending returned an unknown download job status")
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(3, remaining))
    raise FetchError(f"Download job did not finish within {timeout:g} seconds; it was not resubmitted")


def fetch_dataset(output_dir: Path, timeout: float = 600, client: APIClient | None = None) -> Path:
    client = client if client is not None else APIClient()
    filters = build_filters()
    started = utc_now()
    before = get_transaction_count(client, filters)
    if before == 0:
        raise FetchError("The complete public query returned zero contracts; refusing to create a substitute dataset")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime("usaspending_%Y%m%dT%H%M%SZ_")
    run_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=output_dir))
    metadata_path = run_dir / "metadata.json"
    metadata = {
        "status": "in_progress", "source": "USAspending.gov public API",
        "count_endpoint": COUNT_URL, "download_endpoint": DOWNLOAD_URL,
        "query": {"filters": filters, "file_format": "csv"},
        "retrieval_started_at": started, "transaction_count_before": before,
        "revision_limitation": REVISION_LIMITATION,
    }
    try:
        job = client.json_request("POST", DOWNLOAD_URL, metadata["query"], retry=False)
        file_url, file_name = wait_for_download(client, job, timeout)
        metadata.update({"source_file_url": public_url(file_url), "source_file_name": file_name})
        zip_path = run_dir / "download.zip"
        metadata["zip_sha256"] = client.download(file_url, zip_path)
        csv_path, row_count, csv_sha = extract_contract_csv(zip_path, run_dir)
        metadata.update({"raw_file": csv_path.name, "raw_sha256": csv_sha, "raw_row_count": row_count, "row_count": row_count})
        after = get_transaction_count(client, filters)
        metadata["transaction_count_after"] = after
        if before != after:
            raise FetchError(f"Public count changed during download ({before} to {after}); no complete snapshot can be claimed")
        if row_count != before:
            raise FetchError(f"CSV row count {row_count} differs from the public query count {before}; download rejected")
        metadata["status"] = "complete"
        metadata["source_verification"] = "official_api_download_count_checked"
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["error"] = str(exc) if isinstance(exc, FetchError) else type(exc).__name__
        raise
    finally:
        metadata["retrieval_finished_at"] = utc_now()
        with metadata_path.open("x", encoding="utf-8") as output:
            json.dump(metadata, output, indent=2, sort_keys=True)
            output.write("\n")
    return metadata_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--verify-only", action="store_true", help="Query the real transaction count without downloading or writing files")
    parser.add_argument("--timeout", type=float, default=600, help="Maximum download-job polling time in seconds (default: 600)")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 3600:
        parser.error("--timeout must be between 1 and 3600 seconds")
    try:
        if args.verify_only:
            count = get_transaction_count(APIClient(), build_filters())
            print(json.dumps({"transaction_count": count, "source": COUNT_URL, "filters": build_filters(), "checked_at": utc_now()}, indent=2))
        else:
            metadata_path = fetch_dataset(args.output_dir, args.timeout)
            print(f"Complete public transaction CSV and provenance saved: {metadata_path}")
            print(REVISION_LIMITATION)
    except (FetchError, OSError) as exc:
        print(f"Data fetch failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
