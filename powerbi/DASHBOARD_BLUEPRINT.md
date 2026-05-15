# Power BI Dashboard Blueprint

We will build exactly two Power BI dashboards:

1. Current State Of The Portuguese Rental Market
2. Financial State Of The Portuguese Rental Market

The purpose is not to create many dashboards or many disconnected pages. The goal is one clean market dashboard and one clean financial dashboard.

## 1. Power BI Connection To MySQL

Use Power BI Desktop.

1. Open `Get data`.
2. Choose `MySQL database`.
3. Server: `localhost`
4. Database: `portugal_rental_warehouse`
5. Data connectivity mode: `Import`
6. Authentication: `Database`
7. Username: `root`
8. Password: your local MySQL password.
9. Click `Transform Data` before loading.

Import these tables:

- `gold_dim_date`
- `gold_dim_financing_scenario`
- `gold_investor_assumptions`
- `gold_fact_financial_projection`
- `gold_fact_financial_return`
- `gold_mart_property_bi`
- `gold_mart_market_bi`
- `gold_mart_neighbourhood_bi`
- `gold_mart_financial_distribution_bi`

Optional later:

- `gold_mart_host_bi`

Do not import the raw Bronze or Silver tables for the dashboard. The dashboard should use Gold tables only: the Gold facts for detail/drill-through and the Gold marts for visuals.

## 2. Data Model

Use `gold_dim_date` as the date table.

Relationships:

- `gold_dim_date[date_key]` 1:* `gold_mart_property_bi[snapshot_date_key]`
- `gold_dim_date[date_key]` 1:* `gold_mart_market_bi[snapshot_date_key]`
- `gold_dim_date[date_key]` 1:* `gold_mart_neighbourhood_bi[snapshot_date_key]`
- `gold_dim_date[date_key]` 1:* `gold_mart_financial_distribution_bi[snapshot_date_key]`
- `gold_dim_date[date_key]` 1:* `gold_fact_financial_projection[snapshot_date_key]`
- `gold_dim_financing_scenario[scenario_name]` 1:* `gold_mart_property_bi[scenario_name]`
- `gold_dim_financing_scenario[scenario_name]` 1:* `gold_mart_market_bi[scenario_name]`
- `gold_dim_financing_scenario[scenario_name]` 1:* `gold_mart_neighbourhood_bi[scenario_name]`
- `gold_dim_financing_scenario[scenario_name]` 1:* `gold_mart_financial_distribution_bi[scenario_name]`
- `gold_dim_financing_scenario[scenario_name]` 1:* `gold_fact_financial_return[scenario_name]`
- `gold_dim_financing_scenario[scenario_name]` 1:* `gold_investor_assumptions[scenario_name]`
- `gold_fact_financial_projection[financial_projection_key]` 1:* `gold_fact_financial_return[financial_projection_key]`

Keep the model simple. Do not directly join the mart tables to each other unless needed. Use each mart for its own visual level:

- Property-level visuals: `gold_mart_property_bi`
- Market/segment visuals: `gold_mart_market_bi`
- Location/neighbourhood visuals: `gold_mart_neighbourhood_bi`
- Percentile/top-performer visuals: `gold_mart_financial_distribution_bi`

Important: from `v14` onward, the financial marts contain one row per property per financing scenario. Always include a `scenario_name` slicer from `gold_dim_financing_scenario`. For the current market dashboard, use one default scenario, usually `cash_purchase`, or use distinct-count measures so listing counts are not multiplied by five.

## Dashboard 1 - Current State Of The Portuguese Rental Market

### Purpose

Show the current state of the Portuguese listings rental market and identify the most promising locations and why.

This dashboard answers:

- Where are the listings concentrated?
- Which cities/regions/neighbourhoods have stronger price and occupancy?
- Which market segments look healthier?
- Which locations look promising before considering full investor financing?

### Main Filters

Top filter bar:

- Snapshot date
- City
- Region group
- Market type
- Financing scenario
- Room type
- Accommodates bucket
- Investment grade flag

### Layout

```text
+----------------------------------------------------------------------------------+
| Current State Of The Portuguese Rental Market                                     |
| [Snapshot Date] [City] [Region] [Market Type] [Scenario] [Room] [Guests] [Grade] |
+----------------------------------------------------------------------------------+
| KPI Cards                                                                        |
| Listings | Avg Nightly Price | Avg Occupancy | Avg Revenue | Investment Listings |
+----------------------------------------------------------------------------------+
| Listings By City And Market Type        | Price vs Occupancy                     |
| Stacked bar chart                        | Bubble scatter, size = listing count  |
+-----------------------------------------+----------------------------------------+
| Most Promising Locations                                                         |
| Ranking table by neighbourhood/region: listings, price, occupancy, revenue        |
+----------------------------------------------------------------------------------+
| Market Segment Matrix                                                             |
| City | Region | Market Type | Room Type | Guests | Listings | Price | Occupancy |
+----------------------------------------------------------------------------------+
```

### Recommended Visuals

- KPI cards: listing count, average nightly price, average occupancy, average annual gross revenue, investment-grade listing count.
- Stacked bar: listing count by `city` and `market_type`.
- Scatter: `avg_price` vs `avg_occupancy_rate`, bubble size by `listing_count`, color by `market_type`.
- Ranking table: `city`, `neighbourhood_cleansed`, `region_group`, `market_type`, `listing_count`, `avg_price`, `avg_occupancy_rate`, `avg_estimated_revenue`.
- Matrix: `city`, `region_group`, `market_type`, `room_type`, `accommodates_bucket`.

