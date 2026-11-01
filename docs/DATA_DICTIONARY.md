# Data dictionary

Prepared transactions retain only fields supported by the pipeline. Parquet preserves their types; CSV.gz is a compatibility representation. Displays format copies; calculations and CSV downloads retain original names and numeric values.

| Field | Prepared type | Meaning |
| --- | --- | --- |
| transaction_id | string | Unique transaction/modification key |
| vendor_id | string | Recipient UEI; blank is unidentified, never a numeric zero |
| vendor_name | string | Recipient display name; latest nonblank label represents a vendor in summaries |
| award_id | string | Award key; multiple transactions can share an award |
| action_date | ISO date string | Transaction action date, not payment date |
| agency | string | Canonical NSF or NRC awarding agency name |
| state | string | Recipient state, not place of performance; may be blank |
| award_type | string | Contract codes A–D, distinct from ABC categories |
| fiscal_year | int64 | Action-date year plus one for October–December |
| obligation_cents | int64 | Signed amount in USD cents; authoritative aggregation input |
| obligation | float64 | Display/CSV USD amount derived from integer cents |

The DuckDB setup view casts action_date to DATE, derives fiscal_year, and adds recipient_state as an alias of state. Competition and NAICS fields are not retained; no values or mappings are inferred.

## Derived exports

- `category`: A/B/C based on cumulative value before an equal-value group, or Unclassified for nonpositive recipient nets.
- `net_obligations`, `value`: signed USD totals. `net_obligation_cents` is a signed cent total and must be divided by 100 for USD.
- `share`, `value_share`, `category_a_value_share`, `top_vendor_share`, `top_10_share`: fractions, not percentage points. Their denominator is positive-net identified recipient value. Undefined measures remain null in numeric exports.
- `vendor_count`, `vendor_share`: identified recipient count and its fraction of all identified recipients, including nonpositive nets.
- `positive_vendors`, `category_a_vendors`: positive-net recipient count and count assigned A within an agency-year.
- `missing_vendor_rows`: transactions lacking recipient identity; still included in signed totals.
- `hhi`: 10,000 × sum of squared positive-net recipient shares, per agency-year.
- `scope`: agency means a separate agency population; combined aggregates all selected agencies before vendor classification.
- `change_usd`, `change_share`: signed annual difference and difference divided by prior signed total; percentage is undefined when the prior total is zero.
- `new_vendors`, `dropped_vendors`: UEIs present in the current/prior selected year but absent from the other, including zero/negative-net recipients. These are presence measures, not verified supplier churn.
- `previous_rank`, `current_rank`: signed-net recipient ranks with UEI breaking ties. `rank_improvement` = previous minus current; absent recipients have null ranks.
- `normalized_name`, `distinct_ueis`, `vendor_ids`: latest names normalized for whitespace/case and the UEIs sharing that label. No corporate linkage is established.

Source metadata and quality exports describe the full snapshot. Transaction and vendor-summary downloads describe the active filtered population. The concentration export adds top_10_share to the earlier case-study fields; their definitions remain unchanged. Internal cent and missing-ID fields are hidden from display tables but preserved in exports.
