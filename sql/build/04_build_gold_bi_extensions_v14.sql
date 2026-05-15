-- 04_build_gold_bi_extensions_v14.sql
-- Build the lean Gold financial layer, multi-scenario investor return layer, and BI marts.
-- v14 keeps the operating projection logic stable, adds five financing scenarios per market,
-- and adds a distribution mart for percentile/top-performer financial analysis.

USE portugal_rental_warehouse;
SET SQL_SAFE_UPDATES = 0;
SET FOREIGN_KEY_CHECKS = 0;
SET SESSION net_read_timeout = 600;
SET SESSION net_write_timeout = 600;
SET SESSION wait_timeout = 28800;
SET SESSION interactive_timeout = 28800;

DROP TABLE IF EXISTS gold_dim_date;
DROP TABLE IF EXISTS gold_dim_financing_scenario;
DROP TABLE IF EXISTS gold_mart_financial_distribution_bi;
DROP TABLE IF EXISTS gold_mart_market_bi;
DROP TABLE IF EXISTS gold_mart_host_bi;
DROP TABLE IF EXISTS gold_mart_neighbourhood_bi;
DROP TABLE IF EXISTS gold_mart_property_bi;
DROP TABLE IF EXISTS gold_fact_financial_return;
DROP TABLE IF EXISTS gold_investor_assumptions;
DROP TABLE IF EXISTS gold_fact_financial_projection;
DROP TABLE IF EXISTS gold_financial_assumptions;

CREATE TABLE gold_dim_date (
    date_key BIGINT PRIMARY KEY,
    calendar_date DATE,
    day_of_month BIGINT,
    day_name VARCHAR(20),
    week_of_year BIGINT,
    month_number BIGINT,
    month_name VARCHAR(20),
    quarter_number BIGINT,
    year_number BIGINT,
    is_weekend TINYINT,
    is_month_end TINYINT,
    is_month_start TINYINT,
    KEY idx_gold_dim_date_calendar_date (calendar_date),
    KEY idx_gold_dim_date_year_month (year_number, month_number)
) ENGINE=InnoDB;

CREATE TABLE gold_dim_financing_scenario (
    scenario_name VARCHAR(100) PRIMARY KEY,
    scenario_order BIGINT,
    scenario_label VARCHAR(100),
    loan_to_cost_pct DOUBLE,
    active_flag TINYINT,
    notes TEXT
) ENGINE=InnoDB;

CREATE TABLE gold_financial_assumptions (
    assumption_key BIGINT PRIMARY KEY,
    scenario_name VARCHAR(100),
    market_type VARCHAR(50),
    management_style VARCHAR(50),
    avg_stay_nights DOUBLE,
    platform_fee_pct DOUBLE,
    management_fee_pct DOUBLE,
    base_monthly_electricity DOUBLE,
    electricity_per_occupied_night DOUBLE,
    base_monthly_water DOUBLE,
    water_per_occupied_night DOUBLE,
    internet_monthly DOUBLE,
    laundry_per_turnover DOUBLE,
    toiletries_per_turnover DOUBLE,
    cleaning_cost_per_turnover DOUBLE,
    monthly_insurance DOUBLE,
    monthly_condo_fee DOUBLE,
    monthly_other_fixed_cost DOUBLE,
    maintenance_reserve_pct DOUBLE,
    active_flag TINYINT,
    notes TEXT,
    KEY idx_gold_financial_assumptions_market_type (market_type)
) ENGINE=InnoDB;

CREATE TABLE gold_fact_financial_projection (
    financial_projection_key BIGINT PRIMARY KEY,
    assumption_key BIGINT,
    scenario_name VARCHAR(100),
    market_type VARCHAR(50),
    global_property_id VARCHAR(255),
    property_id BIGINT,
    property_key BIGINT,
    host_id BIGINT,
    host_key BIGINT,
    location_key BIGINT,
    city VARCHAR(100),
    neighbourhood_cleansed VARCHAR(255),
    neighbourhood_group_cleansed VARCHAR(255),
    region_group VARCHAR(255),
    market_segment VARCHAR(100),
    coastal_flag TINYINT,
    urban_flag TINYINT,
    platform_count BIGINT,
    snapshot_date DATE,
    price DOUBLE,
    projected_occupancy_rate DOUBLE,
    projected_occupied_nights DOUBLE,
    avg_stay_nights DOUBLE,
    projected_bookings_count DOUBLE,
    projected_gross_revenue DOUBLE,
    monthly_projected_gross_revenue DOUBLE,
    projected_platform_fees DOUBLE,
    projected_management_fees DOUBLE,
    projected_cleaning_cost DOUBLE,
    projected_laundry_cost DOUBLE,
    projected_toiletries_cost DOUBLE,
    projected_base_utility_cost DOUBLE,
    projected_variable_utility_cost DOUBLE,
    projected_total_utility_cost DOUBLE,
    monthly_projected_total_utility_cost DOUBLE,
    projected_insurance_cost DOUBLE,
    projected_condo_cost DOUBLE,
    projected_other_fixed_cost DOUBLE,
    projected_maintenance_reserve DOUBLE,
    projected_total_operating_cost DOUBLE,
    monthly_projected_total_operating_cost DOUBLE,
    projected_noi DOUBLE,
    monthly_projected_noi DOUBLE,
    projected_noi_margin DOUBLE,
    break_even_occupied_nights DOUBLE,
    break_even_occupancy_rate DOUBLE,
    investment_grade_flag TINYINT,
    load_batch_date DATE,
    created_at DATETIME,
    KEY idx_gold_fact_financial_projection_property (property_id),
    KEY idx_gold_fact_financial_projection_location (location_key),
    KEY idx_gold_fact_financial_projection_market_type (market_type)
) ENGINE=InnoDB;

CREATE TABLE gold_investor_assumptions (
    investor_assumption_key BIGINT PRIMARY KEY,
    scenario_name VARCHAR(100),
    market_type VARCHAR(50),
    ownership_structure VARCHAR(100),
    estimated_asset_cost_base DOUBLE,
    estimated_asset_cost_per_bedroom DOUBLE,
    estimated_asset_cost_per_guest DOUBLE,
    furnishing_setup_cost DOUBLE,
    closing_cost_pct DOUBLE,
    imi_rate_pct DOUBLE,
    annual_accounting_cost DOUBLE,
    annual_licensing_cost DOUBLE,
    effective_tax_rate DOUBLE,
    loan_to_cost_pct DOUBLE,
    annual_interest_rate DOUBLE,
    loan_term_years BIGINT,
    active_flag TINYINT,
    notes TEXT,
    KEY idx_gold_investor_assumptions_market_type (market_type)
) ENGINE=InnoDB;

CREATE TABLE gold_fact_financial_return (
    financial_return_key BIGINT PRIMARY KEY,
    financial_projection_key BIGINT,
    investor_assumption_key BIGINT,
    scenario_name VARCHAR(100),
    market_type VARCHAR(50),
    global_property_id VARCHAR(255),
    property_id BIGINT,
    property_key BIGINT,
    host_id BIGINT,
    host_key BIGINT,
    location_key BIGINT,
    city VARCHAR(100),
    neighbourhood_cleansed VARCHAR(255),
    neighbourhood_group_cleansed VARCHAR(255),
    region_group VARCHAR(255),
    market_segment VARCHAR(100),
    coastal_flag TINYINT,
    urban_flag TINYINT,
    investment_grade_flag TINYINT,
    financing_vintage_year BIGINT,
    applied_asset_discount_pct DOUBLE,
    applied_annual_interest_rate DOUBLE,
    estimated_asset_cost DOUBLE,
    estimated_furnishing_setup_cost DOUBLE,
    estimated_closing_cost DOUBLE,
    estimated_total_project_capex DOUBLE,
    estimated_equity_required DOUBLE,
    estimated_loan_amount DOUBLE,
    monthly_debt_service DOUBLE,
    annual_debt_service DOUBLE,
    annual_interest_cost DOUBLE,
    annual_principal_repayment DOUBLE,
    monthly_interest_cost DOUBLE,
    monthly_principal_repayment DOUBLE,
    imi_cost DOUBLE,
    accounting_cost DOUBLE,
    licensing_cost DOUBLE,
    ownership_cost_total DOUBLE,
    taxable_income_estimate DOUBLE,
    tax_due_estimate DOUBLE,
    monthly_tax_due_estimate DOUBLE,
    net_income_after_tax DOUBLE,
    monthly_net_income_after_tax DOUBLE,
    net_cash_flow_after_debt DOUBLE,
    monthly_net_cash_flow_after_debt DOUBLE,
    cash_on_cash_return DOUBLE,
    payback_years DOUBLE,
    load_batch_date DATE,
    created_at DATETIME,
    KEY idx_gold_fact_financial_return_projection (financial_projection_key),
    KEY idx_gold_fact_financial_return_property (property_id),
    KEY idx_gold_fact_financial_return_location (location_key),
    KEY idx_gold_fact_financial_return_market_type (market_type),
    KEY idx_gold_fact_financial_return_scenario (scenario_name)
) ENGINE=InnoDB;

