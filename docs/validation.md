# Validation

Run the automated checks from the repository root:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The suite covers signed obligation totals, vendor and award identities, duplicate handling, fiscal scope, ABC thresholds and ties, filter consistency, source-count and checksum validation, snapshot publication, retry behavior, and dashboard rendering.

Tests use isolated fixtures in temporary directories. Source-download tests mock transport while the preparation and analysis functions execute normally. They do not establish numerical findings for an absent official snapshot.

## Executed checks

An earlier revision passed 70 tests on Python 3.12.14 and 70 tests on Python 3.14.8. Source-panel checks verify full-snapshot cleaning counts, filtered CSV exports, metadata exports, unavailable dates, and consistent source notes on all five pages. Dependency checks found no conflicts with Streamlit 1.52.0. Browser checks at desktop and phone widths found no JavaScript errors or horizontal page overflow.

Live USAspending access and the public Streamlit URL could not be checked from the development workspace because its outbound proxy rejected those destinations. Source totals and public deployment readiness are therefore not inferred from the automated tests. The app must complete an official download, or load a prepared snapshot, before numerical results are available.

## Portfolio revision validation

On 2026-11-01 (Asia/Jakarta), the current cloud checkout passed **72 tests** on Python 3.12.14, including the new SQLite checks for signed adjustments, exact ABC boundaries, tied values crossing a threshold, independent agency/year populations, missing vendor IDs, and undefined HHI for nonpositive vendor populations. Existing Streamlit AppTest coverage executed all five pages and filters with isolated fixtures. `pip check` found no conflicts. GitHub Actions configuration was added; its remote execution has not been observed.

Live-source access was retried through the configured HTTPS proxy and returned a CONNECT 403 for api.usaspending.gov. No official bundle, real-source numeric findings, or updated populated screenshot was created. The existing screenshot is explicitly labelled historical in README. These are outstanding publication prerequisites, not passing checks. No license choice or GitHub About update was made on the owner's behalf.

## DuckDB and display upgrade — 2026-11-01 (Asia/Jakarta)

Final local run: **95 passed in 10.23 seconds**, Python 3.12.14. Total validation process time was 10.74 seconds; peak pytest-process RSS was **323.2 MiB** as reported by Linux child-process resource usage. These measurements use synthetic fixtures, not the absent official cohort, and do not establish full-data production memory or Community Cloud wake-up time. `pip check` found no dependency conflicts. DuckDB 1.4.3 was installed; its Python 3.14 Linux wheel was also downloaded successfully, but the Python 3.14 test matrix has not been run locally.

The original tests remain. Added checks cover Parquet/CSV equivalence, default startup without invoking the download loader, Parquet-only rendering, corrupt checksums/companions, cached file queries, every SQL selection in the UI, formatting without data mutation, duplicate-name labels, log-scale interaction without KPI changes, finding generation, and refusal to publish unverified/explicitly synthetic finding inputs.

DuckDB parity checks compare the unchanged pandas analysis for combined and per-agency populations, filters, recipient identities/names/classes, signed totals, shares and cumulative shares, exact boundaries/ties, nonpositive nets, missing IDs, empty recipient populations, HHI, top-1/top-10 shares and annual totals. The previous SQLite case-study outputs are compared too. No pandas ABC rule was modified. Standalone dependency setup is documented in `sql/README.md`; the file runner executes every query against both CSV.gz and Parquet during tests.

Readiness limits:

- Official access was retried with `scripts/fetch_data.py --verify-only`; it failed with ProxyError. No raw capture, official snapshot, numerical project findings or retrieval date was created.
- `scripts/report_findings.py` was executed against the actual checkout and exited with a missing-metadata error, rather than manufacturing findings.
- Rendering checks use Streamlit AppTest; no new browser/viewport capture or live deployment check was performed. Historical screenshots are preserved and labelled.
- GitHub Actions for code revision `ef259e3` completed successfully in 48 seconds on the configured Python 3.12/3.14 matrix: [run 41248952375](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41248952375). This is observed remote validation, separate from the local 3.12 run. Publication and Community Cloud deployment have not been verified.
- Local Markdown references resolve. No Git candidate exceeds 100 MB and no secret-like `.env`, `secrets.toml`, `.pem` or `.key` path was found in the candidate set. This path check is not an exhaustive secret-content audit.

