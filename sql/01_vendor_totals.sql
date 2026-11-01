-- Each row is one identified recipient within one agency and fiscal year.
-- Signed cents are summed before any eligibility decision. IDs remain strings.
SELECT agency, fiscal_year, vendor_id,
       COALESCE(arg_max(NULLIF(vendor_name, ''),
           struct_pack(d := action_date, n := vendor_name, t := transaction_id)), vendor_id) AS vendor_name,
       SUM(CAST(obligation_cents AS HUGEINT)) AS net_cents,
       SUM(CAST(obligation_cents AS HUGEINT)) / 100.0 AS net_obligations
FROM transactions WHERE vendor_id <> ''
GROUP BY agency, fiscal_year, vendor_id