CREATE TABLE gold_mart_property_bi (
    property_bi_key BIGINT PRIMARY KEY,
    global_property_id VARCHAR(255),
    property_id BIGINT,
    property_key BIGINT,
    host_id BIGINT,
    host_key BIGINT,
    location_key BIGINT,
    city VARCHAR(100),
    neighbourhood_cleansed VARCHAR(255),
    neighbourhood_group_cleansed VARCHAR(255),
    region_group VARCHAR(255),
    market_segment VARCHAR(100),
    market_type VARCHAR(50),
    coastal_flag TINYINT,
    urban_flag TINYINT,
    platform_count BIGINT,
    host_is_superhost TINYINT,
    instant_bookable TINYINT,
    property_type VARCHAR(255),
    room_type VARCHAR(100),
    accommodates BIGINT,
    bedrooms DOUBLE,
    beds DOUBLE,
    bathrooms DOUBLE,
    price DOUBLE,
    price_per_guest DOUBLE,
    price_per_bedroom DOUBLE,
    price_per_bed DOUBLE,
    availability_30 BIGINT,
    availability_60 BIGINT,
    availability_90 BIGINT,
    availability_365 BIGINT,
    occupancy_rate DOUBLE,
    occupancy_rate_alt DOUBLE,
    estimated_occupancy_l365d BIGINT,
    estimated_revenue_l365d DOUBLE,
    number_of_reviews BIGINT,
    reviews_per_month DOUBLE,
    review_scores_rating DOUBLE,
    review_scores_cleanliness DOUBLE,
    review_scores_location DOUBLE,
    review_scores_value DOUBLE,
    scenario_name VARCHAR(100),
    investor_assumption_key BIGINT,
    projected_bookings_count DOUBLE,
    projected_gross_revenue DOUBLE,
    monthly_projected_gross_revenue DOUBLE,
    projected_total_utility_cost DOUBLE,
    monthly_projected_total_utility_cost DOUBLE,
    projected_platform_fees DOUBLE,
    projected_management_fees DOUBLE,
    projected_cleaning_cost DOUBLE,
    projected_total_operating_cost DOUBLE,
    monthly_projected_total_operating_cost DOUBLE,
    projected_noi DOUBLE,
    monthly_projected_noi DOUBLE,
    projected_noi_margin DOUBLE,
    break_even_occupancy_rate DOUBLE,
    investment_grade_flag TINYINT,
    financing_vintage_year BIGINT,
    applied_asset_discount_pct DOUBLE,
    applied_annual_interest_rate DOUBLE,
    estimated_total_project_capex DOUBLE,
    estimated_equity_required DOUBLE,
    estimated_loan_amount DOUBLE,
    annual_debt_service DOUBLE,
    monthly_debt_service DOUBLE,
    annual_interest_cost DOUBLE,
    annual_principal_repayment DOUBLE,
    tax_due_estimate DOUBLE,
    monthly_tax_due_estimate DOUBLE,
    net_income_after_tax DOUBLE,
    monthly_net_income_after_tax DOUBLE,
    net_cash_flow_after_debt DOUBLE,
    monthly_net_cash_flow_after_debt DOUBLE,
    cash_on_cash_return DOUBLE,
    payback_years DOUBLE,
    last_review DATE,
    snapshot_date_key BIGINT,
    snapshot_date DATE,
    load_batch_date_key BIGINT,
    load_batch_date DATE,
    created_at DATETIME,
    KEY idx_gold_mart_property_bi_projection_scenario (snapshot_date_key, scenario_name),
    KEY idx_gold_mart_property_bi_property (property_id),
    KEY idx_gold_mart_property_bi_location (location_key),
    KEY idx_gold_mart_property_bi_host (host_id),
    KEY idx_gold_mart_property_bi_market_type (market_type),
    KEY idx_gold_mart_property_bi_scenario (scenario_name)
) ENGINE=InnoDB;

CREATE TABLE gold_mart_neighbourhood_bi (
    neighbourhood_bi_key BIGINT PRIMARY KEY,
    location_key BIGINT,
    city VARCHAR(100),
    neighbourhood_cleansed VARCHAR(255),
    neighbourhood_group_cleansed VARCHAR(255),
    region_group VARCHAR(255),
    market_segment VARCHAR(100),
    market_type VARCHAR(50),
    scenario_name VARCHAR(100),
    coastal_flag TINYINT,
    urban_flag TINYINT,
    listing_count BIGINT,
    avg_price DOUBLE,
    avg_price_per_guest DOUBLE,
    avg_price_per_bedroom DOUBLE,
    avg_price_per_bed DOUBLE,
    avg_occupancy_rate DOUBLE,
    avg_estimated_revenue DOUBLE,
    avg_projected_bookings_count DOUBLE,
    avg_projected_gross_revenue DOUBLE,
    avg_monthly_projected_gross_revenue DOUBLE,
    avg_projected_utility_cost DOUBLE,
    avg_monthly_projected_utility_cost DOUBLE,
    avg_projected_operating_cost DOUBLE,
    avg_monthly_projected_operating_cost DOUBLE,
    avg_projected_noi DOUBLE,
    avg_monthly_projected_noi DOUBLE,
    avg_projected_noi_margin DOUBLE,
    total_projected_gross_revenue DOUBLE,
    total_projected_noi DOUBLE,
    avg_estimated_total_project_capex DOUBLE,
    avg_estimated_loan_amount DOUBLE,
    avg_annual_debt_service DOUBLE,
    avg_monthly_debt_service DOUBLE,
    avg_annual_interest_cost DOUBLE,
    avg_annual_principal_repayment DOUBLE,
    avg_tax_due_estimate DOUBLE,
    avg_monthly_tax_due_estimate DOUBLE,
    avg_net_income_after_tax DOUBLE,
    avg_monthly_net_income_after_tax DOUBLE,
    avg_net_cash_flow_after_debt DOUBLE,
    avg_monthly_net_cash_flow_after_debt DOUBLE,
    avg_cash_on_cash_return DOUBLE,
    avg_payback_years DOUBLE,
    avg_number_of_reviews DOUBLE,
    avg_reviews_per_month DOUBLE,
    avg_review_score_rating DOUBLE,
    avg_review_score_cleanliness DOUBLE,
    avg_review_score_location DOUBLE,
    avg_review_score_value DOUBLE,
    avg_platform_count DOUBLE,
    superhost_share DOUBLE,
    instant_bookable_share DOUBLE,
    investment_grade_listing_count BIGINT,
    avg_availability_30 DOUBLE,
    avg_availability_60 DOUBLE,
    avg_availability_90 DOUBLE,
    avg_availability_365 DOUBLE,
    snapshot_date_key BIGINT,
    snapshot_date DATE,
    KEY idx_gold_mart_neighbourhood_bi_location (location_key),
    KEY idx_gold_mart_neighbourhood_bi_city_neighbourhood (city, neighbourhood_cleansed),
    KEY idx_gold_mart_neighbourhood_bi_market_type (market_type),
    KEY idx_gold_mart_neighbourhood_bi_scenario (scenario_name)
) ENGINE=InnoDB;

CREATE TABLE gold_mart_host_bi (
    host_bi_key BIGINT PRIMARY KEY,
    host_key BIGINT,
    host_id BIGINT,
    scenario_name VARCHAR(100),
    property_count BIGINT,
    city_count BIGINT,
    avg_price DOUBLE,
    avg_occupancy_rate DOUBLE,
    avg_estimated_revenue DOUBLE,
    avg_projected_gross_revenue DOUBLE,
    avg_monthly_projected_gross_revenue DOUBLE,
    avg_projected_utility_cost DOUBLE,
    avg_monthly_projected_utility_cost DOUBLE,
    avg_projected_operating_cost DOUBLE,
    avg_monthly_projected_operating_cost DOUBLE,
    avg_projected_noi DOUBLE,
    avg_monthly_projected_noi DOUBLE,
    avg_projected_noi_margin DOUBLE,
    total_projected_noi DOUBLE,
    avg_estimated_loan_amount DOUBLE,
    avg_annual_debt_service DOUBLE,
    avg_monthly_debt_service DOUBLE,
    avg_annual_interest_cost DOUBLE,
    avg_annual_principal_repayment DOUBLE,
    avg_tax_due_estimate DOUBLE,
    avg_monthly_tax_due_estimate DOUBLE,
    avg_net_income_after_tax DOUBLE,
    avg_monthly_net_income_after_tax DOUBLE,
    avg_net_cash_flow_after_debt DOUBLE,
    avg_monthly_net_cash_flow_after_debt DOUBLE,
    avg_cash_on_cash_return DOUBLE,
    avg_payback_years DOUBLE,
    avg_review_score_rating DOUBLE,
    avg_platform_count DOUBLE,
    superhost_flag TINYINT,
    snapshot_date_key BIGINT,
    snapshot_date DATE,
    KEY idx_gold_mart_host_bi_host (host_id),
    KEY idx_gold_mart_host_bi_scenario (scenario_name)
) ENGINE=InnoDB;

CREATE TABLE gold_mart_market_bi (
    market_bi_key BIGINT PRIMARY KEY,
    city VARCHAR(100),
    region_group VARCHAR(255),
    market_segment VARCHAR(100),
    market_type VARCHAR(50),
    scenario_name VARCHAR(100),
    room_type VARCHAR(100),
    accommodates_bucket VARCHAR(50),
    listing_count BIGINT,
    avg_price DOUBLE,
    avg_projected_occupied_nights DOUBLE,
    avg_projected_gross_revenue DOUBLE,
    avg_monthly_projected_gross_revenue DOUBLE,
    avg_projected_utility_cost DOUBLE,
    avg_monthly_projected_utility_cost DOUBLE,
    avg_projected_operating_cost DOUBLE,
    avg_monthly_projected_operating_cost DOUBLE,
    avg_projected_noi DOUBLE,
    avg_monthly_projected_noi DOUBLE,
    avg_projected_noi_margin DOUBLE,
    total_projected_gross_revenue DOUBLE,
    total_projected_noi DOUBLE,
    avg_estimated_loan_amount DOUBLE,
    avg_annual_debt_service DOUBLE,
    avg_monthly_debt_service DOUBLE,
    avg_annual_interest_cost DOUBLE,
    avg_annual_principal_repayment DOUBLE,
    avg_tax_due_estimate DOUBLE,
    avg_monthly_tax_due_estimate DOUBLE,
    avg_net_income_after_tax DOUBLE,
    avg_monthly_net_income_after_tax DOUBLE,
    avg_net_cash_flow_after_debt DOUBLE,
    avg_monthly_net_cash_flow_after_debt DOUBLE,
    avg_cash_on_cash_return DOUBLE,
    avg_payback_years DOUBLE,
    avg_review_score_rating DOUBLE,
    snapshot_date_key BIGINT,
    snapshot_date DATE,
    KEY idx_gold_mart_market_bi_city_market (city, market_type),
    KEY idx_gold_mart_market_bi_region_group (region_group),
    KEY idx_gold_mart_market_bi_scenario (scenario_name)
) ENGINE=InnoDB;

CREATE TABLE gold_mart_financial_distribution_bi (
    financial_distribution_bi_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    distribution_level VARCHAR(50),
    city VARCHAR(100),
    location_key BIGINT,
    neighbourhood_cleansed VARCHAR(255),
    region_group VARCHAR(255),
    market_segment VARCHAR(100),
    market_type VARCHAR(50),
    scenario_name VARCHAR(100),
    room_type VARCHAR(100),
    accommodates_bucket VARCHAR(50),
    listing_count BIGINT,
    avg_monthly_net_cash_flow_after_debt DOUBLE,
    p25_monthly_net_cash_flow_after_debt DOUBLE,
    median_monthly_net_cash_flow_after_debt DOUBLE,
    p75_monthly_net_cash_flow_after_debt DOUBLE,
    p90_monthly_net_cash_flow_after_debt DOUBLE,
    top_10pct_avg_monthly_net_cash_flow_after_debt DOUBLE,
    avg_monthly_net_income_after_tax DOUBLE,
    p25_monthly_net_income_after_tax DOUBLE,
    median_monthly_net_income_after_tax DOUBLE,
    p75_monthly_net_income_after_tax DOUBLE,
    p90_monthly_net_income_after_tax DOUBLE,
    avg_cash_on_cash_return DOUBLE,
    median_cash_on_cash_return DOUBLE,
    p75_cash_on_cash_return DOUBLE,
    p90_cash_on_cash_return DOUBLE,
    positive_cash_flow_listing_count BIGINT,
    positive_cash_flow_share DOUBLE,
    investment_grade_listing_count BIGINT,
    snapshot_date_key BIGINT,
    snapshot_date DATE,
    KEY idx_gold_mart_financial_distribution_level (distribution_level),
    KEY idx_gold_mart_financial_distribution_market (city, market_type),
    KEY idx_gold_mart_financial_distribution_scenario (scenario_name)
) ENGINE=InnoDB;

