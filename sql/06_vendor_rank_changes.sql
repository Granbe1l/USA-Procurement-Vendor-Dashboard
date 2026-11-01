-- Supplement to 06_fy_comparison: rank signed vendor nets in adjacent selected FYs.
-- A missing rank is absence from that year, not zero obligations or last place.
WITH totals AS (
    SELECT CASE WHEN GROUPING(agency) = 1 THEN 'combined' ELSE 'agency' END AS scope,
           agency, fiscal_year, vendor_id, SUM(CAST(obligation_cents AS HUGEINT)) AS net_cents
    FROM transactions WHERE vendor_id <> ''
    GROUP BY GROUPING SETS ((agency, fiscal_year, vendor_id), (fiscal_year, vendor_id))
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY scope, agency, fiscal_year
        ORDER BY net_cents DESC, vendor_id) AS vendor_rank FROM totals
), years AS (
    SELECT DISTINCT fiscal_year FROM transactions
), pairs AS (
    SELECT fiscal_year, LAG(fiscal_year) OVER (ORDER BY fiscal_year) AS previous_year FROM years
), identities AS (
    SELECT DISTINCT scope, agency, vendor_id FROM ranked
)
SELECT i.scope, i.agency, y.fiscal_year, y.previous_year, i.vendor_id,
       old.vendor_rank AS previous_rank, now.vendor_rank AS current_rank,
       old.vendor_rank - now.vendor_rank AS rank_improvement,
       old.net_cents / 100.0 AS previous_net_obligations,
       now.net_cents / 100.0 AS current_net_obligations
FROM identities i CROSS JOIN pairs y
LEFT JOIN ranked old ON old.scope = i.scope AND old.agency IS NOT DISTINCT FROM i.agency
 AND old.vendor_id = i.vendor_id AND old.fiscal_year = y.previous_year
LEFT JOIN ranked now ON now.scope = i.scope AND now.agency IS NOT DISTINCT FROM i.agency
 AND now.vendor_id = i.vendor_id AND now.fiscal_year = y.fiscal_year
WHERE y.previous_year IS NOT NULL AND (old.vendor_rank <= 10 OR now.vendor_rank <= 10)
ORDER BY i.scope, i.agency, y.fiscal_year, now.vendor_rank NULLS LAST, old.vendor_rank
