-- Both populations are explicit: scope='agency' and scope='combined'.
-- Filters apply to transactions BEFORE running this query, just as in pandas.
-- Do not classify tied vendors individually: use value BEFORE the entire tie.
WITH vendor_net AS (
    SELECT CASE WHEN GROUPING(agency) = 1 THEN 'combined' ELSE 'agency' END AS scope,
           agency, vendor_id,
           COALESCE(arg_max(NULLIF(vendor_name, ''),
               struct_pack(d := action_date, n := vendor_name, t := transaction_id)), vendor_id) AS vendor_name,
           SUM(CAST(obligation_cents AS HUGEINT)) AS net_cents
    FROM transactions WHERE vendor_id <> ''
    GROUP BY GROUPING SETS ((agency, vendor_id), (vendor_id))
), positive AS (
    SELECT *, SUM(net_cents) OVER (PARTITION BY scope, agency) AS denominator,
           SUM(net_cents) OVER (PARTITION BY scope, agency ORDER BY net_cents DESC
               RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             - net_cents * COUNT(*) OVER (PARTITION BY scope, agency, net_cents) AS value_before_tie,
           SUM(net_cents) OVER (PARTITION BY scope, agency ORDER BY net_cents DESC, vendor_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_cents
    FROM vendor_net WHERE net_cents > 0
)
SELECT v.*, v.net_cents / 100.0 AS net_obligations,
       CASE WHEN v.net_cents <= 0 THEN 'Unclassified'
            WHEN p.value_before_tie * 100 < p.denominator * 80 THEN 'A'
            WHEN p.value_before_tie * 100 < p.denominator * 95 THEN 'B'
            ELSE 'C' END AS category,
       p.net_cents / p.denominator AS share,
       p.running_cents / p.denominator AS cumulative_share
FROM vendor_net v LEFT JOIN positive p
  ON v.scope = p.scope AND v.agency IS NOT DISTINCT FROM p.agency AND v.vendor_id = p.vendor_id
ORDER BY v.scope, v.agency, v.net_cents DESC, v.vendor_id