INSERT INTO gold_financial_assumptions (
    assumption_key, scenario_name, market_type, management_style, avg_stay_nights,
    platform_fee_pct, management_fee_pct, base_monthly_electricity, electricity_per_occupied_night,
    base_monthly_water, water_per_occupied_night, internet_monthly, laundry_per_turnover,
    toiletries_per_turnover, cleaning_cost_per_turnover, monthly_insurance, monthly_condo_fee,
    monthly_other_fixed_cost, maintenance_reserve_pct, active_flag, notes
) VALUES
    (1, 'base_2026', 'urban', 'self_managed', 4.5, 0.03, 0.00, 45.0, 1.00, 15.0, 0.35, 35.0, 10.0, 3.0, 35.0, 15.0, 20.0, 15.0, 0.03, 1, 'Portugal-oriented urban assumptions for a cost-conscious self-managed host.'),
    (2, 'base_2026', 'city',  'self_managed', 5.2, 0.03, 0.00, 50.0, 1.20, 18.0, 0.40, 35.0, 11.0, 3.5, 40.0, 15.0, 25.0, 15.0, 0.03, 1, 'Portugal-oriented city assumptions for a cost-conscious self-managed host.'),
    (3, 'base_2026', 'beach', 'self_managed', 6.3, 0.03, 0.00, 55.0, 1.50, 20.0, 0.50, 35.0, 12.0, 4.0, 45.0, 16.0, 30.0, 20.0, 0.04, 1, 'Portugal-oriented beach assumptions for a cost-conscious self-managed host.');

INSERT INTO gold_dim_financing_scenario (
    scenario_name, scenario_order, scenario_label, loan_to_cost_pct, active_flag, notes
) VALUES
    ('cash_purchase', 1, 'Cash purchase', 0.00, 1, 'No bank debt. Investor funds the full project capex.'),
    ('loan_50', 2, '50% loan', 0.50, 1, 'Moderate leverage: bank funds 50% of total project capex.'),
    ('loan_70', 3, '70% loan', 0.70, 1, 'Balanced leverage: bank funds 70% of total project capex.'),
    ('loan_80', 4, '80% loan', 0.80, 1, 'High but common leverage: bank funds 80% of total project capex.'),
    ('loan_90', 5, '90% loan', 0.90, 1, 'Aggressive leverage: bank funds 90% of total project capex.');

INSERT INTO gold_investor_assumptions (
    investor_assumption_key, scenario_name, market_type, ownership_structure,
    estimated_asset_cost_base, estimated_asset_cost_per_bedroom, estimated_asset_cost_per_guest,
    furnishing_setup_cost, closing_cost_pct, imi_rate_pct, annual_accounting_cost,
    annual_licensing_cost, effective_tax_rate, loan_to_cost_pct, annual_interest_rate,
    loan_term_years, active_flag, notes
) VALUES
    (1,  'cash_purchase', 'urban', 'company_optimized', 90000, 18000, 3500, 10000, 0.05, 0.0035, 1020, 300, 0.17, 0.00, 0.0000, 30, 1, 'Urban cash purchase: no bank debt, full project capex funded by investor equity.'),
    (2,  'loan_50',       'urban', 'company_optimized', 90000, 18000, 3500, 10000, 0.05, 0.0035, 1020, 300, 0.17, 0.50, 0.0375, 30, 1, 'Urban 50% loan-to-cost financing with optimized deductible business expenses.'),
    (3,  'loan_70',       'urban', 'company_optimized', 90000, 18000, 3500, 10000, 0.05, 0.0035, 1020, 300, 0.17, 0.70, 0.0375, 30, 1, 'Urban 70% loan-to-cost financing with optimized deductible business expenses.'),
    (4,  'loan_80',       'urban', 'company_optimized', 90000, 18000, 3500, 10000, 0.05, 0.0035, 1020, 300, 0.17, 0.80, 0.0375, 30, 1, 'Urban 80% loan-to-cost financing with optimized deductible business expenses.'),
    (5,  'loan_90',       'urban', 'company_optimized', 90000, 18000, 3500, 10000, 0.05, 0.0035, 1020, 300, 0.17, 0.90, 0.0375, 30, 1, 'Urban 90% loan-to-cost financing with optimized deductible business expenses.'),
    (6,  'cash_purchase', 'city',  'company_optimized', 105000, 22000, 4500, 12000, 0.05, 0.0038, 1020, 300, 0.17, 0.00, 0.0000, 30, 1, 'City cash purchase: no bank debt, full project capex funded by investor equity.'),
    (7,  'loan_50',       'city',  'company_optimized', 105000, 22000, 4500, 12000, 0.05, 0.0038, 1020, 300, 0.17, 0.50, 0.0375, 30, 1, 'City 50% loan-to-cost financing with optimized deductible business expenses.'),
    (8,  'loan_70',       'city',  'company_optimized', 105000, 22000, 4500, 12000, 0.05, 0.0038, 1020, 300, 0.17, 0.70, 0.0375, 30, 1, 'City 70% loan-to-cost financing with optimized deductible business expenses.'),
    (9,  'loan_80',       'city',  'company_optimized', 105000, 22000, 4500, 12000, 0.05, 0.0038, 1020, 300, 0.17, 0.80, 0.0375, 30, 1, 'City 80% loan-to-cost financing with optimized deductible business expenses.'),
    (10, 'loan_90',       'city',  'company_optimized', 105000, 22000, 4500, 12000, 0.05, 0.0038, 1020, 300, 0.17, 0.90, 0.0375, 30, 1, 'City 90% loan-to-cost financing with optimized deductible business expenses.'),
    (11, 'cash_purchase', 'beach', 'company_optimized', 115000, 25000, 5000, 13000, 0.05, 0.0038, 1020, 300, 0.17, 0.00, 0.0000, 30, 1, 'Beach cash purchase: no bank debt, full project capex funded by investor equity.'),
    (12, 'loan_50',       'beach', 'company_optimized', 115000, 25000, 5000, 13000, 0.05, 0.0038, 1020, 300, 0.17, 0.50, 0.0390, 30, 1, 'Beach 50% loan-to-cost financing with optimized deductible business expenses.'),
    (13, 'loan_70',       'beach', 'company_optimized', 115000, 25000, 5000, 13000, 0.05, 0.0038, 1020, 300, 0.17, 0.70, 0.0390, 30, 1, 'Beach 70% loan-to-cost financing with optimized deductible business expenses.'),
    (14, 'loan_80',       'beach', 'company_optimized', 115000, 25000, 5000, 13000, 0.05, 0.0038, 1020, 300, 0.17, 0.80, 0.0390, 30, 1, 'Beach 80% loan-to-cost financing with optimized deductible business expenses.'),
    (15, 'loan_90',       'beach', 'company_optimized', 115000, 25000, 5000, 13000, 0.05, 0.0038, 1020, 300, 0.17, 0.90, 0.0390, 30, 1, 'Beach 90% loan-to-cost financing with optimized deductible business expenses.');

INSERT INTO gold_dim_date (
    date_key, calendar_date, day_of_month, day_name, week_of_year, month_number, month_name,
    quarter_number, year_number, is_weekend, is_month_end, is_month_start
)
SELECT
    CAST(DATE_FORMAT(d.calendar_date, '%Y%m%d') AS UNSIGNED) AS date_key,
    d.calendar_date,
    DAY(d.calendar_date) AS day_of_month,
    DAYNAME(d.calendar_date) AS day_name,
    WEEKOFYEAR(d.calendar_date) AS week_of_year,
    MONTH(d.calendar_date) AS month_number,
    MONTHNAME(d.calendar_date) AS month_name,
    QUARTER(d.calendar_date) AS quarter_number,
    YEAR(d.calendar_date) AS year_number,
    CASE WHEN DAYOFWEEK(d.calendar_date) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend,
    CASE WHEN d.calendar_date = LAST_DAY(d.calendar_date) THEN 1 ELSE 0 END AS is_month_end,
    CASE WHEN DAY(d.calendar_date) = 1 THEN 1 ELSE 0 END AS is_month_start
FROM (
    SELECT DISTINCT snapshot_date AS calendar_date
    FROM gold_fact_listing_snapshot
    WHERE snapshot_date IS NOT NULL
    UNION
    SELECT DISTINCT load_batch_date AS calendar_date
    FROM gold_fact_listing_snapshot
    WHERE load_batch_date IS NOT NULL
) d;

