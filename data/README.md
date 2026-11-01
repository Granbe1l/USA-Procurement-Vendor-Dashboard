# Data files

The dashboard uses a USAspending snapshot of NSF and NRC contract transactions for FY2024–2025. The dashboard loads a prepared local snapshot without a network request. If `processed/` has no complete snapshot, use an explicit load/retry action or the refresh scripts. The loaded retrieval time and cleaning counts appear under **Source & calculations**.

- `raw/`: original archive, CSV, and capture metadata; ignored by Git.
- `processed/transactions.parquet`: preferred typed snapshot (Zstandard compression).
- `processed/transactions.csv.gz`: equivalent CSV compatibility snapshot.
- `processed/metadata.json`: source, query, timestamps, counts, and checksums.
- `processed/quality.json`: cleaning audit.
- `processed/summary.json`: full-snapshot KPIs.

The verified official snapshot is bundled under `processed/`. Prepared files can be included for a fixed deployment snapshot; keep their original archive and metadata for reproduction. [Source documentation](../docs/SOURCES.md).


## Prepared formats and integrity

`prepare_data.py` writes a Zstandard-compressed Parquet snapshot plus the equivalent CSV.gz, then updates `parquet_sha256` and `processed_sha256` in metadata from those exact outputs. The dashboard prefers Parquet and verifies its recorded checksum. CSV-only bundles remain compatible. Keep metadata, quality, summary and transactions from one capture together. Default startup does not submit network requests; loading a missing bundle requires an explicit action or `PROCUREMENT_AUTO_FETCH=1`. Raw archives remain unchanged.

The snapshot was captured on 2026-11-01 UTC; see `processed/metadata.json` for its source and integrity checks. `data/processed-next/` is an ignored staging location for separately prepared refreshes; inspect and promote the whole validated bundle, preserving the prior bundle. Detailed fields and export units are in [the dictionary](../docs/DATA_DICTIONARY.md).
