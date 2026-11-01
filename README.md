# Analisis Konsentrasi Vendor NSF & NRC (ABC + HHI)

Dashboard untuk melihat seberapa besar nilai kewajiban kontrak (*contract obligations*) pemerintah Amerika Serikat terkonsentrasi pada vendor tertentu. Analisis menggunakan data **National Science Foundation (NSF)** dan **Nuclear Regulatory Commission (NRC)** untuk **tahun fiskal 2024–2025**. Proyek ini membandingkan kontribusi vendor melalui klasifikasi ABC, indeks konsentrasi HHI, dan perubahan antar-tahun fiskal.

Sumber: [USAspending.gov](https://www.usaspending.gov/) · Tanggal transaksi **1 Oktober 2023–30 September 2025** · Snapshot resmi diambil **1 November 2026 (UTC)**. Data bersifat historis, bukan real-time.

**Python · pandas · DuckDB / SQL · Streamlit · Plotly · pytest**

[Buka dashboard](https://usa-federal-procurement-vendor-dashboard-candy.streamlit.app/) · [Metodologi](docs/METHODOLOGY.md) · [Sumber data](docs/SOURCES.md) · [Kamus data](docs/DATA_DICTIONARY.md) · [Hasil pengujian](docs/validation.md) · [Checklist akhir F1–F20](docs/FINAL_REVIEW.md)

> **Status:** Hasil di bawah sudah diverifikasi pada branch `fix/official-data`. Dashboard publik pada tautan di atas masih menggunakan branch `main` dan belum tentu menampilkan perubahan terbaru.

## Temuan utama

Dari snapshot resmi yang sama dengan data analisis:

- Pada **NSF FY2025**, satu penerima kontrak terbesar menyumbang **44,6%** dari total nilai bersih positif vendor. Sumber perhitungan: [SQL konsentrasi](sql/04_concentration_hhi.sql).
- Pada **FY2025**, indeks HHI NSF sebesar **2.118**, sedangkan NRC **467**. Perbedaan ini menunjukkan distribusi nilai kontrak pada NSF lebih terkonsentrasi dalam cakupan data yang dipilih; bukan penilaian kinerja kedua instansi. Sumber: [SQL konsentrasi](sql/04_concentration_hhi.sql).
- Total kewajiban kontrak bersih bertanda untuk kedua instansi **turun USD 74.140.345,72 (7,7%)** dari FY2024 ke FY2025. Sumber: [SQL perbandingan tahun fiskal](sql/06_fy_comparison.sql).
- Dari **737 vendor teridentifikasi**, **60 vendor kategori A** (8,1%) mencakup **80,2% nilai bersih positif vendor**. Sumber: [SQL ringkasan ABC](sql/03_abc_summary.sql).

Angka ini menggambarkan konsentrasi nilai kontrak dalam data terpilih. Angka tersebut tidak otomatis membuktikan risiko pemasok, efisiensi pengadaan, atau tingkat persaingan.

## Tampilan dashboard

Screenshot asli dari snapshot USAspending terverifikasi pada branch `fix/official-data`. Gambar Overview menampilkan bagian atas dashboard; grafik Pareto, ABC, dan perbandingan tahun fiskal ditampilkan terpisah agar tidak terpotong.

![Ringkasan dashboard dengan data resmi](docs/images/overview.png)

**Grafik Pareto — kontribusi nilai vendor**

![Grafik Pareto berdasarkan data resmi](docs/images/pareto.png)

**Klasifikasi ABC**

![Distribusi vendor dan nilai kumulatif ABC](docs/images/abc.png)

**Perbandingan tahun fiskal**

![Perbandingan NSF dan NRC FY2024–FY2025](docs/images/fiscal-year-comparison.png)

## Fitur

| Menu | Isi |
| --- | --- |
| Overview | KPI, temuan utama, grafik Pareto, distribusi ABC, dan ringkasan instansi |
| ABC Classification | Pengelompokan vendor berdasarkan kontribusi nilai bersih positif dan batas kumulatif ABC |
| Vendor Analysis | Peringkat vendor, identitas UEI, dan rincian transaksi terpilih |
| Fiscal-Year Comparison | Perubahan nilai FY2024–FY2025, perbandingan instansi, vendor baru/tidak muncul lagi, dan perubahan peringkat |
| Concentration & SQL | Analisis HHI, kontribusi vendor terbesar, dan query SQL yang mendasari hasil |

Filter instansi, tahun fiskal, negara bagian penerima, dan jenis kontrak diterapkan sebelum penghitungan. Bagian **Source & calculations** menyediakan sumber, penjelasan perhitungan, serta unduhan data.

## Data

Data berasal dari **USAspending.gov**, yang menyediakan informasi transaksi pengadaan pemerintah Amerika Serikat. Snapshot terverifikasi memuat **5.020 transaksi**, seluruhnya dipertahankan setelah pemeriksaan, dengan **0 baris dikarantina**. Terdapat **2.043 award unik** dan **737 identitas vendor unik** pada cakupan tersebut.

Satu baris merupakan transaksi atau perubahan kontrak, bukan satu kontrak utuh. Nilai negatif dan nol tetap disimpan karena dapat mencerminkan penyesuaian kewajiban kontrak. Identitas vendor menggunakan **UEI**, sehingga nama perusahaan yang terlihat sama tidak otomatis digabungkan.

### Batas penggunaan

- Hanya dua instansi dan dua tahun fiskal; hasilnya bukan gambaran seluruh pengadaan federal Amerika Serikat.
- *Obligations* adalah komitmen anggaran, bukan pembayaran tunai.
- Kategori ABC dan HHI mengukur konsentrasi nilai, bukan kualitas vendor atau bukti risiko.
- UEI yang berbeda tidak digabungkan berdasarkan nama karena hubungan kepemilikan perusahaan belum diverifikasi.
- Data USAspending dapat direvisi; hasil ini berlaku untuk snapshot yang tercatat.

Rumus, penanganan nilai negatif, aturan vendor bernilai sama, dan bukti pemeriksaan sumber dijelaskan pada [metodologi](docs/METHODOLOGY.md), [kamus data](docs/DATA_DICTIONARY.md), dan [validasi](docs/validation.md).

## Tentang proyek

### Alasan memilih NSF dan NRC

Saya memilih NSF dan NRC karena keduanya memiliki bidang kerja yang berbeda. NSF berfokus pada pendanaan penelitian dan ilmu pengetahuan, sedangkan NRC berkaitan dengan pengawasan kegiatan nuklir.

Menurut saya, perbedaan tersebut menarik untuk dijadikan bahan perbandingan distribusi nilai kontrak. Namun, saya tidak menggunakan hasilnya untuk menentukan instansi mana yang lebih baik, karena kebutuhan dan karakteristik pengadaan masing-masing instansi tentu berbeda.



## Analisis SQL

[sql/README.md](sql/README.md) explains standalone execution and dependency order. [src/db.py](src/db.py) runs pinned DuckDB in memory, with bounded caches and serialized shared-view updates. There is no external database service, runtime database file, disk spill or extension download. DuckDB's working-memory limit is 256 MB; the full-data CI audit measured 326.6 MiB peak process RSS (including pandas, SQL and Streamlit AppTest), not a production Cloud memory limit.

| Query | Output |
| --- | --- |
| `00_setup_view.sql` | Typed snapshot view, fiscal year derived from action date |
| `01_vendor_totals.sql` | Signed recipient totals per agency and fiscal year |
| `02_abc_classification.sql` | ABC for each agency and for all selected agencies combined |
| `03_abc_summary.sql` | Class count, share of identified recipients, value and positive-value share |
| `04_concentration_hhi.sql` | Agency-year HHI, top-1/top-10 shares, Category A metrics |
| `06_fy_comparison.sql` | Annual signed totals, LAG changes, new/dropped UEIs |
| `06_vendor_rank_changes.sql` | Current/previous top-10 ranks and signed values |
| `07_vendor_name_overlap.sql` | Latest normalized names shared by different UEIs |

Competition and NAICS are not retained in the current cleaned schema, so `05_competition.sql` is not created. No source fields or competition mappings are invented.

[SQL-versus-pandas tests](tests/test_sql_vs_pandas.py) compare identified recipients, names, classifications, shares, totals, HHI and fiscal-year values. Tests include exact boundaries, ties, negative adjustments, missing IDs, nonpositive nets, combined/agency scopes, filters and both snapshot formats. The existing pandas calculation remains the reference. [The legacy SQLite query](sql/vendor_concentration.sql) is retained and checked for case-study compatibility.

## Run locally

Use Python 3.12 or 3.14. Start from the repository root to load the Streamlit theme.

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m streamlit run app.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Production installation only needs `requirements.txt`. `requirements-dev.txt` adds pytest. CI runs dependency checks and pytest on pushes and pull requests for Python 3.12 and 3.14; local and remote results are recorded separately in [validation](docs/validation.md).

## Local snapshot and optional API refresh

The app opens without an automatic download. It prefers `data/processed/transactions.parquet` and falls back to `transactions.csv.gz`. Without a bundle it shows an explicit empty state and a load/retry button. **On the `fix/official-data` review branch, the official verified bundle is committed and loaded locally without runtime API calls.** On `main`, the bundle is not yet deployed; never substitute fixture data.

The pipeline writes both formats from the same cleaned frame, plus `metadata.json`, `quality.json` and `summary.json`. Metadata binds each processed format to its SHA-256 checksum. The app checks the selected format against its recorded checksum; the fetch/bootstrap path additionally checks official counts and publishes a complete nonempty bundle atomically. Older CSV bundles remain supported.

Refresh from the public API separately from opening the dashboard:

```bash
.venv/bin/python scripts/fetch_data.py
.venv/bin/python scripts/prepare_data.py --raw "PATH_FROM_FETCH_OUTPUT.csv" --metadata "PATH_FROM_FETCH_OUTPUT/metadata.json" --output-dir data/processed-next
```

On PowerShell use `.\.venv\Scripts\python.exe` with the same script arguments. Use the actual raw CSV and metadata paths printed by the fetch command. Check the complete staged bundle, preserve the current bundle, then deploy the validated replacement as `data/processed/` together; never update only one companion file. The manual dashboard load path also stages and promotes validated output while preserving previous files.

The fetch requests the contract count, submits a CSV download job, polls for completion, downloads from approved official HTTPS hosts, validates archive paths and transaction keys, then matches CSV rows against counts before/after capture. It records URLs, query, retrieval timestamps and SHA-256 proofs. The default polling budget is 600 seconds, beyond other request/processing time; actual download timing varies by source response. Set `PROCUREMENT_AUTO_FETCH=1` only to opt into first-run loading. Later filters/navigation reuse local data; failed initialization is cached until explicit retry.

Raw archives remain unchanged under ignored `data/raw/`. Keep the raw archive, extracted CSV, capture metadata, processed bundle and code revision together for reproduction. For a fixed deployment bundle, keep each Git file well below 100 MB. Review-branch snapshot retrieval date: **2026-11-01 UTC**.

## Data & methodology

Source: [USAspending API](https://api.usaspending.gov/), U.S. Department of the Treasury. The action-date range is October 1, 2023–September 30, 2025, restricted to NSF/NRC awarding agencies and contract instrument codes A–D. One row is a transaction/modification, not an entire award. Recipient state is vendor location, not place of performance.

The pipeline maps explicit headers, removes exact duplicate transactions and quarantines every conflicting copy of an ID. It validates dates, amounts, agency, contract type and fiscal scope. Valid negative and zero obligations remain; amounts finer than a cent are rejected. Agency case/spacing variants are normalized only for exact selected names. Audit reconciliation is **raw rows = exact duplicates removed + quarantined rows + retained rows**. Quarantine reasons can overlap and must not be summed; empty or fully quarantined inputs cannot become a snapshot.

Recipient UEI identifies a vendor. Missing IDs remain in signed totals but are excluded from vendor counts/ABC. Missing names fall back to UEI; summary labels use the latest nonblank name, with deterministic lexical ties. Award count is distinct from transaction count and appears only when award identifiers are complete; otherwise the KPI uses transaction count.

Fiscal year is derived from action date: October–December belongs to the next FY. Signed integer cents are the aggregation input; USD is the display unit. Vendor ABC eligibility uses positive **net** value after all signed adjustments:

| Class | Cumulative share before the entire equal-value group |
| --- | --- |
| A | Below 80% |
| B | At least 80%, below 95% |
| C | At least 95% |
| Unclassified | Recipient net value is zero or negative |

Crossing groups stay together, so class shares need not equal nominal boundaries. Vendor ID breaks display-order ties, not classification ties. The ABC denominator sums all positive-net identified vendor values and may differ from signed obligations. Vendor-count shares include Unclassified; value shares use the positive-net denominator. Pareto may show only leading vendors but retains the full eligible denominator and 80%/95% reference lines.

HHI is 10,000 × the sum of squared positive-net recipient shares. No positive-net recipients means undefined HHI/shares, not zero concentration. Same-name UEIs remain separate; the overlap query is explicitly an approximation and does not establish a corporate relationship.

Agency, FY, state and award-type filters apply before aggregation; every page uses that population. ABC can change with filters. Source coverage/cleaning counts always describe the full snapshot, whereas transaction/vendor exports describe the active selection. Missing dates and counts stay unavailable instead of becoming inferred values or zeros.

Displays use readable labels, currency, percentages and em dashes for unavailable values. Downloads retain numeric values and machine-friendly fields, including internal cents; see the [data dictionary](docs/DATA_DICTIONARY.md). **Source & calculations** offers filtered transactions/vendor summaries and full-snapshot metadata/quality exports; Overview also exports agency-year concentration.

Detailed references: [Methodology](docs/METHODOLOGY.md) · [Sources](docs/SOURCES.md) · [Validation](docs/validation.md) · [Interview notes](docs/INTERVIEW_NOTES.md).

## Limitations

- Two agencies and two fiscal years do not represent all federal procurement or establish a long-term trend. Different missions, modifications and changing transaction populations can explain differences.
- Obligations are commitments, not cash payments or contract ceilings.
- UEIs are not consolidated to corporate parents; corporate-group concentration may be understated. Name overlap alone does not establish common ownership.
- ABC/HHI describe obligation-value concentration, not recipient quality, efficiency, performance or proven supply risk; this is not an antitrust market definition.
- USAspending records can be revised. Count matching reduces capture inconsistency but does not make the source immutable. Official-source results, populated screenshots and CI-based full-data startup/memory measurements are available on the review branch. Production Streamlit Cloud cold-start performance remains unverified.

## Deployment, license and repository profile

For Streamlit Community Cloud, select the repository branch and `app.py`, with Python 3.12 or 3.14. A validated bundled snapshot avoids source downloads on opening. Explicit refresh needs `api.usaspending.gov` and `files.usaspending.gov`; no private API credentials are required.

Code is under the [MIT license](LICENSE), as selected by the owner. USAspending data remains attributed to its publisher; the code license is not a separate grant for third-party content.

Usulan deskripsi GitHub About (belum diterapkan pada pengaturan repository): **NSF & NRC vendor concentration, FY2024–2025: auditable ABC, HHI and fiscal-year comparisons with Python, DuckDB SQL and Streamlit.** Website: the dashboard URL above. Suggested topics: `streamlit`, `duckdb`, `sql`, `procurement`, `usaspending`, `data-analysis`, `pareto`, `hhi`.

## Contact

Project maintainer: **Candy**. Use the GitHub repository's profile and issue tracker for project-related questions. Personal email, LinkedIn, and portfolio links will be added only after the owner confirms which details should be public.