INSERT INTO gold_fact_financial_projection (
    financial_projection_key, assumption_key, scenario_name, market_type, global_property_id,
    property_id, property_key, host_id, host_key, location_key, city, neighbourhood_cleansed,
    neighbourhood_group_cleansed, region_group, market_segment, coastal_flag, urban_flag,
    platform_count, snapshot_date, price, projected_occupancy_rate, projected_occupied_nights,
    avg_stay_nights, projected_bookings_count, projected_gross_revenue, monthly_projected_gross_revenue, projected_platform_fees,
    projected_management_fees, projected_cleaning_cost, projected_laundry_cost,
    projected_toiletries_cost, projected_base_utility_cost, projected_variable_utility_cost,
    projected_total_utility_cost, monthly_projected_total_utility_cost, projected_insurance_cost, projected_condo_cost,
    projected_other_fixed_cost, projected_maintenance_reserve, projected_total_operating_cost, monthly_projected_total_operating_cost,
    projected_noi, monthly_projected_noi, projected_noi_margin, break_even_occupied_nights, break_even_occupancy_rate,
    investment_grade_flag, load_batch_date, created_at
)
WITH platform_counts AS (
    SELECT property_id, COUNT(DISTINCT platform_key) AS platform_count
    FROM gold_bridge_property_platform
    GROUP BY property_id
),
snapshot_stage1 AS (
    SELECT
        fls.snapshot_key AS financial_projection_key,
        fls.global_property_id,
        fls.property_id,
        fls.property_key,
        fls.host_id,
        fls.host_key,
        fls.location_key,
        dl.city,
        dl.neighbourhood_cleansed,
        dl.neighbourhood_group_cleansed,
        dl.region_group,
        dl.market_segment,
        dl.coastal_flag,
        dl.urban_flag,
        COALESCE(pc.platform_count, 1) AS platform_count,
        fls.snapshot_date,
        fls.load_batch_date,
        fls.created_at,
        COALESCE(fls.price, 0) AS price,
        COALESCE(dp.room_type, 'Unknown') AS room_type,
        COALESCE(dp.accommodates, 0) AS accommodates,
        CASE
            WHEN dl.market_segment = 'coast_beach' OR COALESCE(dl.coastal_flag, 0) = 1 THEN 'beach'
            WHEN dl.market_segment = 'urban_area' OR COALESCE(dl.urban_flag, 0) = 1 THEN 'urban'
            ELSE 'city'
        END AS market_type,
        CASE
            WHEN fls.estimated_occupancy_l365d IS NOT NULL AND fls.estimated_occupancy_l365d > 0
                THEN ROUND(fls.estimated_occupancy_l365d / 365.0, 4)
            WHEN fls.occupancy_rate IS NOT NULL THEN fls.occupancy_rate
            WHEN fls.occupancy_rate_alt IS NOT NULL AND fls.occupancy_rate_alt > 1
                THEN ROUND(fls.occupancy_rate_alt / 365.0, 4)
            WHEN fls.occupancy_rate_alt IS NOT NULL THEN fls.occupancy_rate_alt
            ELSE 0
        END AS projected_occupancy_rate,
        fls.estimated_occupancy_l365d,
        fls.estimated_revenue_l365d
    FROM gold_fact_listing_snapshot fls
    LEFT JOIN gold_dim_location dl ON fls.location_key = dl.location_key
    LEFT JOIN gold_dim_property dp ON fls.property_key = dp.property_key
    LEFT JOIN platform_counts pc ON fls.property_id = pc.property_id
),
snapshot_stage2 AS (
    SELECT
        s1.*,
        CASE
            WHEN s1.estimated_occupancy_l365d IS NOT NULL AND s1.estimated_occupancy_l365d > 0
                THEN s1.estimated_occupancy_l365d
            ELSE ROUND(s1.projected_occupancy_rate * 365.0, 4)
        END AS projected_occupied_nights
    FROM snapshot_stage1 s1
),
projection_base AS (
    SELECT
        s2.*,
        a.assumption_key,
        a.scenario_name,
        a.avg_stay_nights,
        a.platform_fee_pct,
        a.management_fee_pct,
        a.base_monthly_electricity,
        a.electricity_per_occupied_night,
        a.base_monthly_water,
        a.water_per_occupied_night,
        a.internet_monthly,
        a.laundry_per_turnover,
        a.toiletries_per_turnover,
        a.cleaning_cost_per_turnover,
        a.monthly_insurance,
        a.monthly_condo_fee,
        a.monthly_other_fixed_cost,
        a.maintenance_reserve_pct,
        CASE
            WHEN COALESCE(s2.estimated_revenue_l365d, 0) > 0 THEN s2.estimated_revenue_l365d
            WHEN s2.price > 0 THEN ROUND(s2.price * s2.projected_occupied_nights, 4)
            ELSE 0
        END AS projected_gross_revenue
    FROM snapshot_stage2 s2
    INNER JOIN gold_financial_assumptions a
        ON s2.market_type = a.market_type
       AND a.active_flag = 1
),
projection_metrics AS (
    SELECT
        pb.*,
        ROUND(pb.projected_occupied_nights / NULLIF(pb.avg_stay_nights, 0), 4) AS projected_bookings_count,
        ROUND(pb.projected_gross_revenue * pb.platform_fee_pct, 4) AS projected_platform_fees,
        ROUND(pb.projected_gross_revenue * pb.management_fee_pct, 4) AS projected_management_fees,
        ROUND((pb.projected_occupied_nights / NULLIF(pb.avg_stay_nights, 0)) * pb.cleaning_cost_per_turnover, 4) AS projected_cleaning_cost,
        ROUND((pb.projected_occupied_nights / NULLIF(pb.avg_stay_nights, 0)) * pb.laundry_per_turnover, 4) AS projected_laundry_cost,
        ROUND((pb.projected_occupied_nights / NULLIF(pb.avg_stay_nights, 0)) * pb.toiletries_per_turnover, 4) AS projected_toiletries_cost,
        ROUND(12.0 * (pb.base_monthly_electricity + pb.base_monthly_water + pb.internet_monthly), 4) AS projected_base_utility_cost,
        ROUND(pb.projected_occupied_nights * (pb.electricity_per_occupied_night + pb.water_per_occupied_night), 4) AS projected_variable_utility_cost,
        ROUND(12.0 * pb.monthly_insurance, 4) AS projected_insurance_cost,
        ROUND(12.0 * pb.monthly_condo_fee, 4) AS projected_condo_cost,
        ROUND(12.0 * pb.monthly_other_fixed_cost, 4) AS projected_other_fixed_cost,
        ROUND(pb.projected_gross_revenue * pb.maintenance_reserve_pct, 4) AS projected_maintenance_reserve
    FROM projection_base pb
),
projection_final AS (
    SELECT
        pm.*,
        ROUND(pm.projected_base_utility_cost + pm.projected_variable_utility_cost, 4) AS projected_total_utility_cost,
        ROUND(
            pm.projected_platform_fees + pm.projected_management_fees + pm.projected_cleaning_cost +
            pm.projected_laundry_cost + pm.projected_toiletries_cost + pm.projected_base_utility_cost +
            pm.projected_variable_utility_cost + pm.projected_insurance_cost + pm.projected_condo_cost +
            pm.projected_other_fixed_cost + pm.projected_maintenance_reserve,
            4
        ) AS projected_total_operating_cost
    FROM projection_metrics pm
)
SELECT
    pf.financial_projection_key,
    pf.assumption_key,
    pf.scenario_name,
    pf.market_type,
    pf.global_property_id,
    pf.property_id,
    pf.property_key,
    pf.host_id,
    pf.host_key,
    pf.location_key,
    pf.city,
    pf.neighbourhood_cleansed,
    pf.neighbourhood_group_cleansed,
    pf.region_group,
    pf.market_segment,
    pf.coastal_flag,
    pf.urban_flag,
    pf.platform_count,
    pf.snapshot_date,
    pf.price,
    ROUND(pf.projected_occupancy_rate, 4) AS projected_occupancy_rate,
    ROUND(pf.projected_occupied_nights, 4) AS projected_occupied_nights,
    pf.avg_stay_nights,
    pf.projected_bookings_count,
    ROUND(pf.projected_gross_revenue, 4) AS projected_gross_revenue,
    ROUND(pf.projected_gross_revenue / 12.0, 4) AS monthly_projected_gross_revenue,
    pf.projected_platform_fees,
    pf.projected_management_fees,
    pf.projected_cleaning_cost,
    pf.projected_laundry_cost,
    pf.projected_toiletries_cost,
    pf.projected_base_utility_cost,
    pf.projected_variable_utility_cost,
    pf.projected_total_utility_cost,
    ROUND(pf.projected_total_utility_cost / 12.0, 4) AS monthly_projected_total_utility_cost,
    pf.projected_insurance_cost,
    pf.projected_condo_cost,
    pf.projected_other_fixed_cost,
    pf.projected_maintenance_reserve,
    pf.projected_total_operating_cost,
    ROUND(pf.projected_total_operating_cost / 12.0, 4) AS monthly_projected_total_operating_cost,
    ROUND(pf.projected_gross_revenue - pf.projected_total_operating_cost, 4) AS projected_noi,
    ROUND((pf.projected_gross_revenue - pf.projected_total_operating_cost) / 12.0, 4) AS monthly_projected_noi,
    ROUND((pf.projected_gross_revenue - pf.projected_total_operating_cost) / NULLIF(pf.projected_gross_revenue, 0), 4) AS projected_noi_margin,
    ROUND(pf.projected_total_operating_cost / NULLIF(pf.price, 0), 4) AS break_even_occupied_nights,
    ROUND((pf.projected_total_operating_cost / NULLIF(pf.price, 0)) / 365.0, 4) AS break_even_occupancy_rate,
    CASE
        WHEN pf.room_type = 'Entire home/apt'
         AND pf.price BETWEEN 50 AND 450
         AND pf.projected_occupied_nights >= 60
         AND pf.projected_gross_revenue >= 12000
        THEN 1 ELSE 0
    END AS investment_grade_flag,
    pf.load_batch_date,
    pf.created_at
FROM projection_final pf;

