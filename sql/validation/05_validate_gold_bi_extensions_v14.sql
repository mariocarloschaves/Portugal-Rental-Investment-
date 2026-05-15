-- 05_validate_gold_bi_extensions_v14.sql

USE portugal_rental_warehouse;

SELECT 'gold_financial_assumptions' AS table_name, COUNT(*) AS row_count, 3 AS expected_rows
FROM gold_financial_assumptions;

SELECT 'gold_dim_financing_scenario' AS table_name, COUNT(*) AS row_count, 5 AS expected_rows
FROM gold_dim_financing_scenario;

SELECT 'gold_investor_assumptions' AS table_name, COUNT(*) AS row_count, 15 AS expected_rows
FROM gold_investor_assumptions;

SELECT
    market_type,
    scenario_name,
    COUNT(*) AS assumption_rows,
    ROUND(AVG(loan_to_cost_pct), 2) AS loan_to_cost_pct
FROM gold_investor_assumptions
GROUP BY market_type, scenario_name
ORDER BY market_type, loan_to_cost_pct;

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
    (SELECT COUNT(*) * 5 FROM gold_fact_listing_snapshot) AS expected_rows
FROM gold_fact_financial_return;

SELECT
    'gold_mart_property_bi' AS table_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(*) * 5 FROM gold_fact_listing_snapshot) AS expected_rows
FROM gold_mart_property_bi;

SELECT
    'gold_mart_neighbourhood_bi' AS table_name,
    COUNT(*) AS row_count
FROM gold_mart_neighbourhood_bi;

SELECT
    'gold_mart_host_bi' AS table_name,
    COUNT(*) AS row_count
FROM gold_mart_host_bi;

SELECT
    'gold_mart_market_bi' AS table_name,
    COUNT(*) AS row_count
FROM gold_mart_market_bi;

SELECT
    'gold_mart_financial_distribution_bi' AS table_name,
    COUNT(*) AS row_count
FROM gold_mart_financial_distribution_bi;

SELECT
    scenario_name,
    COUNT(*) AS financial_return_rows,
    ROUND(AVG(monthly_debt_service), 2) AS avg_monthly_debt_service,
    ROUND(AVG(monthly_net_cash_flow_after_debt), 2) AS avg_monthly_net_cash_flow_after_debt,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_cash_on_cash_return
FROM gold_fact_financial_return
GROUP BY scenario_name
ORDER BY FIELD(scenario_name, 'cash_purchase', 'loan_50', 'loan_70', 'loan_80', 'loan_90');

SELECT
    scenario_name,
    COUNT(*) AS property_mart_rows
FROM gold_mart_property_bi
GROUP BY scenario_name
ORDER BY FIELD(scenario_name, 'cash_purchase', 'loan_50', 'loan_70', 'loan_80', 'loan_90');

SELECT
    'cash_purchase_zero_debt_check' AS validation_name,
    SUM(
        CASE
            WHEN estimated_loan_amount <> 0
              OR monthly_debt_service <> 0
              OR annual_debt_service <> 0
              OR annual_interest_cost <> 0
              OR annual_principal_repayment <> 0
              OR applied_annual_interest_rate <> 0
            THEN 1 ELSE 0
        END
    ) AS failing_rows
FROM gold_fact_financial_return
WHERE scenario_name = 'cash_purchase';

WITH debt_by_projection AS (
    SELECT
        financial_projection_key,
        MAX(CASE WHEN scenario_name = 'cash_purchase' THEN monthly_debt_service END) AS cash_monthly_debt,
        MAX(CASE WHEN scenario_name = 'loan_50' THEN monthly_debt_service END) AS loan_50_monthly_debt,
        MAX(CASE WHEN scenario_name = 'loan_70' THEN monthly_debt_service END) AS loan_70_monthly_debt,
        MAX(CASE WHEN scenario_name = 'loan_80' THEN monthly_debt_service END) AS loan_80_monthly_debt,
        MAX(CASE WHEN scenario_name = 'loan_90' THEN monthly_debt_service END) AS loan_90_monthly_debt
    FROM gold_fact_financial_return
    GROUP BY financial_projection_key
)
SELECT
    'debt_service_increases_by_leverage_check' AS validation_name,
    SUM(
        CASE
            WHEN cash_monthly_debt = 0
             AND loan_50_monthly_debt < loan_70_monthly_debt
             AND loan_70_monthly_debt < loan_80_monthly_debt
             AND loan_80_monthly_debt < loan_90_monthly_debt
            THEN 0 ELSE 1
        END
    ) AS failing_projection_rows