### Main Tables

Use:

- `gold_mart_market_bi` for market segment comparison.
- `gold_mart_neighbourhood_bi` for promising location ranking.
- `gold_mart_property_bi` only for detailed listing-level counts if needed.

### Core DAX Measures

```DAX
Listings =
DISTINCTCOUNT(gold_mart_property_bi[property_id])

Investment Grade Listings =
CALCULATE(
    DISTINCTCOUNT(gold_mart_property_bi[property_id]),
    gold_mart_property_bi[investment_grade_flag] = 1
)

Avg Nightly Price =
AVERAGE(gold_mart_property_bi[price])

Avg Occupancy Rate =
AVERAGE(gold_mart_property_bi[occupancy_rate])

Avg Annual Gross Revenue =
AVERAGE(gold_mart_property_bi[projected_gross_revenue])
```

## Dashboard 2 - Financial State Of The Portuguese Rental Market

### Purpose

Show the financial state of the Portuguese rental market from an investor perspective.

This dashboard answers:

- Which locations produce stronger monthly net income?
- Which segments have better NOI?
- Where is bank payment pressure too high?
- Which locations have stronger cash-on-equity return?
- Which markets are promising after operating costs, financing, and taxes?

### Main Filters

Top filter bar:

- Snapshot date
- City
- Region group
- Market type
- Financing scenario
- Room type
- Accommodates bucket
- Investment grade flag

### Layout

```text
+----------------------------------------------------------------------------------+
| Financial State Of The Portuguese Rental Market                                   |
| [Snapshot Date] [City] [Region] [Market Type] [Scenario] [Room] [Guests] [Grade] |
+----------------------------------------------------------------------------------+
| KPI Cards                                                                        |
| Monthly Gross Revenue | Monthly NOI | Bank Payment | Tax | Net Income | Return   |
+----------------------------------------------------------------------------------+
| Monthly Financial Waterfall              | Net Income By Location                 |
| Gross -> Costs -> NOI -> Bank -> Tax     | Bar chart by city/region/market type  |
+------------------------------------------+---------------------------------------+
| Cash-On-Equity vs Monthly Net Income                                             |
| Scatter, size = listing count, color = market type                                |
+----------------------------------------------------------------------------------+
| Financial Segment Matrix                                                          |
| City | Region | Market | Room | Guests | Gross | NOI | Bank | Tax | Net Income   |
+----------------------------------------------------------------------------------+
```

### Recommended Visuals

- KPI cards: average monthly gross revenue, average monthly NOI, average monthly bank payment, average monthly tax, average monthly net income after tax, average cash-on-equity return.
- Waterfall: monthly gross revenue -> operating costs -> NOI -> bank payment -> taxes -> net income after tax.
- Bar chart: average monthly net income after tax by city and market type.
- Scatter: average cash-on-equity return vs average monthly net income after tax, bubble size by listing count.
- Matrix: `city`, `region_group`, `market_type`, `room_type`, `accommodates_bucket`, with all financial metrics.
- Percentile table: use `gold_mart_financial_distribution_bi` to compare median, p75, p90, top 10% monthly cash flow, and positive cash-flow share by scenario.

### Main Tables

Use:

- `gold_mart_market_bi` as the main table for financial segment benchmarking.
- `gold_mart_neighbourhood_bi` for financial location ranking.
- `gold_mart_financial_distribution_bi` for median, percentile, and top-performer views.
- `gold_mart_property_bi` for property-level detail if needed.

### Core DAX Measures

```DAX
Avg Monthly Gross Revenue =
AVERAGE(gold_mart_property_bi[monthly_projected_gross_revenue])

Avg Monthly NOI =
AVERAGE(gold_mart_property_bi[monthly_projected_noi])

Avg Monthly Bank Payment =
AVERAGE(gold_mart_property_bi[monthly_debt_service])

Avg Monthly Tax =
AVERAGE(gold_mart_property_bi[monthly_tax_due_estimate])

Avg Monthly Net Income After Tax =
AVERAGE(gold_mart_property_bi[monthly_net_income_after_tax])

Avg Cash On Equity Return =
AVERAGE(gold_mart_property_bi[cash_on_cash_return])

Avg Payback Years =
AVERAGE(gold_mart_property_bi[payback_years])
```

## Build Order

1. Connect Power BI to MySQL.
2. Import only the Gold BI tables.
3. Build relationships with `gold_dim_date`.
4. Build Dashboard 1 first: current market state.
5. Build Dashboard 2 second: financial market state.
6. Validate a few averages against MySQL.
7. Then move to the final project stack: model inference, backend/API, and Wix deployment.

## Final Project Stack After Dashboards

After the two dashboards are built:

1. Finalize model inference scripts for price and occupancy.
2. Build a backend/API that loads the deployment model artifacts.
3. Connect the backend/API to Wix.
4. Create the user-facing flow:
   - user enters property/location/details
   - model predicts fair nightly price
   - model predicts occupancy
   - financial layer estimates revenue, costs, debt payment, tax, and net income
