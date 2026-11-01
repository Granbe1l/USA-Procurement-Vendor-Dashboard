-- Run on cleaned transactions. Amounts are integer cents; missing IDs stay
-- in signed totals but cannot be assigned to a vendor. No parent consolidation.
WITH vendor_net AS (
    SELECT agency, fiscal_year, vendor_id, SUM(obligation_cents) AS net_cents
    FROM transactions WHERE vendor_id <> ''
    GROUP BY agency, fiscal_year, vendor_id
), ranked AS (
    SELECT *, SUM(net_cents) OVER (PARTITION BY agency, fiscal_year) AS denominator,
           COALESCE(SUM(net_cents) OVER (
               PARTITION BY agency, fiscal_year ORDER BY net_cents DESC
               RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ), 0) - net_cents * COUNT(*) OVER (
               PARTITION BY agency, fiscal_year, net_cents
           ) AS value_before_tie
    FROM vendor_net WHERE net_cents > 0
), classified AS (
    SELECT *, CASE WHEN value_before_tie < denominator * 0.80 THEN 'A'
                   WHEN value_before_tie < denominator * 0.95 THEN 'B'
                   ELSE 'C' END AS category
    FROM ranked
), concentration AS (
    SELECT agency, fiscal_year, COUNT(*) AS positive_vendors,
           SUM(CASE WHEN category = 'A' THEN 1 ELSE 0 END) AS category_a_vendors,
           1.0 * SUM(CASE WHEN category = 'A' THEN net_cents ELSE 0 END)
               / MAX(denominator) AS category_a_value_share,
           MAX(1.0 * net_cents / denominator) AS top_vendor_share,
           10000.0 * SUM((1.0 * net_cents / denominator) *
                        (1.0 * net_cents / denominator)) AS hhi
    FROM classified GROUP BY agency, fiscal_year
), scope AS (
    SELECT agency, fiscal_year, COUNT(*) AS transactions,
           SUM(obligation_cents) AS net_obligation_cents,
           SUM(CASE WHEN vendor_id = '' THEN 1 ELSE 0 END) AS missing_vendor_rows
    FROM transactions GROUP BY agency, fiscal_year
)
SELECT scope.*, concentration.positive_vendors, concentration.category_a_vendors,
       concentration.category_a_value_share, concentration.top_vendor_share,
       concentration.hhi
FROM scope LEFT JOIN concentration USING (agency, fiscal_year)
ORDER BY agency, fiscal_year;