DROP PROCEDURE IF EXISTS build_gold_financial_return_for_scenario;
DELIMITER $$
CREATE PROCEDURE build_gold_financial_return_for_scenario(IN p_scenario_name VARCHAR(100))
BEGIN
INSERT INTO gold_fact_financial_return (
    financial_return_key, financial_projection_key, investor_assumption_key, scenario_name, market_type,
    global_property_id, property_id, property_key, host_id, host_key, location_key, city,
    neighbourhood_cleansed, neighbourhood_group_cleansed, region_group, market_segment, coastal_flag,
    urban_flag, investment_grade_flag, financing_vintage_year, applied_asset_discount_pct, applied_annual_interest_rate, estimated_asset_cost, estimated_furnishing_setup_cost,
    estimated_closing_cost, estimated_total_project_capex, estimated_equity_required, estimated_loan_amount,
    monthly_debt_service, annual_debt_service, annual_interest_cost, annual_principal_repayment,
    monthly_interest_cost, monthly_principal_repayment, imi_cost, accounting_cost, licensing_cost,
    ownership_cost_total, taxable_income_estimate, tax_due_estimate, monthly_tax_due_estimate,
    net_income_after_tax, monthly_net_income_after_tax, net_cash_flow_after_debt, monthly_net_cash_flow_after_debt,
    cash_on_cash_return, payback_years, load_batch_date, created_at
)
WITH return_base AS (
    SELECT
        fp.financial_projection_key,
        fp.financial_projection_key AS financial_return_key,
        ia.investor_assumption_key,
        ia.scenario_name,
        fp.market_type,
        fp.global_property_id,
        fp.property_id,
        fp.property_key,
        fp.host_id,
        fp.host_key,
        fp.location_key,
        fp.city,
        fp.neighbourhood_cleansed,
        fp.neighbourhood_group_cleansed,
        fp.region_group,
        fp.market_segment,
        fp.coastal_flag,
        fp.urban_flag,
        fp.investment_grade_flag,
        fp.snapshot_date,
        fp.load_batch_date,
        fp.created_at,
        COALESCE(dp.bedrooms, 1) AS bedrooms,
        COALESCE(dp.accommodates, 2) AS accommodates,
        dh.host_since,
        ia.estimated_asset_cost_base,
        ia.estimated_asset_cost_per_bedroom,
        ia.estimated_asset_cost_per_guest,
        ia.furnishing_setup_cost,
        ia.closing_cost_pct,
        ia.imi_rate_pct,
        ia.annual_accounting_cost,
        ia.annual_licensing_cost,
        ia.effective_tax_rate,
        ia.loan_to_cost_pct,
        ia.annual_interest_rate,
        ia.loan_term_years,
        fp.projected_noi
    FROM gold_fact_financial_projection fp
    INNER JOIN gold_investor_assumptions ia
        ON fp.market_type = ia.market_type
       AND ia.active_flag = 1
       AND ia.scenario_name = p_scenario_name
    LEFT JOIN gold_dim_property dp
        ON fp.property_key = dp.property_key
    LEFT JOIN gold_dim_host dh
        ON fp.host_key = dh.host_key
),
return_vintage AS (
    SELECT
        rb.*,
        CASE
            WHEN rb.host_since IS NULL THEN YEAR(COALESCE(rb.snapshot_date, CURDATE()))
            WHEN YEAR(rb.host_since) <= 2021 THEN 2021
            WHEN YEAR(rb.host_since) >= YEAR(COALESCE(rb.snapshot_date, CURDATE())) THEN YEAR(COALESCE(rb.snapshot_date, CURDATE()))
            ELSE YEAR(rb.host_since)
        END AS financing_vintage_year,
        CASE
            WHEN rb.loan_to_cost_pct = 0 THEN 0.0000
            WHEN rb.host_since IS NULL THEN COALESCE(rb.annual_interest_rate, 0.0283)
            WHEN YEAR(rb.host_since) <= 2021 THEN 0.0185
            WHEN YEAR(rb.host_since) = 2022 THEN 0.0250
            WHEN YEAR(rb.host_since) = 2023 THEN 0.0423
            WHEN YEAR(rb.host_since) = 2024 THEN 0.0368
            WHEN YEAR(rb.host_since) = 2025 THEN 0.0320
            ELSE 0.0283
        END AS applied_annual_interest_rate,
        CASE
            WHEN rb.host_since IS NULL THEN 0.00
            WHEN YEAR(rb.host_since) <= 2021 THEN 0.22
            WHEN YEAR(rb.host_since) = 2022 THEN 0.16
            WHEN YEAR(rb.host_since) = 2023 THEN 0.10
            WHEN YEAR(rb.host_since) = 2024 THEN 0.05
            WHEN YEAR(rb.host_since) = 2025 THEN 0.02
            ELSE 0.00
        END AS applied_asset_discount_pct
    FROM return_base rb
),
return_costs AS (
    SELECT
        rv.*,
        ROUND(
            GREATEST(
                rv.estimated_asset_cost_base * (1 - rv.applied_asset_discount_pct),
                (
                    rv.estimated_asset_cost_base
                    + GREATEST(COALESCE(rv.bedrooms, 1) - 1, 0) * rv.estimated_asset_cost_per_bedroom
                    + GREATEST(COALESCE(rv.accommodates, 2) - 2, 0) * rv.estimated_asset_cost_per_guest
                ) * (1 - rv.applied_asset_discount_pct)
            ),
            4
        ) AS estimated_asset_cost
    FROM return_vintage rv
),
return_capex AS (
    SELECT
        rc.*,
        ROUND(rc.furnishing_setup_cost, 4) AS estimated_furnishing_setup_cost,
        ROUND(rc.estimated_asset_cost * rc.closing_cost_pct, 4) AS estimated_closing_cost,
        ROUND(rc.estimated_asset_cost + rc.furnishing_setup_cost + (rc.estimated_asset_cost * rc.closing_cost_pct), 4) AS estimated_total_project_capex
    FROM return_costs rc
),
return_financing AS (
    SELECT
        rcap.*,
        ROUND(rcap.estimated_total_project_capex * (1 - rcap.loan_to_cost_pct), 4) AS estimated_equity_required,
        ROUND(rcap.estimated_total_project_capex * rcap.loan_to_cost_pct, 4) AS estimated_loan_amount
    FROM return_capex rcap
),
return_payments AS (
    SELECT
        rf.*,
        ROUND(
            CASE
                WHEN rf.applied_annual_interest_rate <= 0 OR rf.loan_term_years <= 0 THEN rf.estimated_loan_amount / NULLIF(rf.loan_term_years * 12, 0)
                ELSE
                    rf.estimated_loan_amount
                    * ((rf.applied_annual_interest_rate / 12.0) * POWER(1 + (rf.applied_annual_interest_rate / 12.0), rf.loan_term_years * 12))
                    / NULLIF(POWER(1 + (rf.applied_annual_interest_rate / 12.0), rf.loan_term_years * 12) - 1, 0)
            END,
            4
        ) AS monthly_debt_service
    FROM return_financing rf
),
return_final AS (
    SELECT
        rp.*,
        ROUND(rp.monthly_debt_service * 12.0, 4) AS annual_debt_service,
        ROUND(rp.estimated_loan_amount * rp.applied_annual_interest_rate, 4) AS annual_interest_cost,
        ROUND(rp.estimated_asset_cost * rp.imi_rate_pct, 4) AS imi_cost,
        ROUND(rp.annual_accounting_cost, 4) AS accounting_cost,
        ROUND(rp.annual_licensing_cost, 4) AS licensing_cost
    FROM return_payments rp
)
SELECT
    (rf.financial_projection_key * 100) + rf.investor_assumption_key AS financial_return_key,
    rf.financial_projection_key,
    rf.investor_assumption_key,
    rf.scenario_name,
    rf.market_type,
    rf.global_property_id,
    rf.property_id,
    rf.property_key,
    rf.host_id,
    rf.host_key,
    rf.location_key,
    rf.city,
    rf.neighbourhood_cleansed,
    rf.neighbourhood_group_cleansed,
    rf.region_group,
    rf.market_segment,
    rf.coastal_flag,
    rf.urban_flag,
    rf.investment_grade_flag,
    rf.financing_vintage_year,
    rf.applied_asset_discount_pct,
    rf.applied_annual_interest_rate,
    rf.estimated_asset_cost,
    rf.estimated_furnishing_setup_cost,
    rf.estimated_closing_cost,
    rf.estimated_total_project_capex,
    rf.estimated_equity_required,
    rf.estimated_loan_amount,
    rf.monthly_debt_service,
    rf.annual_debt_service,
    rf.annual_interest_cost,
    ROUND(GREATEST(rf.annual_debt_service - rf.annual_interest_cost, 0), 4) AS annual_principal_repayment,
    ROUND(rf.annual_interest_cost / 12.0, 4) AS monthly_interest_cost,
    ROUND(GREATEST(rf.annual_debt_service - rf.annual_interest_cost, 0) / 12.0, 4) AS monthly_principal_repayment,
    rf.imi_cost,
    rf.accounting_cost,
    rf.licensing_cost,
    ROUND(rf.imi_cost + rf.accounting_cost + rf.licensing_cost, 4) AS ownership_cost_total,
    ROUND(
        rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
        4
    ) AS taxable_income_estimate,
    ROUND(
        GREATEST(
            rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
            0
        ) * rf.effective_tax_rate,
        4
    ) AS tax_due_estimate,
    ROUND(
        (
            GREATEST(
                rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                0
            ) * rf.effective_tax_rate
        ) / 12.0,
        4
    ) AS monthly_tax_due_estimate,
    ROUND(
        rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost
        - (
            GREATEST(
                rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                0
            ) * rf.effective_tax_rate
        ),
        4
    ) AS net_income_after_tax,
    ROUND(
        (
            rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost
            - (
                GREATEST(
                    rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                    0
                ) * rf.effective_tax_rate
            )
        ) / 12.0,
        4
    ) AS monthly_net_income_after_tax,
    ROUND(
        rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_debt_service
        - (
            GREATEST(
                rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                0
            ) * rf.effective_tax_rate
        ),
        4
    ) AS net_cash_flow_after_debt,
    ROUND(
        (
            rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_debt_service
            - (
                GREATEST(
                    rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                    0
                ) * rf.effective_tax_rate
            )
        ) / 12.0,
        4
    ) AS monthly_net_cash_flow_after_debt,
    ROUND(
        (
            rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_debt_service
            - (
                GREATEST(
                    rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                    0
                ) * rf.effective_tax_rate
            )
        ) / NULLIF(rf.estimated_equity_required, 0),
        4
    ) AS cash_on_cash_return,
    CASE
        WHEN
            (
                rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_debt_service
                - (
                    GREATEST(
                        rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                        0
                    ) * rf.effective_tax_rate
                )
            ) > 0
        THEN ROUND(
            rf.estimated_equity_required / (
                rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_debt_service
                - (
                    GREATEST(
                        rf.projected_noi - (rf.imi_cost + rf.accounting_cost + rf.licensing_cost) - rf.annual_interest_cost,
                        0
                    ) * rf.effective_tax_rate
                )
            ),
            4
        )
        ELSE NULL
    END AS payback_years,
    rf.load_batch_date,
    rf.created_at
FROM return_final rf;
END$$
DELIMITER ;

CALL build_gold_financial_return_for_scenario('cash_purchase');
CALL build_gold_financial_return_for_scenario('loan_50');
CALL build_gold_financial_return_for_scenario('loan_70');
CALL build_gold_financial_return_for_scenario('loan_80');
CALL build_gold_financial_return_for_scenario('loan_90');

DROP PROCEDURE IF EXISTS build_gold_financial_return_for_scenario;

