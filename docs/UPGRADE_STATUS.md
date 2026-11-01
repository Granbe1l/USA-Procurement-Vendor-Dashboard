# Upgrade status

Recorded 2026-11-01, Asia/Jakarta. This is a development report, not a claim that the public deployment or source findings have been verified.

## Phase outcomes

| Phase | Outcome and evidence | Outstanding |
| --- | --- | --- |
| 1 — cold start | Automatic download defaults off; local Parquet preferred, CSV compatible; preparation writes both hashes; AppTest verifies offline rendering and corrupt-artifact rejection | Official bundle is missing because source access fails. Instant populated production startup is not established. |
| 2 — SQL | Pinned in-memory DuckDB; standalone queries, bounded caches, serialized connections, SQL page and query expanders | Competition query omitted because its column is not retained; actual raw schema remains unavailable. |
| 3 — parity | SQL/pandas and legacy-SQLite checks pass for synthetic populations, including edge cases and both formats | Parity on the real source cohort awaits the official bundle. |
| 4 — UI | Findings moved under KPIs; case-study explanation collapsed; readable tables, UEI labels, log Pareto, count/value distribution, annual deltas and rank changes | No new browser screenshot; actual source-driven findings and full-data performance remain unverified. |
| 5 — README | Scope, SQL, page features, run/refresh paths, data dictionary, screenshot instructions, personal placeholders | Real query-backed findings and owner screenshots are pending. |
| 6 — hygiene | MIT selected by owner and added; CI matrix 3.12/3.14, badge, ignored secret/db/staging paths | CI passed for code revision ef259e3 on the 3.12/3.14 matrix; public deployment is unverified. About suggestions were not applied to GitHub settings. |
| 7 — interview pack | Fifteen factual study prompts with exact code/query references and owner-answer placeholders | Owner must supply personal answers. |

## Validation

The final local suite passed **95 tests** in 10.23 seconds on Python 3.12.14; `pip check` passed. Peak pytest-process RSS was **323.2 MiB** on synthetic fixtures. No pandas ABC rule changed. Rendering tests execute every page and SQL selector and preserve KPI values when the Pareto scale changes. GitHub Actions [run 41248952375](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41248952375) completed successfully for code revision `ef259e3` on the Python 3.12/3.14 matrix (48 seconds). Source retrieval, official findings, full-data memory/startup and live deployment are unverified. The official findings command exits explicitly when the bundle is missing.

## Files added or changed

Application and dependencies:

- `app.py`: offline default, preferred snapshot/checksum checks, bounded caches, SQL integration, findings hierarchy and display changes.
- `procurement.py`: Parquet loading only; `analyze` and its business rules are unchanged.
- `snapshot_bootstrap.py`: validation/reuse of Parquet-only and dual-format bundles, including each present companion.
- `scripts/prepare_data.py`: equivalent CSV.gz/Parquet output and hashes.
- `scripts/report_findings.py`: evidence-gated Markdown finding generation.
- `requirements.txt`: pinned DuckDB.
- `src/__init__.py`, `src/db.py`, `src/insights.py`, `src/presentation.py`: query execution, findings and display-only helpers.

Queries:

- `sql/00_setup_view.sql`, `01_vendor_totals.sql`, `02_abc_classification.sql`, `03_abc_summary.sql`, `04_concentration_hhi.sql`, `06_fy_comparison.sql`, `06_vendor_rank_changes.sql`, `07_vendor_name_overlap.sql`, and `sql/README.md`.
- The existing `sql/vendor_concentration.sql` is preserved unchanged as the SQLite baseline. There is no invented competition query.

Checks and repository hygiene:

- `tests/test_procurement.py`, `tests/test_bootstrap.py`: extend existing coverage; original checks remain.
- `tests/test_sql_vs_pandas.py`, `tests/test_findings_report.py`: new parity and evidence checks.
- `.github/workflows/tests.yml`, `.gitignore`, `LICENSE`: supported-version CI, local artifact exclusions and owner-selected MIT.

Documentation:

- `README.md`, `data/README.md`, `docs/METHODOLOGY.md`, `docs/SOURCES.md`, `docs/validation.md`.
- `docs/DATA_DICTIONARY.md`, `docs/INTERVIEW_NOTES.md`, `docs/images/README.md`, and this report.
- Existing source/methodology docs, raw pipeline, fixture tests and historical images remain.

## Assumptions and limits

- NSF/NRC and FY2024–2025 remain the existing scope; no extra fields or competition mappings are inferred.
- SQL receives the same filtered transaction population before aggregation. Separate agency and combined scopes are explicit.
- Same normalized names are an approximation only; UEIs remain separate, including in all existing calculations.
- New/dropped UEIs measure presence, not verified supplier churn. The owner must assess contract/mission context before interpreting descriptive differences.
- Current runtime policy does not enable the required USAspending hosts. The previously saved domain additions need application through environment settings before another capture can succeed. Never bypass the proxy or substitute fixture data.

## Every owner placeholder

There are **24 `TODO(me)` entries** across the following files. Each supplies two or three guiding questions; none has been filled with an invented personal claim.

README (four): real agency choice; motivation; lessons/challenges; public LinkedIn/email/portfolio contacts.

Methodology Decisions (five): 80/95 thresholds; signed adjustments; ties/boundaries; agency choice; DuckDB choice.

Interview notes (fifteen): observation versus award; ABC denominator; exact boundaries/ties; negative values/cents; windows versus GROUP BY; HHI interpretation; fiscal-year derivation; obligations versus payments; UEI versus name/parent; approximate name grouping; agency choice/two-year limits; DuckDB tradeoffs; parity validation; snapshot/cold start; future extensions.

Other owner actions:

1. Enable the required `api.usaspending.gov` and `files.usaspending.gov` access in environment settings, or provide a complete independently verified official capture through the supported file workflow.
2. Prepare and validate the official bundle; generate findings with `scripts/report_findings.py` and independently check two or three numbers in the cited queries.
3. Supply `overview.png`, `concentration.png`, and `fiscal-year-comparison.png` under `docs/images/`, following its capture instructions.
4. Review suggested About text/website/topics and apply them manually if desired.
5. Verify Community Cloud deployment; measure full-data memory and populated startup before describing the app as production-ready. Remote CI for the code revision passed; keep checking subsequent changes.