See `UPGRADE_STATUS.md` for phase status, files and owner tasks.


## Verified official snapshot and final review — 2026-11-01

**Current review-branch evidence supersedes earlier notes above that reported unavailable source access.** Those earlier notes document the state of the project at that time, not the current state.

- Review branch: `fix/official-data`. The verified USAspending capture contains **5,020 transactions**, with **5,020 retained** and **zero quarantined**. The prepared snapshot, metadata, quality audit and SQL-generated findings are committed under `data/processed/`. These are real source records, not test fixtures.
- GitHub Actions code tests passed for commit `f3d00431ef3dad56538de021f3e3a71d215c6a90`: [Tests run 41257292561](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41257292561).
- Official USAspending verification and all-five-page Streamlit AppTest smoke checks passed: [official-data run 41257292518](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41257292518).
- **Not yet verified:** screenshots of the latest review-branch interface with the official dataset; visual checks at desktop/mobile viewport sizes; full-data startup and memory measurements; production Streamlit deployment. Passing AppTest does not substitute for a browser screenshot or prove production readiness.
- **Deployment safety:** the production `main` branch and public Streamlit dashboard have not been updated by this review. Do not represent the public URL as evidence of the review branch's new interface.

Before merging: inspect the review branch in a real browser with the bundled snapshot, capture the three views in `docs/images/README.md`, confirm that all displayed KPI figures agree with the snapshot and SQL output, and obtain owner approval to merge and deploy.


## Final portfolio audit — 2026-11-01

This section is the latest observed evidence. Historical validation notes above describe earlier revisions and **must not be interpreted as the current state**.

### Verified official-data checks

- **Snapshot:** 5,020 official USAspending contract transactions, all retained, zero quarantined, with checksum and source-count verification in `data/processed/metadata.json` and `quality.json`. Snapshot retrieval completed 2026-11-01 UTC. These records are not synthetic test fixtures.
- **Automated tests:** [Tests run 41262449260](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41262449260) passed on commit `c1b2ae6931f09ffa34fb510c6209b8a4248c0fdb`.
- **Official source workflow:** [run 41262449316](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41262449316) passed, including official-source checks and five-page Streamlit AppTest smoke coverage.
- **Visual screenshots:** [run 41262449267](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41262449267) passed. Real-data Overview, Pareto, ABC and fiscal-year screenshot images are committed under `docs/images/` and embedded in README. A passing capture workflow does not prove every possible mobile layout or chart/filter combination is visually correct.
- **Performance and filter audit:** [run 41262449245](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41262449245) passed. Verified 5,020 source rows, 0.025-second Parquet load, 1.483-second initial Streamlit AppTest run and 326.6 MiB peak Linux audit-process RSS. These are **CI measurements**, not Streamlit Community Cloud wake-up benchmarks.
- **UI KPI/filter consistency:** the same performance-audit run passed real-data checks for all data (5,020 rows), NSF FY2025 (948), NRC FY2024 (1,513), recipient state (1,822), award type (2,581), and filter reset (5,020). In these scenarios the rendered KPI values matched pandas and the SQL signed-obligation totals within USD 0.02, and the filtered transaction population matched the source used for CSV export. The tests did not download CSV through a browser or visually inspect every chart after every filter combination.

### Remaining verification and publication boundaries

1. **Public Streamlit deployment:** the review branch has not been merged into `main`; the public dashboard URL must not be treated as a live demonstration of the new verified review-branch version. Test a real production cold start after an explicitly approved deployment.
2. **Final visual/manual checks:** review mobile readability and one browser CSV download on the actual deployed version; confirm the complete chart labels and filter behavior in a browser. Automated tests cover selected cases, not every possible interaction.
3. **Repository profile:** GitHub About, website and topics are suggested in README but have not been verified as applied to repository settings.
4. **Vendor-name consolidation:** UEI is the analysis identity. No unverified parent-company grouping is performed; normalized-name overlap is only an exploratory view.
5. **Owner-controlled statements:** personal interview TODOs remain unanswered and should be completed by the owner, not generated as claimed experience.

**Release gate:** keep PR #1 as a review PR and obtain explicit owner approval before merging or deploying. Do not substitute synthetic data or claim production validation from CI results.
