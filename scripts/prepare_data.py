"""Import a real USAspending contract snapshot into local analysis artifacts."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from procurement import FIELD_ALIASES, OPTIONAL_FIELDS, analyze, clean_transactions


def read_raw(path):
    path = Path(path)
    filename = path.name.lower()
    if filename.endswith((".csv", ".csv.gz")):
        # Inspect the original header before pandas can rename duplicate fields.
        # Keep the full source archive on disk, but only read analysis columns
        # into memory; a USAspending export has hundreds of unrelated fields.
        opener = gzip.open if filename.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), [])
        if len(header) != len(set(header)):
            raise ValueError("CSV memiliki nama kolom duplikat; pemetaan tidak dapat diverifikasi.")
        missing = [target for target, aliases in FIELD_ALIASES.items()
                   if target not in OPTIONAL_FIELDS and not any(alias in header for alias in aliases)]
        if missing:
            raise ValueError("Kolom wajib tidak tersedia: " + ", ".join(missing))
        recognized = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
        projection = [column for column in header if column in recognized]
        return pd.read_csv(path, dtype=str, keep_default_na=False, usecols=projection, encoding="utf-8-sig")
    opener = gzip.open if filename.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("Snapshot JSON harus berupa array transaksi, bukan respons API agregat.")
    return pd.DataFrame(records)


def prepare(raw_path, metadata_path=None, output_dir=BASE_DIR / "data/processed"):
    raw_path, output_dir = Path(raw_path), Path(output_dir)
    with raw_path.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8")) if metadata_path else {}
    supplied_checksum = metadata.get("raw_sha256")
    if metadata.get("status") is not None and metadata["status"] != "complete":
        raise ValueError("Metadata menyatakan pengambilan gagal/belum selesai; snapshot tidak diproses.")
    if supplied_checksum and supplied_checksum != checksum:
        raise ValueError("Checksum SHA-256 tidak cocok; snapshot tidak diproses.")
    # A filename or successful import does not prove government provenance.
    metadata.setdefault("source", "Tidak diverifikasi; metadata sumber tidak disertakan")
    metadata["raw_sha256"] = checksum
    metadata["raw_filename"] = raw_path.name
    raw = read_raw(raw_path)
    count_keys = ["row_count", "raw_row_count", "transaction_count_before", "transaction_count_after"]
    for key in count_keys:
        if metadata.get(key) is not None and int(metadata[key]) != len(raw):
            raise ValueError(f"Jumlah baris snapshot berbeda dari metadata ({key}).")
    verified_capture_metadata = (
        metadata.get("status") == "complete"
        and bool(supplied_checksum)
        and all(metadata.get(key) is not None for key in ["raw_row_count", "transaction_count_before", "transaction_count_after"])
    )
    metadata.setdefault("source_verification", "metadata_capture_complete; checksum_and_counts_match" if verified_capture_metadata else "unverified")
    metadata["imported_row_count"] = len(raw)
    if raw.empty:
        raise ValueError("Snapshot tidak memiliki transaksi (raw=0); tidak ada hasil olahan yang dibuat.")
    clean, quality = clean_transactions(raw)
    if clean.empty:
        counts = ", ".join(f"{reason}={count}" for reason, count in quality["quarantine_reasons"].items() if count)
        raise ValueError(
            f"Tidak ada transaksi valid setelah cleaning (raw={len(raw)}, "
            f"duplicates_removed={quality['identical_duplicate_rows_removed']}, "
            f"quarantined={quality['quarantined_rows']}, retained=0). "
            f"Alasan karantina (dapat tumpang tindih): {counts or 'tidak tersedia'}. "
            "Periksa skema dan cakupan sumber; tidak ada hasil olahan yang dibuat."
        )
    result = analyze(clean)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean.to_csv(output_dir / "transactions.csv.gz", index=False, compression="gzip")
    clean.to_parquet(output_dir / "transactions.parquet", index=False, compression="zstd")
    # Keep the CSV compatibility artifact and bind both formats to this capture.
    for filename, key in [("transactions.csv.gz", "processed_sha256"),
                          ("transactions.parquet", "parquet_sha256")]:
        metadata[key] = hashlib.sha256((output_dir / filename).read_bytes()).hexdigest()
    for filename, content in [("metadata.json", metadata), ("quality.json", quality), ("summary.json", result["kpi"])]:
        (output_dir / filename).write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"retained_rows": len(clean), "kpi": result["kpi"], "source_verification": metadata["source_verification"]}, ensure_ascii=False))
    return clean, quality, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="CSV/JSON transaksi asli, boleh .gz")
    parser.add_argument("--metadata", type=Path, help="Metadata sumber dan checksum dari proses fetch")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "data/processed")
    args = parser.parse_args()
    try:
        prepare(args.raw, args.metadata, args.output_dir)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        parser.exit(1, f"Persiapan data gagal: {exc}\n")


if __name__ == "__main__":
    main()