FROM debt_by_projection;

SELECT
    'financial_return_to_projection_orphan_check' AS validation_name,
    COUNT(*) AS orphan_rows
FROM gold_fact_financial_return fr
LEFT JOIN gold_fact_financial_projection fp
    ON fr.financial_projection_key = fp.financial_projection_key
WHERE fp.financial_projection_key IS NULL;

SELECT
    'taxable_income_interest_only_check' AS validation_name,
    SUM(
        CASE
            WHEN ABS(
                fr.taxable_income_estimate
                - ROUND(fp.projected_noi - fr.ownership_cost_total - fr.annual_interest_cost, 4)
            ) > 0.01
            THEN 1 ELSE 0
        END
    ) AS failing_rows
FROM gold_fact_financial_return fr
INNER JOIN gold_fact_financial_projection fp
    ON fr.financial_projection_key = fp.financial_projection_key;

SELECT
    scenario_name,
    COUNT(*) AS investment_grade_rows,
    ROUND(AVG(CASE WHEN monthly_net_cash_flow_after_debt > 0 THEN 1 ELSE 0 END), 4) AS positive_cash_flow_share,
    ROUND(AVG(monthly_net_cash_flow_after_debt), 2) AS avg_monthly_net_cash_flow_after_debt,
    ROUND(AVG(net_cash_flow_after_debt), 2) AS avg_annual_net_cash_flow_after_debt
FROM gold_mart_property_bi
WHERE investment_grade_flag = 1
GROUP BY scenario_name
ORDER BY FIELD(scenario_name, 'cash_purchase', 'loan_50', 'loan_70', 'loan_80', 'loan_90');

SELECT
    distribution_level,
    scenario_name,
    COUNT(*) AS distribution_rows,
    ROUND(AVG(positive_cash_flow_share), 4) AS avg_positive_cash_flow_share,
    ROUND(AVG(median_monthly_net_cash_flow_after_debt), 2) AS avg_median_monthly_net_cash_flow_after_debt,
    ROUND(AVG(top_10pct_avg_monthly_net_cash_flow_after_debt), 2) AS avg_top_10pct_monthly_net_cash_flow_after_debt
FROM gold_mart_financial_distribution_bi
GROUP BY distribution_level, scenario_name
ORDER BY distribution_level, FIELD(scenario_name, 'cash_purchase', 'loan_50', 'loan_70', 'loan_80', 'loan_90');

SELECT
    city,
    market_type,
    scenario_name,
    COUNT(*) AS listing_count,
    ROUND(AVG(projected_gross_revenue), 2) AS avg_annual_projected_gross_revenue,
    ROUND(AVG(projected_noi), 2) AS avg_annual_projected_noi,
    ROUND(AVG(monthly_debt_service), 2) AS avg_monthly_bank_payment,
    ROUND(AVG(monthly_tax_due_estimate), 2) AS avg_monthly_tax_due_estimate,
    ROUND(AVG(monthly_net_cash_flow_after_debt), 2) AS avg_monthly_net_cash_flow_after_debt,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_annual_cash_on_equity_return
FROM gold_mart_property_bi
WHERE investment_grade_flag = 1
GROUP BY city, market_type, scenario_name
ORDER BY city, market_type, FIELD(scenario_name, 'cash_purchase', 'loan_50', 'loan_70', 'loan_80', 'loan_90');
