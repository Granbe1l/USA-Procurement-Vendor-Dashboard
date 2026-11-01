-- Overall plus agency-level signed totals. Blank IDs are included in money totals.
-- New/dropped counts use identified recipients with ANY net value, matching pandas.
WITH annual AS (
    SELECT CASE WHEN GROUPING(agency) = 1 THEN 'combined' ELSE 'agency' END AS scope,
           agency, fiscal_year, SUM(CAST(obligation_cents AS HUGEINT)) AS net_cents
    FROM transactions GROUP BY GROUPING SETS ((agency, fiscal_year), (fiscal_year))
), previous AS (
    SELECT *, LAG(net_cents) OVER (PARTITION BY scope, agency ORDER BY fiscal_year) AS previous_cents,
              LAG(fiscal_year) OVER (PARTITION BY scope, agency ORDER BY fiscal_year) AS previous_year
    FROM annual
), recipients AS (
    SELECT DISTINCT CASE WHEN GROUPING(agency) = 1 THEN 'combined' ELSE 'agency' END AS scope,
           agency, fiscal_year, vendor_id
    FROM transactions WHERE vendor_id <> ''
    GROUP BY GROUPING SETS ((agency, fiscal_year, vendor_id), (fiscal_year, vendor_id))
)
SELECT p.scope, p.agency, p.fiscal_year, p.previous_year, p.net_cents / 100.0 AS net_obligations,
       (p.net_cents - p.previous_cents) / 100.0 AS change_usd,
       (p.net_cents - p.previous_cents) * 1.0 / NULLIF(p.previous_cents, 0) AS change_share,
       CASE WHEN p.previous_year IS NOT NULL THEN (
          SELECT COUNT(*) FROM recipients r WHERE r.scope = p.scope
          AND r.agency IS NOT DISTINCT FROM p.agency AND r.fiscal_year = p.fiscal_year
          AND NOT EXISTS (SELECT 1 FROM recipients old WHERE old.scope = r.scope
              AND old.agency IS NOT DISTINCT FROM r.agency AND old.vendor_id = r.vendor_id
              AND old.fiscal_year = p.previous_year)) END AS new_vendors,
       CASE WHEN p.previous_year IS NOT NULL THEN (
          SELECT COUNT(*) FROM recipients old WHERE old.scope = p.scope
          AND old.agency IS NOT DISTINCT FROM p.agency AND old.fiscal_year = p.previous_year
          AND NOT EXISTS (SELECT 1 FROM recipients r WHERE r.scope = old.scope
              AND r.agency IS NOT DISTINCT FROM old.agency AND r.vendor_id = old.vendor_id
              AND r.fiscal_year = p.fiscal_year)) END AS dropped_vendors
FROM previous p ORDER BY p.scope, p.agency, p.fiscal_year