INSERT INTO gold_mart_property_bi (
    property_bi_key, global_property_id, property_id, property_key, host_id, host_key, location_key,
    city, neighbourhood_cleansed, neighbourhood_group_cleansed, region_group, market_segment,
    market_type, coastal_flag, urban_flag, platform_count, host_is_superhost, instant_bookable,
    property_type, room_type, accommodates, bedrooms, beds, bathrooms, price, price_per_guest,
    price_per_bedroom, price_per_bed, availability_30, availability_60, availability_90,
    availability_365, occupancy_rate, occupancy_rate_alt, estimated_occupancy_l365d,
    estimated_revenue_l365d, number_of_reviews, reviews_per_month, review_scores_rating,
    review_scores_cleanliness, review_scores_location, review_scores_value, scenario_name, investor_assumption_key,
    projected_bookings_count, projected_gross_revenue, monthly_projected_gross_revenue, projected_total_utility_cost,
    monthly_projected_total_utility_cost,
    projected_platform_fees, projected_management_fees, projected_cleaning_cost,
    projected_total_operating_cost, monthly_projected_total_operating_cost, projected_noi, monthly_projected_noi,
    projected_noi_margin, break_even_occupancy_rate,
    investment_grade_flag, financing_vintage_year, applied_asset_discount_pct, applied_annual_interest_rate, estimated_total_project_capex, estimated_equity_required,
    estimated_loan_amount, annual_debt_service, monthly_debt_service, annual_interest_cost, annual_principal_repayment, tax_due_estimate, monthly_tax_due_estimate,
    net_income_after_tax, monthly_net_income_after_tax, net_cash_flow_after_debt, monthly_net_cash_flow_after_debt,
    cash_on_cash_return, payback_years, last_review, snapshot_date_key, snapshot_date, load_batch_date_key, load_batch_date, created_at
)
WITH platform_counts AS (
    SELECT property_id, COUNT(DISTINCT platform_key) AS platform_count
    FROM gold_bridge_property_platform
    GROUP BY property_id
)
SELECT
    (fls.snapshot_key * 100) + fr.investor_assumption_key AS property_bi_key,
    fls.global_property_id,
    fls.property_id,
    fls.property_key,
    fls.host_id,
    fls.host_key,
    fls.location_key,
    dl.city,
    dl.neighbourhood_cleansed,
    dl.neighbourhood_group_cleansed,
    dl.region_group,
    dl.market_segment,
    fp.market_type,
    dl.coastal_flag,
    dl.urban_flag,
    COALESCE(pc.platform_count, 1) AS platform_count,
    dh.host_is_superhost,
    dp.instant_bookable,
    dp.property_type,
    dp.room_type,
    dp.accommodates,
    dp.bedrooms,
    dp.beds,
    dp.bathrooms,
    fls.price,
    fls.price_per_guest,
    fls.price_per_bedroom,
    fls.price_per_bed,
    fls.availability_30,
    fls.availability_60,
    fls.availability_90,
    fls.availability_365,
    fls.occupancy_rate,
    fls.occupancy_rate_alt,
    fls.estimated_occupancy_l365d,
    fls.estimated_revenue_l365d,
    fls.number_of_reviews,
    fls.reviews_per_month,
    fls.review_scores_rating,
    fls.review_scores_cleanliness,
    fls.review_scores_location,
    fls.review_scores_value,
    fr.scenario_name,
    fr.investor_assumption_key,
    fp.projected_bookings_count,
    fp.projected_gross_revenue,
    fp.monthly_projected_gross_revenue,
    fp.projected_total_utility_cost,
    fp.monthly_projected_total_utility_cost,
    fp.projected_platform_fees,
    fp.projected_management_fees,
    fp.projected_cleaning_cost,
    fp.projected_total_operating_cost,
    fp.monthly_projected_total_operating_cost,
    fp.projected_noi,
    fp.monthly_projected_noi,
    fp.projected_noi_margin,
    fp.break_even_occupancy_rate,
    fp.investment_grade_flag,
    fr.financing_vintage_year,
    fr.applied_asset_discount_pct,
    fr.applied_annual_interest_rate,
    fr.estimated_total_project_capex,
    fr.estimated_equity_required,
    fr.estimated_loan_amount,
    fr.annual_debt_service,
    fr.monthly_debt_service,
    fr.annual_interest_cost,
    fr.annual_principal_repayment,
    fr.tax_due_estimate,
    fr.monthly_tax_due_estimate,
    fr.net_income_after_tax,
    fr.monthly_net_income_after_tax,
    fr.net_cash_flow_after_debt,
    fr.monthly_net_cash_flow_after_debt,
    fr.cash_on_cash_return,
    fr.payback_years,
    fls.last_review,
    fls.snapshot_date_key,
    fls.snapshot_date,
    fls.load_batch_date_key,
    fls.load_batch_date,
    fls.created_at
FROM gold_fact_listing_snapshot fls
LEFT JOIN gold_dim_property dp ON fls.property_key = dp.property_key
LEFT JOIN gold_dim_location dl ON fls.location_key = dl.location_key
LEFT JOIN gold_dim_host dh ON fls.host_key = dh.host_key
LEFT JOIN platform_counts pc ON fls.property_id = pc.property_id
LEFT JOIN gold_fact_financial_projection fp ON fls.snapshot_key = fp.financial_projection_key
LEFT JOIN gold_fact_financial_return fr ON fls.snapshot_key = fr.financial_projection_key;

INSERT INTO gold_mart_neighbourhood_bi (
    neighbourhood_bi_key, location_key, city, neighbourhood_cleansed, neighbourhood_group_cleansed,
    region_group, market_segment, market_type, scenario_name, coastal_flag, urban_flag, listing_count, avg_price,
    avg_price_per_guest, avg_price_per_bedroom, avg_price_per_bed, avg_occupancy_rate,
    avg_estimated_revenue, avg_projected_bookings_count, avg_projected_gross_revenue, avg_monthly_projected_gross_revenue,
    avg_projected_utility_cost, avg_monthly_projected_utility_cost, avg_projected_operating_cost, avg_monthly_projected_operating_cost, avg_projected_noi,
    avg_monthly_projected_noi,
    avg_projected_noi_margin, total_projected_gross_revenue, total_projected_noi,
    avg_estimated_total_project_capex, avg_estimated_loan_amount, avg_annual_debt_service, avg_monthly_debt_service,
    avg_annual_interest_cost, avg_annual_principal_repayment, avg_tax_due_estimate, avg_monthly_tax_due_estimate,
    avg_net_income_after_tax, avg_monthly_net_income_after_tax, avg_net_cash_flow_after_debt, avg_monthly_net_cash_flow_after_debt, avg_cash_on_cash_return,
    avg_payback_years,
    avg_number_of_reviews, avg_reviews_per_month, avg_review_score_rating,
    avg_review_score_cleanliness, avg_review_score_location, avg_review_score_value,
    avg_platform_count, superhost_share, instant_bookable_share, investment_grade_listing_count,
    avg_availability_30, avg_availability_60, avg_availability_90, avg_availability_365,
    snapshot_date_key, snapshot_date
)
SELECT
    ROW_NUMBER() OVER (ORDER BY snapshot_date_key, location_key, scenario_name) AS neighbourhood_bi_key,
    location_key,
    city,
    neighbourhood_cleansed,
    neighbourhood_group_cleansed,
    region_group,
    market_segment,
    market_type,
    scenario_name,
    coastal_flag,
    urban_flag,
    COUNT(*) AS listing_count,
    ROUND(AVG(price), 4) AS avg_price,
    ROUND(AVG(price_per_guest), 4) AS avg_price_per_guest,
    ROUND(AVG(price_per_bedroom), 4) AS avg_price_per_bedroom,
    ROUND(AVG(price_per_bed), 4) AS avg_price_per_bed,
    ROUND(AVG(occupancy_rate), 4) AS avg_occupancy_rate,
    ROUND(AVG(estimated_revenue_l365d), 4) AS avg_estimated_revenue,
    ROUND(AVG(projected_bookings_count), 4) AS avg_projected_bookings_count,
    ROUND(AVG(projected_gross_revenue), 4) AS avg_projected_gross_revenue,
    ROUND(AVG(monthly_projected_gross_revenue), 4) AS avg_monthly_projected_gross_revenue,
    ROUND(AVG(projected_total_utility_cost), 4) AS avg_projected_utility_cost,
    ROUND(AVG(monthly_projected_total_utility_cost), 4) AS avg_monthly_projected_utility_cost,
    ROUND(AVG(projected_total_operating_cost), 4) AS avg_projected_operating_cost,
    ROUND(AVG(monthly_projected_total_operating_cost), 4) AS avg_monthly_projected_operating_cost,
    ROUND(AVG(projected_noi), 4) AS avg_projected_noi,
    ROUND(AVG(monthly_projected_noi), 4) AS avg_monthly_projected_noi,
    ROUND(AVG(projected_noi_margin), 4) AS avg_projected_noi_margin,
    ROUND(SUM(projected_gross_revenue), 4) AS total_projected_gross_revenue,
    ROUND(SUM(projected_noi), 4) AS total_projected_noi,
    ROUND(AVG(estimated_total_project_capex), 4) AS avg_estimated_total_project_capex,
    ROUND(AVG(estimated_loan_amount), 4) AS avg_estimated_loan_amount,
    ROUND(AVG(annual_debt_service), 4) AS avg_annual_debt_service,
    ROUND(AVG(monthly_debt_service), 4) AS avg_monthly_debt_service,
    ROUND(AVG(annual_interest_cost), 4) AS avg_annual_interest_cost,
    ROUND(AVG(annual_principal_repayment), 4) AS avg_annual_principal_repayment,
    ROUND(AVG(tax_due_estimate), 4) AS avg_tax_due_estimate,
    ROUND(AVG(monthly_tax_due_estimate), 4) AS avg_monthly_tax_due_estimate,
    ROUND(AVG(net_income_after_tax), 4) AS avg_net_income_after_tax,
    ROUND(AVG(monthly_net_income_after_tax), 4) AS avg_monthly_net_income_after_tax,
    ROUND(AVG(net_cash_flow_after_debt), 4) AS avg_net_cash_flow_after_debt,
    ROUND(AVG(monthly_net_cash_flow_after_debt), 4) AS avg_monthly_net_cash_flow_after_debt,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_cash_on_cash_return,
    ROUND(AVG(payback_years), 4) AS avg_payback_years,
    ROUND(AVG(number_of_reviews), 4) AS avg_number_of_reviews,
    ROUND(AVG(reviews_per_month), 4) AS avg_reviews_per_month,
    ROUND(AVG(review_scores_rating), 4) AS avg_review_score_rating,
    ROUND(AVG(review_scores_cleanliness), 4) AS avg_review_score_cleanliness,
    ROUND(AVG(review_scores_location), 4) AS avg_review_score_location,
    ROUND(AVG(review_scores_value), 4) AS avg_review_score_value,
    ROUND(AVG(platform_count), 4) AS avg_platform_count,
    ROUND(AVG(COALESCE(host_is_superhost, 0)), 4) AS superhost_share,
    ROUND(AVG(COALESCE(instant_bookable, 0)), 4) AS instant_bookable_share,
    SUM(COALESCE(investment_grade_flag, 0)) AS investment_grade_listing_count,
    ROUND(AVG(availability_30), 4) AS avg_availability_30,
    ROUND(AVG(availability_60), 4) AS avg_availability_60,
    ROUND(AVG(availability_90), 4) AS avg_availability_90,
    ROUND(AVG(availability_365), 4) AS avg_availability_365,
    snapshot_date_key,
    snapshot_date
FROM gold_mart_property_bi
GROUP BY
    location_key, city, neighbourhood_cleansed, neighbourhood_group_cleansed, region_group,
    market_segment, market_type, scenario_name, coastal_flag, urban_flag, snapshot_date_key, snapshot_date;

