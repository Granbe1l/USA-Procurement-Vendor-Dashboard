# Methodology

## Purpose and observation unit

This analysis examines vendor concentration in NSF and NRC contract obligations for FY2024–2025. One observation is a contract transaction identified by `contract_transaction_unique_key`. Multiple modifications of one award are separate observations.

Vendor identity comes from `recipient_uei`. Names serve as display labels. An award identifier links related transactions; the award count is distinct from the transaction count.

## Scope and fiscal year

Included action dates are October 1, 2023 through September 30, 2025. The federal fiscal year runs from October 1 to September 30 of the named year:

- FY2024: October 1, 2023–September 30, 2024.
- FY2025: October 1, 2024–September 30, 2025.

Fiscal year is derived from each transaction's action date. Source award types A, B, C, and D describe contract instruments; they are separate from the calculated vendor ABC groups.

## Cleaning

1. Check required source headers and retain their explicit mappings. Only analysis columns are read into memory; the full source CSV remains archived locally.
2. Remove exact duplicate transactions. Quarantine all conflicting copies of a transaction identifier.
3. Validate the identifier, date, amount, agency, award type, and fiscal-year scope. Agency capitalization and repeated spaces are normalized only when they match one of the two selected agency names.
4. Keep valid negative and zero obligations. Currency values are aggregated in integer cents; amounts finer than one cent are rejected rather than rounded silently.
5. Retain rows with missing vendor IDs in the signed total, but exclude them from vendor counts and ABC groups. If a vendor name is missing, use its valid ID as the display label.
6. Show distinct awards only when award identifiers are complete in the selected rows. Otherwise show the transaction count.

The cleaning audit reconciles:

```text
Raw rows = exact duplicates removed + quarantined rows + retained rows
```

Quarantine reasons can overlap, so their individual counts should not be added together. Quarantined records remain traceable in the original source file. Empty or fully quarantined input does not produce an analytical snapshot.

## Net obligations

For the selected transaction population, total net obligations are the sum of signed `federal_action_obligation` values. Vendor net obligations are the same sum grouped by valid vendor ID.

```text
Vendor net value = sum of that vendor's signed obligations
Total net obligations = sum of all selected signed obligations
```

A negative transaction is an adjustment or deobligation in the source records. It is not converted to an absolute value. The measure is an obligation commitment, rather than a cash payment or contract ceiling.

## ABC and Pareto

Only vendors with positive net value enter the ABC denominator:

```text
ABC denominator = sum of positive-net identified vendor values
Vendor share = vendor net value / ABC denominator
Cumulative share = running sum of vendor shares, largest value first
```

Equal-value vendors form a group. The group receives its class using the cumulative share **before** the group is added:

| Group | Prior cumulative share |
| --- | --- |
| A | Below 80% |
| B | At least 80%, below 95% |
| C | At least 95% |

The entire group stays together when it crosses a threshold. Individual cumulative shares still follow the displayed vendor order, with vendor ID breaking ties for a reproducible display. The method does not assume that exactly 20% of vendors account for 80% of value.

Zero- and negative-net vendors are **Unclassified** and remain visible in the vendor table. Their balances and rows without vendor IDs remain in the signed total-obligations KPI. Consequently, the ABC denominator can differ from that total.

## Reading the KPIs and charts

| Metric | Definition |
| --- | --- |
| Net obligations | Sum of all selected signed transaction values |
| Unique vendors | Distinct nonblank vendor IDs, including nonpositive-net vendors |
| Unique awards | Distinct award IDs, only if all selected rows contain an ID |
| Transactions | Retained row count; replaces the award KPI when award IDs are incomplete |
| Category A value share | Positive value assigned to A divided by the ABC denominator |
| Vendor distribution | Vendor count in each group divided by all identified vendors, including Unclassified |

Overview Pareto may show only the largest vendors. Its cumulative denominator always includes every ABC-eligible vendor in the selected population, including those outside the displayed subset. Vendor-count percentages and value percentages answer different questions.

The two fiscal-year totals provide a comparison within this extraction scope. Two annual points do not establish a detailed time-series pattern. Recipient state refers to vendor location when supplied, rather than place of performance.

## Filters and exports

Agency, fiscal year, recipient state, and award type filters select transactions before vendor aggregation. Every page uses those same selections. ABC membership is recalculated, so a vendor's group can differ between selections.

Source coverage and cleaning counts describe the full snapshot. The current-filter count and downloaded analysis tables describe the selected rows. A missing value is not converted into a measured zero. An em dash means the relevant metric is unavailable.

## Interpretation

ABC measures concentration of obligation value. It does not measure vendor quality, efficiency, or risk, and does not explain why a vendor or agency has a particular total. Source records can be revised. The scope is NSF and NRC contract transactions in the stated period, rather than all federal procurement.


## Complementary SQL concentration analysis

The active Overview runs `sql/04_concentration_hhi.sql` through in-memory DuckDB on the same filtered cleaned transactions. The legacy `sql/vendor_concentration.sql` SQLite query is retained for compatibility testing, not used to power the current Overview. Within each agency and fiscal year, sum signed integer cents by nonempty recipient UEI. Only positive-net vendors enter shares and HHI. HHI = 10,000 × Σ(vendor net / positive-net denominator)²; a single positive-net vendor gives 10,000. No positive-net vendors means undefined shares and HHI, not zero concentration. ABC uses cumulative value before the entire equal-value group, consistent with the pandas implementation. Signed totals and missing-ID transaction counts remain visible separately.

Recipient UEIs are not consolidated to corporate parents. This can understate group-level concentration. HHI describes obligations among the selected recipients, not a defined economic market or an assessment of performance. Compare agency-year shares with mission and contract context; two annual observations do not establish a trend.

## DuckDB parity and presentation decisions

The SQL files in `sql/` add in-memory DuckDB analysis without replacing the pandas ABC function. `02_abc_classification.sql` returns separate `scope='agency'` and `scope='combined'` populations. It uses integer-cent comparisons against 80/95 rather than rounded decimal boundaries and computes cumulative value before the whole equal-value group. Display cumulative positions still advance in deterministic recipient-ID order. `04_concentration_hhi.sql` retains the earlier agency-year case-study definitions and adds top-10 share; the old SQLite query remains for compatibility tests.

Annual changes in `06_fy_comparison.sql` use signed obligations. Relative change is undefined for a zero prior total. New/dropped recipients measure UEI presence, including nonpositive nets, not verified supplier churn. `06_vendor_rank_changes.sql` compares signed-net ranks in either year's top 10, with UEI breaking ties. Whitespace/case-normalized name overlap (`07`) is reported separately and never merges the calculation population.

`src/presentation.py` formats copies only. Currency is converted from cents once where required, fractions become percentages, and undefined values display an em dash. Machine-friendly exports retain their names, numeric values and missingness. The Pareto logarithmic option changes only the bar scale; the denominator, reference lines and classes remain the same.

## Design choices to discuss

The rules above are implemented facts. These are open questions for the project author to discuss rather than claims of personal experience.

- **Threshold rationale:** Why use 80% and 95% here? What alternative would I compare? What does this choice help a reader see?
- **Signed adjustments:** Why keep negative values? What would absolute values distort? How would I investigate an unexpected deobligation?
- **Ties and boundaries:** Why keep tied values together? What happens when a group crosses 80%? How would I explain a Category A share above 80%?
- **Agency selection:** Why NSF and NRC? What comparison is useful despite different missions? What scope would I choose next?
- **DuckDB selection:** Why use an in-memory analytical engine here? What does the SQL layer demonstrate beyond pandas? When would another storage/query design be preferable?
