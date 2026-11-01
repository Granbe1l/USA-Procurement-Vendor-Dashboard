-- Approximation only: same normalized display name is NOT a corporate-parent link.
-- Use the latest nonblank label per UEI, matching the pandas label policy.
WITH latest AS (
    SELECT vendor_id,
           arg_max(NULLIF(vendor_name, ''), struct_pack(d := action_date, n := vendor_name, t := transaction_id)) AS vendor_name
    FROM transactions WHERE vendor_id <> '' GROUP BY vendor_id
), normalized AS (
    SELECT *, UPPER(regexp_replace(TRIM(vendor_name), '\s+', ' ', 'g')) AS normalized_name FROM latest
)
SELECT normalized_name, COUNT(*) AS distinct_ueis,
       string_agg(vendor_id, ', ' ORDER BY vendor_id) AS vendor_ids
FROM normalized WHERE normalized_name IS NOT NULL
GROUP BY normalized_name HAVING COUNT(*) > 1
ORDER BY distinct_ueis DESC, normalized_name