INSERT INTO gold_mart_host_bi (
    host_bi_key, host_key, host_id, scenario_name, property_count, city_count, avg_price, avg_occupancy_rate,
    avg_estimated_revenue, avg_projected_gross_revenue, avg_monthly_projected_gross_revenue, avg_projected_utility_cost,
    avg_monthly_projected_utility_cost, avg_projected_operating_cost, avg_monthly_projected_operating_cost, avg_projected_noi, avg_monthly_projected_noi, avg_projected_noi_margin, total_projected_noi,
    avg_estimated_loan_amount, avg_annual_debt_service, avg_monthly_debt_service, avg_annual_interest_cost, avg_annual_principal_repayment,
    avg_tax_due_estimate, avg_monthly_tax_due_estimate, avg_net_income_after_tax, avg_monthly_net_income_after_tax,
    avg_net_cash_flow_after_debt, avg_monthly_net_cash_flow_after_debt, avg_cash_on_cash_return, avg_payback_years, avg_review_score_rating,
    avg_platform_count, superhost_flag, snapshot_date_key, snapshot_date
)
SELECT
    ROW_NUMBER() OVER (ORDER BY snapshot_date_key, host_key, scenario_name) AS host_bi_key,
    host_key,
    host_id,
    scenario_name,
    COUNT(*) AS property_count,
    COUNT(DISTINCT city) AS city_count,
    ROUND(AVG(price), 4) AS avg_price,
    ROUND(AVG(occupancy_rate), 4) AS avg_occupancy_rate,
    ROUND(AVG(estimated_revenue_l365d), 4) AS avg_estimated_revenue,
    ROUND(AVG(projected_gross_revenue), 4) AS avg_projected_gross_revenue,
    ROUND(AVG(monthly_projected_gross_revenue), 4) AS avg_monthly_projected_gross_revenue,
    ROUND(AVG(projected_total_utility_cost), 4) AS avg_projected_utility_cost,
    ROUND(AVG(monthly_projected_total_utility_cost), 4) AS avg_monthly_projected_utility_cost,
    ROUND(AVG(projected_total_operating_cost), 4) AS avg_projected_operating_cost,
    ROUND(AVG(monthly_projected_total_operating_cost), 4) AS avg_monthly_projected_operating_cost,
    ROUND(AVG(projected_noi), 4) AS avg_projected_noi,
    ROUND(AVG(monthly_projected_noi), 4) AS avg_monthly_projected_noi,
    ROUND(AVG(projected_noi_margin), 4) AS avg_projected_noi_margin,
    ROUND(SUM(projected_noi), 4) AS total_projected_noi,
    ROUND(AVG(estimated_loan_amount), 4) AS avg_estimated_loan_amount,
    ROUND(AVG(annual_debt_service), 4) AS avg_annual_debt_service,
    ROUND(AVG(monthly_debt_service), 4) AS avg_monthly_debt_service,
    ROUND(AVG(annual_interest_cost), 4) AS avg_annual_interest_cost,
    ROUND(AVG(annual_principal_repayment), 4) AS avg_annual_principal_repayment,
    ROUND(AVG(tax_due_estimate), 4) AS avg_tax_due_estimate,
    ROUND(AVG(monthly_tax_due_estimate), 4) AS avg_monthly_tax_due_estimate,
    ROUND(AVG(net_income_after_tax), 4) AS avg_net_income_after_tax,
    ROUND(AVG(monthly_net_income_after_tax), 4) AS avg_monthly_net_income_after_tax,
    ROUND(AVG(net_cash_flow_after_debt), 4) AS avg_net_cash_flow_after_debt,
    ROUND(AVG(monthly_net_cash_flow_after_debt), 4) AS avg_monthly_net_cash_flow_after_debt,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_cash_on_cash_return,
    ROUND(AVG(payback_years), 4) AS avg_payback_years,
    ROUND(AVG(review_scores_rating), 4) AS avg_review_score_rating,
    ROUND(AVG(platform_count), 4) AS avg_platform_count,
    MAX(COALESCE(host_is_superhost, 0)) AS superhost_flag,
    snapshot_date_key,
    snapshot_date
FROM gold_mart_property_bi
GROUP BY host_key, host_id, scenario_name, snapshot_date_key, snapshot_date;

INSERT INTO gold_mart_market_bi (
    market_bi_key, city, region_group, market_segment, market_type, scenario_name, room_type, accommodates_bucket,
    listing_count, avg_price, avg_projected_occupied_nights, avg_projected_gross_revenue, avg_monthly_projected_gross_revenue,
    avg_projected_utility_cost, avg_monthly_projected_utility_cost, avg_projected_operating_cost, avg_monthly_projected_operating_cost, avg_projected_noi,
    avg_monthly_projected_noi,
    avg_projected_noi_margin, total_projected_gross_revenue, total_projected_noi,
    avg_estimated_loan_amount, avg_annual_debt_service, avg_monthly_debt_service, avg_annual_interest_cost, avg_annual_principal_repayment,
    avg_tax_due_estimate, avg_monthly_tax_due_estimate, avg_net_income_after_tax, avg_monthly_net_income_after_tax,
    avg_net_cash_flow_after_debt, avg_monthly_net_cash_flow_after_debt, avg_cash_on_cash_return, avg_payback_years, avg_review_score_rating,
    snapshot_date_key, snapshot_date
)
SELECT
    ROW_NUMBER() OVER (ORDER BY snapshot_date_key, city, region_group, market_type, scenario_name, room_type, accommodates_bucket) AS market_bi_key,
    city,
    region_group,
    market_segment,
    market_type,
    scenario_name,
    room_type,
    accommodates_bucket,
    COUNT(*) AS listing_count,
    ROUND(AVG(price), 4) AS avg_price,
    ROUND(AVG(projected_occupied_nights), 4) AS avg_projected_occupied_nights,
    ROUND(AVG(projected_gross_revenue), 4) AS avg_projected_gross_revenue,
    ROUND(AVG(monthly_projected_gross_revenue), 4) AS avg_monthly_projected_gross_revenue,
    ROUND(AVG(projected_total_utility_cost), 4) AS avg_projected_utility_cost,
    ROUND(AVG(monthly_projected_total_utility_cost), 4) AS avg_monthly_projected_utility_cost,
    ROUND(AVG(projected_total_operating_cost), 4) AS avg_projected_operating_cost,
    ROUND(AVG(monthly_projected_total_operating_cost), 4) AS avg_monthly_projected_operating_cost,
    ROUND(AVG(projected_noi), 4) AS avg_projected_noi,
    ROUND(AVG(monthly_projected_noi), 4) AS avg_monthly_projected_noi,
    ROUND(AVG(projected_noi_margin), 4) AS avg_projected_noi_margin,
    ROUND(SUM(projected_gross_revenue), 4) AS total_projected_gross_revenue,
    ROUND(SUM(projected_noi), 4) AS total_projected_noi,
    ROUND(AVG(estimated_loan_amount), 4) AS avg_estimated_loan_amount,
    ROUND(AVG(annual_debt_service), 4) AS avg_annual_debt_service,
    ROUND(AVG(monthly_debt_service), 4) AS avg_monthly_debt_service,
    ROUND(AVG(annual_interest_cost), 4) AS avg_annual_interest_cost,
    ROUND(AVG(annual_principal_repayment), 4) AS avg_annual_principal_repayment,
    ROUND(AVG(tax_due_estimate), 4) AS avg_tax_due_estimate,
    ROUND(AVG(monthly_tax_due_estimate), 4) AS avg_monthly_tax_due_estimate,
    ROUND(AVG(net_income_after_tax), 4) AS avg_net_income_after_tax,
    ROUND(AVG(monthly_net_income_after_tax), 4) AS avg_monthly_net_income_after_tax,
    ROUND(AVG(net_cash_flow_after_debt), 4) AS avg_net_cash_flow_after_debt,
    ROUND(AVG(monthly_net_cash_flow_after_debt), 4) AS avg_monthly_net_cash_flow_after_debt,
    ROUND(AVG(cash_on_cash_return), 4) AS avg_cash_on_cash_return,
    ROUND(AVG(payback_years), 4) AS avg_payback_years,
    ROUND(AVG(review_scores_rating), 4) AS avg_review_score_rating,
    snapshot_date_key,
    snapshot_date
FROM (
    SELECT
        city,
        region_group,
        market_segment,
        market_type,
        scenario_name,
        room_type,
        snapshot_date_key,
        snapshot_date,
        CASE
            WHEN accommodates <= 2 THEN '1-2 guests'
            WHEN accommodates <= 4 THEN '3-4 guests'
            WHEN accommodates <= 6 THEN '5-6 guests'
            ELSE '7+ guests'
        END AS accommodates_bucket,
        price,
        estimated_occupancy_l365d AS projected_occupied_nights,
        projected_gross_revenue,
        monthly_projected_gross_revenue,
        projected_total_utility_cost,
        monthly_projected_total_utility_cost,
        projected_total_operating_cost,
        monthly_projected_total_operating_cost,
        projected_noi,
        monthly_projected_noi,
        projected_noi_margin,
        estimated_loan_amount,
        annual_debt_service,
        monthly_debt_service,
        annual_interest_cost,
        annual_principal_repayment,
        tax_due_estimate,
        monthly_tax_due_estimate,
        net_income_after_tax,
        monthly_net_income_after_tax,
        net_cash_flow_after_debt,
        monthly_net_cash_flow_after_debt,
        cash_on_cash_return,
        payback_years,
        review_scores_rating
    FROM gold_mart_property_bi
    WHERE investment_grade_flag = 1
) benchmark
GROUP BY snapshot_date_key, snapshot_date, city, region_group, market_segment, market_type, scenario_name, room_type, accommodates_bucket;

