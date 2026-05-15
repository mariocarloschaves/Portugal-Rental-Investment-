-- 05_validate_gold_bi_extensions_v13.sql

USE portugal_rental_warehouse;

SELECT 'gold_financial_assumptions' AS table_name, COUNT(*) AS row_count, 3 AS expected_rows
FROM gold_financial_assumptions;

SELECT 'gold_investor_assumptions' AS table_name, COUNT(*) AS row_count, 3 AS expected_rows
FROM gold_investor_assumptions;

SELECT
    'gold_dim_date' AS table_name,
    COUNT(*) AS row_count,
    (
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT snapshot_date AS calendar_date
            FROM gold_fact_listing_snapshot
            WHERE snapshot_date IS NOT NULL
            UNION
            SELECT DISTINCT load_batch_date AS calendar_date
            FROM gold_fact_listing_snapshot
            WHERE load_batch_date IS NOT NULL
        ) d
    ) AS expected_rows
FROM gold_dim_date;

SELECT
    'gold_fact_financial_projection' AS table_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(*) FROM gold_fact_listing_snapshot) AS expected_rows
FROM gold_fact_financial_projection;

SELECT
    'gold_fact_financial_return' AS table_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(*) FROM gold_fact_listing_snapshot) AS expected_rows
FROM gold_fact_financial_return;

SELECT
    'gold_mart_property_bi' AS table_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(*) FROM gold_fact_listing_snapshot) AS expected_rows
FROM gold_mart_property_bi;

SELECT
    'gold_mart_neighbourhood_bi' AS table_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(DISTINCT location_key) FROM gold_mart_property_bi) AS expected_rows
FROM gold_mart_neighbourhood_bi;

SELECT
    'gold_mart_host_bi' AS table_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(DISTINCT host_key) FROM gold_mart_property_bi) AS expected_rows
FROM gold_mart_host_bi;

SELECT
    'gold_mart_market_bi' AS table_name,
    COUNT(*) AS row_count
FROM gold_mart_market_bi;

SELECT
    snapshot_date,
    city,
    market_type,
    COUNT(*) AS listing_count,
    ROUND(AVG(projected_gross_revenue), 2) AS avg_annual_projected_gross_revenue,
    ROUND(AVG(monthly_projected_gross_revenue), 2) AS avg_monthly_projected_gross_revenue,
    ROUND(AVG(projected_noi), 2) AS avg_annual_projected_noi,
    ROUND(AVG(monthly_projected_noi), 2) AS avg_monthly_projected_noi,
    ROUND(AVG(financing_vintage_year), 1) AS avg_financing_vintage_year,
    ROUND(AVG(applied_asset_discount_pct), 4) AS avg_applied_asset_discount_pct,
    ROUND(AVG(applied_annual_interest_rate), 4) AS avg_applied_annual_interest_rate,
    ROUND(AVG(annual_debt_service), 2) AS avg_annual_bank_payment_equivalent,
    ROUND(AVG(monthly_debt_service), 2) AS avg_monthly_bank_payment,
    ROUND(AVG(tax_due_estimate), 2) AS avg_annual_tax_due_estimate,
    ROUND(AVG(monthly_tax_due_estimate), 2) AS avg_monthly_tax_due_estimate,
    ROUND(AVG(net_income_after_tax), 2) AS avg_annual_net_income_after_tax,
    ROUND(AVG(monthly_net_income_after_tax), 2) AS avg_monthly_net_income_after_tax,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_annual_cash_on_equity_return
FROM gold_mart_property_bi
WHERE investment_grade_flag = 1
GROUP BY snapshot_date, city, market_type
ORDER BY snapshot_date, city, market_type;

SELECT
    snapshot_date,
    city,
    region_group,
    market_type,
    room_type,
    CASE
        WHEN accommodates <= 2 THEN '1-2 guests'
        WHEN accommodates <= 4 THEN '3-4 guests'
        WHEN accommodates <= 6 THEN '5-6 guests'
        ELSE '7+ guests'
    END AS accommodates_bucket,
    COUNT(*) AS listing_count,
    ROUND(AVG(projected_gross_revenue), 2) AS avg_annual_projected_gross_revenue,
    ROUND(AVG(monthly_projected_gross_revenue), 2) AS avg_monthly_projected_gross_revenue,
    ROUND(AVG(projected_noi), 2) AS avg_annual_projected_noi,
    ROUND(AVG(monthly_projected_noi), 2) AS avg_monthly_projected_noi,
    ROUND(AVG(financing_vintage_year), 1) AS avg_financing_vintage_year,
    ROUND(AVG(applied_asset_discount_pct), 4) AS avg_applied_asset_discount_pct,
    ROUND(AVG(applied_annual_interest_rate), 4) AS avg_applied_annual_interest_rate,
    ROUND(AVG(annual_debt_service), 2) AS avg_annual_bank_payment_equivalent,
    ROUND(AVG(monthly_debt_service), 2) AS avg_monthly_bank_payment,
    ROUND(AVG(tax_due_estimate), 2) AS avg_annual_tax_due_estimate,
    ROUND(AVG(monthly_tax_due_estimate), 2) AS avg_monthly_tax_due_estimate,
    ROUND(AVG(net_income_after_tax), 2) AS avg_annual_net_income_after_tax,
    ROUND(AVG(monthly_net_income_after_tax), 2) AS avg_monthly_net_income_after_tax,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_annual_cash_on_equity_return
FROM gold_mart_property_bi
WHERE investment_grade_flag = 1
GROUP BY
    snapshot_date,
    city,
    region_group,
    market_type,
    room_type,
    CASE
        WHEN accommodates <= 2 THEN '1-2 guests'
        WHEN accommodates <= 4 THEN '3-4 guests'
        WHEN accommodates <= 6 THEN '5-6 guests'
        ELSE '7+ guests'
    END
ORDER BY snapshot_date, city, market_type, room_type, accommodates_bucket;
