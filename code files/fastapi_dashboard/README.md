# FastAPI Rental Forecast Dashboard

This local app turns the deployed ML models into a first-year rental scenario simulator for a Portugal short-term rental property.
It also adds a practical 3-year occupancy ramp-up scenario and pricing guidance on top of the Year 1 ML forecast.

## Active Models

- `nightly_price_deployment_model_v2.joblib`
- `occupancy_deployment_model_v3.joblib`

Occupancy deployment model V3 uses the dynamic top-model blend:

- `I_dynamic_top_model_blend`

## Current Model Scores

Price deployment model v2:

- `R2 = 0.700360`
- `RMSE = 40.065582`
- `MAE = 27.245058`

Occupancy deployment model v3:

- `R2 = 0.738184`
- `RMSE = 0.083477`
- `MAE = 0.058549`

## Financial Logic

The dashboard follows this structure:

```text
Gross revenue - operating costs = NOI
NOI - bank payment - tax = final net
```

Operating costs include:

- platform fees
- cleaning
- laundry
- toiletries
- utilities
- insurance
- condo
- maintenance
- accounting
- licensing
- IMI/property tax

Tax is estimated on NOI after the interest deduction.

## 3-Year Occupancy Ramp-Up Scenario

- Year 1 is the ML model forecast.
- Years 2 and 3 are scenario assumptions toward a stabilized market occupancy target.
- These are scenario targets, not guaranteed outcomes.
- The scenario assumes high-quality hosting, strong reviews, good availability, and pricing discipline.

Stabilized occupancy targets:

- Urban: `62%`
- City: `65%`
- Beach: `67%`

## Pricing Guidance

- The app compares the current predicted occupancy with the stabilized market target.
- It then suggests whether the host should stay competitive, stay disciplined, or cautiously test higher prices.
- Price guidance is practical, not guaranteed.

## What The Dashboard Shows

- model info
- forecast strength
- likely range
- wider stress-test range
- pricing guidance
- 3-year occupancy ramp-up scenario
- where the money goes
- taxes, simply explained
- compare financing options
- dynamic city / region / neighbourhood filters
- glossary
- independent scrolling input and dashboard panels on desktop

## Product Assumptions

- The property is self-managed.
- `management_fee_pct = 0`.
- The host is treated as a strong operator and superhost-style operator.
- `platform_count = 1`.
- Availability is treated as fully open for the year.
- Reviews are estimated from predicted bookings using a 65% review capture rate.
- The forecast is a simplified scenario simulator, not legal or tax advice.
- The 3-year scenario is not a guarantee. It assumes high standards, strong reviews, good availability, and careful pricing.

## Important Runtime Note

The deployed artifacts were saved from the Python 3.13 ML environment with:

- `numpy 2.4.1`
- `scikit-learn 1.8.0`

Run the dashboard with:

```powershell
python3.13 -m uvicorn main:app --reload
```

Do not start it with the older Anaconda `python` command.

## Run Locally

From the project root:

```powershell
cd "code files\fastapi_dashboard"
python3.13 -m uvicorn main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## API Endpoints

- `/health`
- `/api/options`
- `/api/predict`

## Final Note

This dashboard is a scenario simulator. It gives statistical support, not guaranteed investment returns.