DROP PROCEDURE IF EXISTS build_gold_financial_distribution_for_scenario;
DELIMITER $$
CREATE PROCEDURE build_gold_financial_distribution_for_scenario(IN p_scenario_name VARCHAR(100))
BEGIN
INSERT INTO gold_mart_financial_distribution_bi (
    distribution_level, city, location_key, neighbourhood_cleansed,
    region_group, market_segment, market_type, scenario_name, room_type, accommodates_bucket,
    listing_count, avg_monthly_net_cash_flow_after_debt, p25_monthly_net_cash_flow_after_debt,
    median_monthly_net_cash_flow_after_debt, p75_monthly_net_cash_flow_after_debt,
    p90_monthly_net_cash_flow_after_debt, top_10pct_avg_monthly_net_cash_flow_after_debt,
    avg_monthly_net_income_after_tax, p25_monthly_net_income_after_tax,
    median_monthly_net_income_after_tax, p75_monthly_net_income_after_tax,
    p90_monthly_net_income_after_tax, avg_cash_on_cash_return, median_cash_on_cash_return,
    p75_cash_on_cash_return, p90_cash_on_cash_return, positive_cash_flow_listing_count,
    positive_cash_flow_share, investment_grade_listing_count, snapshot_date_key, snapshot_date
)
WITH market_base AS (
    SELECT
        CONVERT('market' USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS distribution_level,
        CONVERT(city USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS city,
        CAST(NULL AS SIGNED) AS location_key,
        CONVERT(CAST(NULL AS CHAR(255)) USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS neighbourhood_cleansed,
        CONVERT(region_group USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS region_group,
        CONVERT(market_segment USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS market_segment,
        CONVERT(market_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS market_type,
        CONVERT(scenario_name USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS scenario_name,
        CONVERT(room_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS room_type,
        CONVERT(CASE
            WHEN accommodates <= 2 THEN '1-2 guests'
            WHEN accommodates <= 4 THEN '3-4 guests'
            WHEN accommodates <= 6 THEN '5-6 guests'
            ELSE '7+ guests'
        END USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS accommodates_bucket,
        monthly_net_cash_flow_after_debt,
        monthly_net_income_after_tax,
        cash_on_cash_return,
        investment_grade_flag,
        snapshot_date_key,
        snapshot_date
    FROM gold_mart_property_bi
    WHERE investment_grade_flag = 1
      AND scenario_name = p_scenario_name
),
market_ranked AS (
    SELECT
        mb.*,
        COUNT(*) OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, region_group, market_segment,
                         market_type, scenario_name, room_type, accommodates_bucket
        ) AS group_count,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, region_group, market_segment,
                         market_type, scenario_name, room_type, accommodates_bucket
            ORDER BY monthly_net_cash_flow_after_debt
        ) AS cash_flow_rank,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, region_group, market_segment,
                         market_type, scenario_name, room_type, accommodates_bucket
            ORDER BY monthly_net_income_after_tax
        ) AS net_income_rank,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, region_group, market_segment,
                         market_type, scenario_name, room_type, accommodates_bucket
            ORDER BY cash_on_cash_return
        ) AS return_rank
    FROM market_base mb
),
neighbourhood_base AS (
    SELECT
        CONVERT('neighbourhood' USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS distribution_level,
        CONVERT(city USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS city,
        location_key,
        CONVERT(neighbourhood_cleansed USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS neighbourhood_cleansed,
        CONVERT(region_group USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS region_group,
        CONVERT(market_segment USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS market_segment,
        CONVERT(market_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS market_type,
        CONVERT(scenario_name USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS scenario_name,
        CONVERT(CAST(NULL AS CHAR(100)) USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS room_type,
        CONVERT(CAST(NULL AS CHAR(50)) USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS accommodates_bucket,
        monthly_net_cash_flow_after_debt,
        monthly_net_income_after_tax,
        cash_on_cash_return,
        investment_grade_flag,
        snapshot_date_key,
        snapshot_date
    FROM gold_mart_property_bi
    WHERE investment_grade_flag = 1
      AND scenario_name = p_scenario_name
),
neighbourhood_ranked AS (
    SELECT
        nb.*,
        COUNT(*) OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, location_key, neighbourhood_cleansed,
                         region_group, market_segment, market_type, scenario_name
        ) AS group_count,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, location_key, neighbourhood_cleansed,
                         region_group, market_segment, market_type, scenario_name
            ORDER BY monthly_net_cash_flow_after_debt
        ) AS cash_flow_rank,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, location_key, neighbourhood_cleansed,
                         region_group, market_segment, market_type, scenario_name
            ORDER BY monthly_net_income_after_tax
        ) AS net_income_rank,
        ROW_NUMBER() OVER (
            PARTITION BY snapshot_date_key, snapshot_date, city, location_key, neighbourhood_cleansed,
                         region_group, market_segment, market_type, scenario_name
            ORDER BY cash_on_cash_return
        ) AS return_rank
    FROM neighbourhood_base nb
),
distribution_rows AS (
    SELECT
        distribution_level,
        city,
        location_key,
        neighbourhood_cleansed,
        region_group,
        market_segment,
        market_type,
        scenario_name,
        room_type,
        accommodates_bucket,
        COUNT(*) AS listing_count,
        ROUND(AVG(monthly_net_cash_flow_after_debt), 4) AS avg_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.25) THEN monthly_net_cash_flow_after_debt END), 4) AS p25_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.50) THEN monthly_net_cash_flow_after_debt END), 4) AS median_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.75) THEN monthly_net_cash_flow_after_debt END), 4) AS p75_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.90) THEN monthly_net_cash_flow_after_debt END), 4) AS p90_monthly_net_cash_flow_after_debt,
        ROUND(AVG(CASE WHEN cash_flow_rank >= CEIL(group_count * 0.90) THEN monthly_net_cash_flow_after_debt END), 4) AS top_10pct_avg_monthly_net_cash_flow_after_debt,
        ROUND(AVG(monthly_net_income_after_tax), 4) AS avg_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.25) THEN monthly_net_income_after_tax END), 4) AS p25_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.50) THEN monthly_net_income_after_tax END), 4) AS median_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.75) THEN monthly_net_income_after_tax END), 4) AS p75_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.90) THEN monthly_net_income_after_tax END), 4) AS p90_monthly_net_income_after_tax,
        ROUND(AVG(cash_on_cash_return), 4) AS avg_cash_on_cash_return,
        ROUND(MAX(CASE WHEN return_rank = CEIL(group_count * 0.50) THEN cash_on_cash_return END), 4) AS median_cash_on_cash_return,
        ROUND(MAX(CASE WHEN return_rank = CEIL(group_count * 0.75) THEN cash_on_cash_return END), 4) AS p75_cash_on_cash_return,
        ROUND(MAX(CASE WHEN return_rank = CEIL(group_count * 0.90) THEN cash_on_cash_return END), 4) AS p90_cash_on_cash_return,
        SUM(CASE WHEN monthly_net_cash_flow_after_debt > 0 THEN 1 ELSE 0 END) AS positive_cash_flow_listing_count,
        ROUND(SUM(CASE WHEN monthly_net_cash_flow_after_debt > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 4) AS positive_cash_flow_share,
        SUM(COALESCE(investment_grade_flag, 0)) AS investment_grade_listing_count,
        snapshot_date_key,
        snapshot_date
    FROM market_ranked
    GROUP BY
        distribution_level, city, location_key, neighbourhood_cleansed, region_group, market_segment,
        market_type, scenario_name, room_type, accommodates_bucket, snapshot_date_key, snapshot_date
    UNION ALL
    SELECT
        distribution_level,
        city,
        location_key,
        neighbourhood_cleansed,
        region_group,
        market_segment,
        market_type,
        scenario_name,
        room_type,
        accommodates_bucket,
        COUNT(*) AS listing_count,
        ROUND(AVG(monthly_net_cash_flow_after_debt), 4) AS avg_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.25) THEN monthly_net_cash_flow_after_debt END), 4) AS p25_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.50) THEN monthly_net_cash_flow_after_debt END), 4) AS median_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.75) THEN monthly_net_cash_flow_after_debt END), 4) AS p75_monthly_net_cash_flow_after_debt,
        ROUND(MAX(CASE WHEN cash_flow_rank = CEIL(group_count * 0.90) THEN monthly_net_cash_flow_after_debt END), 4) AS p90_monthly_net_cash_flow_after_debt,
        ROUND(AVG(CASE WHEN cash_flow_rank >= CEIL(group_count * 0.90) THEN monthly_net_cash_flow_after_debt END), 4) AS top_10pct_avg_monthly_net_cash_flow_after_debt,
        ROUND(AVG(monthly_net_income_after_tax), 4) AS avg_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.25) THEN monthly_net_income_after_tax END), 4) AS p25_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.50) THEN monthly_net_income_after_tax END), 4) AS median_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.75) THEN monthly_net_income_after_tax END), 4) AS p75_monthly_net_income_after_tax,
        ROUND(MAX(CASE WHEN net_income_rank = CEIL(group_count * 0.90) THEN monthly_net_income_after_tax END), 4) AS p90_monthly_net_income_after_tax,
        ROUND(AVG(cash_on_cash_return), 4) AS avg_cash_on_cash_return,
        ROUND(MAX(CASE WHEN return_rank = CEIL(group_count * 0.50) THEN cash_on_cash_return END), 4) AS median_cash_on_cash_return,
        ROUND(MAX(CASE WHEN return_rank = CEIL(group_count * 0.75) THEN cash_on_cash_return END), 4) AS p75_cash_on_cash_return,
        ROUND(MAX(CASE WHEN return_rank = CEIL(group_count * 0.90) THEN cash_on_cash_return END), 4) AS p90_cash_on_cash_return,
        SUM(CASE WHEN monthly_net_cash_flow_after_debt > 0 THEN 1 ELSE 0 END) AS positive_cash_flow_listing_count,
        ROUND(SUM(CASE WHEN monthly_net_cash_flow_after_debt > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 4) AS positive_cash_flow_share,
        SUM(COALESCE(investment_grade_flag, 0)) AS investment_grade_listing_count,
        snapshot_date_key,
        snapshot_date
    FROM neighbourhood_ranked
    GROUP BY
        distribution_level, city, location_key, neighbourhood_cleansed, region_group, market_segment,
        market_type, scenario_name, room_type, accommodates_bucket, snapshot_date_key, snapshot_date
)
SELECT
    distribution_level,
    city,
    location_key,
    neighbourhood_cleansed,
    region_group,
    market_segment,
    market_type,
    scenario_name,
    room_type,
    accommodates_bucket,
    listing_count,
    avg_monthly_net_cash_flow_after_debt,
    p25_monthly_net_cash_flow_after_debt,
    median_monthly_net_cash_flow_after_debt,
    p75_monthly_net_cash_flow_after_debt,
    p90_monthly_net_cash_flow_after_debt,
    top_10pct_avg_monthly_net_cash_flow_after_debt,
    avg_monthly_net_income_after_tax,
    p25_monthly_net_income_after_tax,
    median_monthly_net_income_after_tax,
    p75_monthly_net_income_after_tax,
    p90_monthly_net_income_after_tax,
    avg_cash_on_cash_return,
    median_cash_on_cash_return,
    p75_cash_on_cash_return,
    p90_cash_on_cash_return,
    positive_cash_flow_listing_count,
    positive_cash_flow_share,
    investment_grade_listing_count,
    snapshot_date_key,
    snapshot_date
FROM distribution_rows;
END$$
DELIMITER ;

CALL build_gold_financial_distribution_for_scenario('cash_purchase');
CALL build_gold_financial_distribution_for_scenario('loan_50');
CALL build_gold_financial_distribution_for_scenario('loan_70');
CALL build_gold_financial_distribution_for_scenario('loan_80');
CALL build_gold_financial_distribution_for_scenario('loan_90');

DROP PROCEDURE IF EXISTS build_gold_financial_distribution_for_scenario;

SET FOREIGN_KEY_CHECKS = 1;
SET SQL_SAFE_UPDATES = 1;
