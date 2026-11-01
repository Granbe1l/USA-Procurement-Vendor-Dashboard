-- Same agency-year population/positive-net denominator as the existing case study.
-- HHI is descriptive (0-10,000), not an assessment of procurement risk.
WITH positive AS (
    SELECT *, SUM(net_cents) OVER (PARTITION BY agency, fiscal_year) AS denominator,
           SUM(net_cents) OVER (PARTITION BY agency, fiscal_year ORDER BY net_cents DESC
             RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             - net_cents * COUNT(*) OVER (PARTITION BY agency, fiscal_year, net_cents) AS value_before_tie,
           ROW_NUMBER() OVER (PARTITION BY agency, fiscal_year ORDER BY net_cents DESC, vendor_id) AS vendor_rank
    FROM vendor_totals WHERE net_cents > 0
), metrics AS (
    SELECT agency, fiscal_year, COUNT(*) AS positive_vendors,
           COUNT(*) FILTER (WHERE value_before_tie * 100 < denominator * 80) AS category_a_vendors,
           SUM(CASE WHEN value_before_tie * 100 < denominator * 80 THEN net_cents ELSE 0 END)
               / MAX(denominator) AS category_a_value_share,
           MAX(net_cents / denominator) AS top_vendor_share,
           SUM(CASE WHEN vendor_rank <= 10 THEN net_cents ELSE 0 END) / MAX(denominator) AS top_10_share,
           10000 * SUM(POWER(net_cents / denominator, 2)) AS hhi
    FROM positive GROUP BY agency, fiscal_year
), signed AS (
    SELECT agency, fiscal_year, COUNT(*) AS transactions,
           SUM(CAST(obligation_cents AS HUGEINT)) AS net_obligation_cents,
           COUNT(*) FILTER (WHERE vendor_id = '') AS missing_vendor_rows
    FROM transactions GROUP BY agency, fiscal_year
)
SELECT signed.*, metrics.positive_vendors, metrics.category_a_vendors,
       metrics.category_a_value_share, metrics.top_vendor_share, metrics.top_10_share, metrics.hhi
FROM signed LEFT JOIN metrics USING (agency, fiscal_year)
ORDER BY agency, fiscal_year
