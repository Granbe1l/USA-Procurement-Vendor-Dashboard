-- Replace {DATA_PATH} with an escaped absolute path to the prepared Parquet file.
-- The Python runner also supports the existing CSV.gz compatibility artifact.
-- Dates and signed cents come from the validated cleaning pipeline, not inference.
CREATE OR REPLACE VIEW transactions AS
SELECT CAST(transaction_id AS VARCHAR) AS transaction_id,
       COALESCE(CAST(vendor_id AS VARCHAR), '') AS vendor_id,
       COALESCE(CAST(vendor_name AS VARCHAR), '') AS vendor_name,
       CAST(award_id AS VARCHAR) AS award_id,
       CAST(agency AS VARCHAR) AS agency,
       CAST(action_date AS DATE) AS action_date,
       CAST(EXTRACT(YEAR FROM CAST(action_date AS DATE)) +
            CASE WHEN EXTRACT(MONTH FROM CAST(action_date AS DATE)) >= 10
                 THEN 1 ELSE 0 END AS INTEGER) AS fiscal_year,
       CAST(award_type AS VARCHAR) AS award_type,
       CAST(state AS VARCHAR) AS state,
       CAST(state AS VARCHAR) AS recipient_state,
       CAST(obligation_cents AS BIGINT) AS obligation_cents,
       CAST(obligation_cents AS BIGINT) / 100.0 AS obligation
FROM read_parquet('{DATA_PATH}')
