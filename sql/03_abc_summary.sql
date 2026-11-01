-- abc_classification is the result of 02. Counts include Unclassified vendors.
-- Unclassified value share is undefined, not zero or a share of signed totals.
WITH populations AS (
    SELECT DISTINCT 'agency' AS scope, agency FROM transactions
    UNION ALL SELECT 'combined' AS scope, NULL::VARCHAR AS agency
),
classes(category) AS (VALUES ('A'), ('B'), ('C'), ('Unclassified')),
stats AS (
    SELECT scope, agency, COUNT(*) AS vendor_count,
           SUM(CASE WHEN net_cents > 0 THEN net_cents ELSE 0 END) AS denominator
    FROM abc_classification GROUP BY scope, agency
)
SELECT p.scope, p.agency, c.category, COUNT(a.vendor_id) AS vendor_count,
       COUNT(a.vendor_id) * 1.0 / NULLIF(s.vendor_count, 0) AS vendor_share,
       COALESCE(SUM(a.net_cents), 0) / 100.0 AS value,
       CASE WHEN c.category <> 'Unclassified' THEN
            COALESCE(SUM(a.net_cents), 0) * 1.0 / NULLIF(s.denominator, 0) END AS value_share
FROM populations p CROSS JOIN classes c
LEFT JOIN stats s ON s.scope = p.scope AND s.agency IS NOT DISTINCT FROM p.agency
LEFT JOIN abc_classification a ON a.scope = p.scope
 AND a.agency IS NOT DISTINCT FROM p.agency AND a.category = c.category
GROUP BY p.scope, p.agency, c.category, s.vendor_count, s.denominator
ORDER BY p.scope, p.agency, CASE c.category WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 ELSE 4 END
