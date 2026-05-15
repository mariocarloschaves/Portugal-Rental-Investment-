-- 03_validate_portugal_rental_warehouse_lean.sql

USE portugal_rental_warehouse;

SELECT 'bronze_airbnb_listings_raw' AS table_name, COUNT(*) AS row_count, 40255 AS expected_rows FROM `bronze_airbnb_listings_raw`;
SELECT 'bronze_airbnb_neighbourhoods_raw' AS table_name, COUNT(*) AS row_count, 307 AS expected_rows FROM `bronze_airbnb_neighbourhoods_raw`;
SELECT 'bronze_airbnb_neighbourhood_geo_raw' AS table_name, COUNT(*) AS row_count, 350 AS expected_rows FROM `bronze_airbnb_neighbourhood_geo_raw`;
SELECT 'bronze_booking_listings_raw' AS table_name, COUNT(*) AS row_count, 0 AS expected_rows FROM `bronze_booking_listings_raw`;
SELECT 'bronze_vrbo_listings_raw' AS table_name, COUNT(*) AS row_count, 19 AS expected_rows FROM `bronze_vrbo_listings_raw`;
SELECT 'silver_clean_master_listings' AS table_name, COUNT(*) AS row_count, 40255 AS expected_rows FROM `silver_clean_master_listings`;
SELECT 'silver_location_labels' AS table_name, COUNT(*) AS row_count, 294 AS expected_rows FROM `silver_location_labels`;
SELECT 'silver_build_summary' AS table_name, COUNT(*) AS row_count, 1 AS expected_rows FROM `silver_build_summary`;
SELECT 'silver_column_profile' AS table_name, COUNT(*) AS row_count, 57 AS expected_rows FROM `silver_column_profile`;
SELECT 'silver_null_audit' AS table_name, COUNT(*) AS row_count, 57 AS expected_rows FROM `silver_null_audit`;
SELECT 'gold_dim_host' AS table_name, COUNT(*) AS row_count, 15297 AS expected_rows FROM `gold_dim_host`;
SELECT 'gold_dim_location' AS table_name, COUNT(*) AS row_count, 294 AS expected_rows FROM `gold_dim_location`;
SELECT 'gold_dim_neighbourhood_geo' AS table_name, COUNT(*) AS row_count, 336 AS expected_rows FROM `gold_dim_neighbourhood_geo`;
SELECT 'gold_dim_platform' AS table_name, COUNT(*) AS row_count, 3 AS expected_rows FROM `gold_dim_platform`;
SELECT 'gold_dim_property' AS table_name, COUNT(*) AS row_count, 40255 AS expected_rows FROM `gold_dim_property`;
SELECT 'gold_bridge_property_platform' AS table_name, COUNT(*) AS row_count, 40255 AS expected_rows FROM `gold_bridge_property_platform`;
SELECT 'gold_fact_listing_snapshot' AS table_name, COUNT(*) AS row_count, 40255 AS expected_rows FROM `gold_fact_listing_snapshot`;
