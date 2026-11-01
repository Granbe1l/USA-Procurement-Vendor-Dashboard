# Data sources

## Publication

**USAspending.gov**, published by the U.S. Department of the Treasury, provides the public transaction source for this analysis.

- Website: https://www.usaspending.gov/
- API: https://api.usaspending.gov/
- API documentation: https://api.usaspending.gov/docs/
- Transaction-download contract: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/download/transactions.md
- Transaction-count contract: https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_transaction_count.md

The records are secondary administrative data reported through USAspending. No survey or primary collection is performed by this project.

## Extraction scope

| Item | Selection |
| --- | --- |
| Awarding agencies | National Science Foundation; Nuclear Regulatory Commission |
| Award type codes | A, B, C, D: contracts |
| Action dates | October 1, 2023–September 30, 2025 |
| Fiscal years | 2024 and 2025 |
| Observation unit | Contract transaction or modification |
| Value | Signed federal action obligation, USD |

The download script saves the full query in the snapshot metadata. It uses the complete contract transaction export for these filters rather than an unlabelled sample or the first page of a search result.

## Acquisition and checks

1. Request the contract transaction count.
2. Submit the official CSV download job and wait for its completion.
3. Download the returned archive from the approved official hosts.
4. Check the transaction keys and compare CSV row count with the API counts before and after acquisition.
5. Record the archive and CSV SHA-256 checksums, source URLs, query, and retrieval times.
6. Validate those proofs during preparation; publish a complete processed bundle only after it is nonempty and readable.

Matching counts reduce the chance of an inconsistent capture, but do not prove that source values were immutable during the request. USAspending may revise historical transactions. A later capture can therefore differ from an earlier one with the same filters.

The dashboard shows the actual retrieval time and counts from the snapshot it loaded. Without a loaded snapshot, these values are unavailable. No fixed transaction count or source checksum is asserted in this document.

## Local files

| File | Purpose |
| --- | --- |
| `data/raw/<capture>/download.zip` | Original downloaded archive |
| `data/raw/<capture>/*.csv` | Extracted full source CSV |
| `data/raw/<capture>/metadata.json` | Source query, URLs, capture times, status, counts, and checksums |
| `data/processed/transactions.parquet` | Preferred typed snapshot with Zstandard compression |
| `data/processed/transactions.csv.gz` | Equivalent CSV compatibility snapshot |
| `data/processed/metadata.json` | Provenance carried into the prepared snapshot |
| `data/processed/quality.json` | Cleaning counts, quarantine reasons, and rules |
| `data/processed/summary.json` | Full-snapshot KPI output |

Raw files remain unchanged by cleaning and are ignored by Git. For exact reproduction, keep the raw archive, extracted CSV, metadata, prepared data, and matching code revision together. The dashboard's source-download checks are provenance checks, rather than a separate audit of government reporting accuracy.

The verified official snapshot is included in the current repository under `data/processed/`. It contains 5,020 transactions, with zero quarantined rows, captured on 2026-11-01 UTC. Metadata and quality reports document the counts and checksums. Automated tests use separate temporary fixtures.
