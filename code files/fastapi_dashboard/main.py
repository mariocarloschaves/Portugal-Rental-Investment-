from __future__ import annotations

import json
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
warnings.filterwarnings("ignore", message="Pandas requires version")

import joblib
import numpy as np
import pandas as pd
import sklearn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from starlette.templating import Jinja2Templates


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[1]
DEPLOYMENT_CODE_DIR = PROJECT_ROOT / "code files" / "ml" / "deployment_models"
ARTIFACT_DIR = PROJECT_ROOT / "code files" / "data" / "gold" / "modeling" / "deployment_models"

sys.path.insert(0, str(DEPLOYMENT_CODE_DIR))

PRICE_MODEL_PATH = ARTIFACT_DIR / "nightly_price_deployment_model_v2.joblib"
OCCUPANCY_MODEL_PATH = ARTIFACT_DIR / "occupancy_deployment_model_v3.joblib"
PRICE_METADATA_PATH = ARTIFACT_DIR / "nightly_price_deployment_model_v2_metadata.json"
OCCUPANCY_METADATA_PATH = ARTIFACT_DIR / "occupancy_deployment_model_v3_metadata.json"


SCENARIO_ORDER = ["cash_purchase", "loan_50", "loan_70", "loan_80", "loan_90"]
SCENARIO_LABELS = {
    "cash_purchase": "Cash purchase",
    "loan_50": "50% bank loan",
    "loan_70": "70% bank loan",
    "loan_80": "80% bank loan",
    "loan_90": "90% bank loan",
}
LOAN_TO_COST = {
    "cash_purchase": 0.00,
    "loan_50": 0.50,
    "loan_70": 0.70,
    "loan_80": 0.80,
    "loan_90": 0.90,
}

LOCATION_OPTIONS: dict[str, dict[str, Any]] = {
    "lisbon": {
        "regions": {
            "lisbon_inland": {
                "market_types": ["urban", "city"],
                "neighbourhoods": [
                    "baixa",
                    "alfama",
                    "chiado",
                    "bairro alto",
                    "santa maria maior",
                ],
            },
            "lisbon_coast": {
                "market_types": ["beach", "city"],
                "neighbourhoods": [
                    "cascais",
                    "estoril",
                    "carcavelos",
                ],
            },
        }
    },
    "porto": {
        "regions": {
            "porto_north": {
                "market_types": ["urban", "city"],
                "neighbourhoods": [
                    "bonfim",
                    "cedofeita",
                    "ribeira",
                    "campanha",
                ],
            }
        }
    },
    "setubal": {
        "regions": {
            "setubal_coast": {
                "market_types": ["beach", "city"],
                "neighbourhoods": [
                    "setubal",
                    "sesimbra",
                    "troia",
                ],
            }
        }
    },
    "faro": {
        "regions": {
            "algarve_coast": {
                "market_types": ["beach", "city"],
                "neighbourhoods": [
                    "faro",
                    "albufeira",
                    "lagos",
                    "portimao",
                    "vilamoura",
                ],
            }
        }
    },
    "coimbra": {
        "regions": {
            "coimbra_central": {
                "market_types": ["urban", "city"],
                "neighbourhoods": [
                    "coimbra",
                    "solum",
                    "baixa de coimbra",
                    "santa clara",
                ],
            }
        }
    },
    "braga": {
        "regions": {
            "braga_north": {
                "market_types": ["urban", "city"],
                "neighbourhoods": [
                    "braga",
                    "sao vicente",
                    "maximinos",
                    "nogueiro",
                ],
            }
        }
    },
    "aveiro": {
        "regions": {
            "aveiro_central": {
                "market_types": ["city", "beach"],
                "neighbourhoods": [
                    "aveiro",
                    "gloria",
                    "barra",
                    "costa nova",
                ],
            }
        }
    },
}

PROPERTY_TYPES = [
    "Entire rental unit",
    "Entire condo",
    "Entire home",
    "Entire villa",
    "Entire loft",
    "Tiny home",
]

ROOM_TYPES = [
    "Entire home/apt",
    "Private room",
    "Hotel room",
    "Shared room",
]

FINANCING_SCENARIOS = [
    {"value": scenario_name, "label": SCENARIO_LABELS[scenario_name]}
    for scenario_name in SCENARIO_ORDER
]

AMENITIES = [
    {"name": "instant_bookable", "label": "Instant bookable"},
    {"name": "has_wifi", "label": "Wi-Fi"},
    {"name": "has_aircon", "label": "Air conditioning"},
    {"name": "has_pool", "label": "Pool"},
    {"name": "has_parking", "label": "Parking"},
    {"name": "has_washer", "label": "Washer"},
    {"name": "has_dryer", "label": "Dryer"},
    {"name": "has_kitchen", "label": "Kitchen"},
    {"name": "has_tv", "label": "TV"},
    {"name": "has_heating", "label": "Heating"},
]

LIMITED_SUPPORT_CITIES = {"coimbra", "braga", "aveiro"}

OPERATING_ASSUMPTIONS = {
    "urban": {
        "avg_stay_nights": 4.5,
        "platform_fee_pct": 0.03,
        "management_fee_pct": 0.00,
        "base_monthly_electricity": 45.0,
        "electricity_per_occupied_night": 1.00,
        "base_monthly_water": 15.0,
        "water_per_occupied_night": 0.35,
        "internet_monthly": 35.0,
        "laundry_per_turnover": 10.0,
        "toiletries_per_turnover": 3.0,
        "cleaning_cost_per_turnover": 35.0,
        "monthly_insurance": 15.0,
        "monthly_condo_fee": 20.0,
        "monthly_other_fixed_cost": 15.0,
        "maintenance_reserve_pct": 0.03,
    },
    "city": {
        "avg_stay_nights": 5.2,
        "platform_fee_pct": 0.03,
        "management_fee_pct": 0.00,
        "base_monthly_electricity": 50.0,
        "electricity_per_occupied_night": 1.20,
        "base_monthly_water": 18.0,
        "water_per_occupied_night": 0.40,
        "internet_monthly": 35.0,
        "laundry_per_turnover": 11.0,
        "toiletries_per_turnover": 3.5,
        "cleaning_cost_per_turnover": 40.0,
        "monthly_insurance": 15.0,
        "monthly_condo_fee": 25.0,
        "monthly_other_fixed_cost": 15.0,
        "maintenance_reserve_pct": 0.03,
    },
    "beach": {
        "avg_stay_nights": 6.3,
        "platform_fee_pct": 0.03,
        "management_fee_pct": 0.00,
        "base_monthly_electricity": 55.0,
        "electricity_per_occupied_night": 1.50,
        "base_monthly_water": 20.0,
        "water_per_occupied_night": 0.50,
        "internet_monthly": 35.0,
        "laundry_per_turnover": 12.0,
        "toiletries_per_turnover": 4.0,
        "cleaning_cost_per_turnover": 45.0,
        "monthly_insurance": 16.0,
        "monthly_condo_fee": 30.0,
        "monthly_other_fixed_cost": 20.0,
        "maintenance_reserve_pct": 0.04,
    },
}

INVESTOR_ASSUMPTIONS = {
    "urban": {"closing_cost_pct": 0.05, "imi_rate_pct": 0.0035, "annual_interest_rate": 0.0375},
    "city": {"closing_cost_pct": 0.05, "imi_rate_pct": 0.0038, "annual_interest_rate": 0.0375},
    "beach": {"closing_cost_pct": 0.05, "imi_rate_pct": 0.0038, "annual_interest_rate": 0.0390},
}

ANNUAL_ACCOUNTING_COST = 1020.0
ANNUAL_LICENSING_COST = 300.0
EFFECTIVE_TAX_RATE = 0.17
LOAN_TERM_YEARS = 30
REVIEW_CAPTURE_RATE = 0.65
MARKET_STABILIZED_OCCUPANCY_TARGET = {
    "urban": 0.62,
    "city": 0.65,
    "beach": 0.67,
}

PRICE_RMSE_68 = 40.06558237044478
OCCUPANCY_RMSE_68 = 0.08347654287324272
PRICE_RMSE_95 = 1.96 * PRICE_RMSE_68
OCCUPANCY_RMSE_95 = 1.96 * OCCUPANCY_RMSE_68

PRICE_MODEL_R2 = 0.700360
PRICE_MODEL_RMSE = 40.065582
PRICE_MODEL_MAE = 27.245058

OCCUPANCY_MODEL_R2 = 0.738184
OCCUPANCY_MODEL_RMSE = 0.083477
OCCUPANCY_MODEL_MAE = 0.058549

INTERPRETATION_NOTE = (
    "The models explain about 70%+ of the historical price and occupancy patterns. "
    "That is strong for real-world property data, but this is still a forecast, not a guarantee."
)

CONFIDENCE_NOTE = (
    "Likely range uses +/-1 model error. Wider range uses +/-1.96 model error. "
    "This helps show downside and upside, but it is not a guarantee."
)


def version_tuple(raw: str) -> tuple[int, ...]:
    parts = []
    for token in raw.split("."):
        digits = "".join(character for character in token if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


class PropertyForecastInput(BaseModel):
    city: str = Field(..., min_length=2, max_length=100)
    neighbourhood_cleansed: str = Field(..., min_length=2, max_length=255)
    region_group: str = Field(..., min_length=2, max_length=255)
    market_type: Literal["urban", "city", "beach"]
    property_type: str = Field(..., min_length=2, max_length=255)
    room_type: str = Field(default="Entire home/apt", min_length=2, max_length=100)
    accommodates: int = Field(..., ge=1, le=20)
    bedrooms: float = Field(..., ge=0, le=20)
    beds: float = Field(..., ge=0, le=30)
    bathrooms: float = Field(..., ge=0, le=20)
    minimum_nights: int = Field(..., ge=1, le=365)
    maximum_nights: int = Field(..., ge=1, le=1125)
    instant_bookable: bool = True
    has_wifi: bool = True
    has_aircon: bool = False
    has_pool: bool = False
    has_parking: bool = False
    has_washer: bool = True
    has_dryer: bool = False
    has_kitchen: bool = True
    has_tv: bool = True
    has_heating: bool = True
    property_acquisition_cost: float = Field(..., gt=0, le=5_000_000)
    furnishing_setup_cost: float = Field(..., ge=0, le=500_000)
    financing_scenario: Literal["cash_purchase", "loan_50", "loan_70", "loan_80", "loan_90"]

    @model_validator(mode="after")
    def validate_property_shape(self) -> "PropertyForecastInput":
        if self.maximum_nights < self.minimum_nights:
            raise ValueError("Maximum nights must be greater than or equal to minimum nights.")
        if self.beds == 0 and self.accommodates > 1:
            raise ValueError("Beds must be greater than zero when the property accommodates guests.")
        if self.bedrooms > self.accommodates:
            raise ValueError("Bedrooms cannot be higher than the number of guests accommodated.")
        if self.bathrooms <= 0:
            raise ValueError("Bathrooms must be greater than zero.")
        if self.bedrooms < 0 or self.beds < 0 or self.bathrooms <= 0:
            raise ValueError("Bedrooms, beds, and bathrooms must be realistic positive values.")
        return self


@dataclass
class AutoAssumptions:
    number_of_reviews: float = 0.0
    reviews_per_month: float = 0.0
    review_scores_rating: float = 4.8
    review_scores_cleanliness: float = 4.8
    review_scores_location: float = 4.8
    review_scores_value: float = 4.7
    host_is_superhost: int = 1
    platform_count: int = 1
    host_response_rate: float = 100.0
    host_acceptance_rate: float = 100.0
    host_listings_count: int = 1
    host_total_listings_count: int = 1
    host_tenure_days: float = 365.0

    @property
    def host_tenure_years(self) -> float:
        return self.host_tenure_days / 365.25


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def clean_text(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_location(value: str) -> str:
    return clean_text(value).lower()


def round_money(value: float | int | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def safe_ratio_feature(numerator: float | None, denominator: float | None) -> float:
    if denominator is None or pd.isna(denominator) or float(denominator) == 0:
        return np.nan
    if numerator is None or pd.isna(numerator):
        return np.nan
    return float(numerator) / float(denominator)


def safe_div_value(numerator: float | None, denominator: float | None) -> float | None:
    if denominator is None or pd.isna(denominator) or float(denominator) == 0:
        return None
    if numerator is None or pd.isna(numerator):
        return None
    return float(numerator) / float(denominator)


def ensure_columns(frame: pd.DataFrame, columns: list[str] | None) -> pd.DataFrame:
    if not columns:
        return frame.copy()
    output = frame.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = np.nan
    return output


def format_options_payload() -> dict[str, Any]:
    return {
        "locations": LOCATION_OPTIONS,
        "property_types": PROPERTY_TYPES,
        "room_types": ROOM_TYPES,
        "financing_scenarios": FINANCING_SCENARIOS,
        "amenities": AMENITIES,
    }


def validate_location_configuration(payload: PropertyForecastInput) -> None:
    city_key = normalize_location(payload.city)
    if city_key not in LOCATION_OPTIONS:
        raise ValueError("Please choose one of the supported cities.")

    region_key = normalize_location(payload.region_group)
    city_entry = LOCATION_OPTIONS[city_key]
    if region_key not in city_entry["regions"]:
        raise ValueError("The selected region does not belong to this city.")

    region_entry = city_entry["regions"][region_key]
    neighbourhood_key = normalize_location(payload.neighbourhood_cleansed)
    if neighbourhood_key not in region_entry["neighbourhoods"]:
        raise ValueError("The selected neighbourhood does not belong to this city/region.")

    if payload.market_type not in region_entry["market_types"]:
        raise ValueError("The selected market type does not match the selected city/region.")


def evidence_rating() -> str:
    if PRICE_MODEL_R2 >= 0.70 and OCCUPANCY_MODEL_R2 >= 0.70:
        return "Strong"
    if PRICE_MODEL_R2 >= 0.50 and OCCUPANCY_MODEL_R2 >= 0.50:
        return "Moderate"
    return "Limited"


def predict_price_target(pipeline: Any, frame: pd.DataFrame, features: list[str], target_mode: str) -> np.ndarray:
    pred = pipeline.predict(frame[features])
    if target_mode == "log_price":
        pred = np.expm1(pred)
    return np.clip(pred, 10.0, None)


def blend_weight_for_price(baseline_price: float, blend: dict[str, Any]) -> float:
    edges = blend.get("bucket_edges") or {}
    weights = blend.get("bucket_weights") or {}
    chosen_strategy = blend.get("chosen_strategy") or {}
    global_fallback = float(chosen_strategy.get("global_fallback_weight", 0.70))

    q50 = edges.get("q50")
    q80 = edges.get("q80")
    q95 = edges.get("q95")
    if q50 is None or q80 is None or q95 is None:
        return global_fallback

    if baseline_price <= q50:
        bucket = "low_price"
    elif baseline_price <= q80:
        bucket = "medium_price"
    elif baseline_price <= q95:
        bucket = "high_price"
    else:
        bucket = "luxury_extreme_price"

    return float(weights.get(bucket, global_fallback))


def build_feature_row(
    payload: PropertyForecastInput,
    auto: AutoAssumptions,
    price: float | None,
    predicted_fair_price: float | None,
) -> dict[str, Any]:
    today = date.today()
    market_segment = {
        "beach": "coast_beach",
        "urban": "urban_area",
        "city": "city_area",
    }[payload.market_type]
    amenity_flags = [
        payload.has_wifi,
        payload.has_aircon,
        payload.has_pool,
        payload.has_parking,
        payload.has_washer,
        payload.has_dryer,
        payload.has_kitchen,
        payload.has_tv,
        payload.has_heating,
    ]
    amenity_count = int(sum(bool(flag) for flag in amenity_flags))
    price_value = float(price) if price is not None else np.nan
    fair_price = float(predicted_fair_price) if predicted_fair_price is not None else price_value

    if pd.isna(price_value) or pd.isna(fair_price) or fair_price == 0:
        price_gap_abs = 0.0
        price_gap_pct = 0.0
    else:
        price_gap_abs = price_value - fair_price
        price_gap_pct = price_gap_abs / fair_price

    row: dict[str, Any] = {
        "city": normalize_location(payload.city),
        "region_group": normalize_location(payload.region_group),
        "market_segment": market_segment,
        "market_type": payload.market_type,
        "neighbourhood_cleansed": normalize_location(payload.neighbourhood_cleansed),
        "neighbourhood_group_cleansed": normalize_location(payload.region_group),
        "property_type": clean_text(payload.property_type),
        "room_type": clean_text(payload.room_type),
        "accommodates": payload.accommodates,
        "bedrooms": payload.bedrooms,
        "beds": payload.beds,
        "bathrooms": payload.bathrooms,
        "price": price_value,
        "price_per_guest": safe_ratio_feature(price_value, payload.accommodates),
        "price_per_bedroom": safe_ratio_feature(price_value, payload.bedrooms),
        "price_per_bed": safe_ratio_feature(price_value, payload.beds),
        "minimum_nights": payload.minimum_nights,
        "maximum_nights": payload.maximum_nights,
        "instant_bookable": int(payload.instant_bookable),
        "host_is_superhost": auto.host_is_superhost,
        "platform_count": auto.platform_count,
        "number_of_reviews": auto.number_of_reviews,
        "reviews_per_month": auto.reviews_per_month,
        "review_scores_rating": auto.review_scores_rating,
        "review_scores_cleanliness": auto.review_scores_cleanliness,
        "review_scores_location": auto.review_scores_location,
        "review_scores_value": auto.review_scores_value,
        "host_response_rate": auto.host_response_rate,
        "host_acceptance_rate": auto.host_acceptance_rate,
        "host_listings_count": auto.host_listings_count,
        "host_total_listings_count": auto.host_total_listings_count,
        "host_tenure_days": auto.host_tenure_days,
        "host_tenure_years": auto.host_tenure_years,
        "review_score_blend": np.mean(
            [
                auto.review_scores_rating,
                auto.review_scores_cleanliness,
                auto.review_scores_location,
                auto.review_scores_value,
            ]
        ),
        "amenity_count": amenity_count,
        "booking_flex_window": payload.maximum_nights - payload.minimum_nights,
        "beds_per_guest": safe_ratio_feature(payload.beds, payload.accommodates),
        "bathrooms_per_guest": safe_ratio_feature(payload.bathrooms, payload.accommodates),
        "bedrooms_per_guest": safe_ratio_feature(payload.bedrooms, payload.accommodates),
        "log_price": np.log1p(max(price_value, 0.0)) if not pd.isna(price_value) else np.nan,
        "financing_vintage_year": today.year,
        "applied_asset_discount_pct": 0.0,
        "applied_annual_interest_rate": INVESTOR_ASSUMPTIONS[payload.market_type]["annual_interest_rate"],
        "availability_30": 30,
        "availability_60": 60,
        "availability_90": 90,
        "availability_365": 365,
        "predicted_fair_price": fair_price,
        "price_gap_abs": price_gap_abs,
        "price_gap_pct": price_gap_pct,
        "overpriced_flag": int(price_gap_pct > 0.10),
        "underpriced_flag": int(price_gap_pct < -0.10),
        "snapshot_month": today.month,
        "snapshot_quarter": (today.month - 1) // 3 + 1,
        "is_summer": int(today.month in [6, 7, 8]),
        "is_shoulder_season": int(today.month in [4, 5, 9, 10]),
        "has_wifi": int(payload.has_wifi),
        "has_aircon": int(payload.has_aircon),
        "has_pool": int(payload.has_pool),
        "has_parking": int(payload.has_parking),
        "has_washer": int(payload.has_washer),
        "has_dryer": int(payload.has_dryer),
        "has_kitchen": int(payload.has_kitchen),
        "has_tv": int(payload.has_tv),
        "has_heating": int(payload.has_heating),
    }

    for proxy_feature in [
        "px_city_neigh_avg_price",
        "px_city_neigh_median_price",
        "px_city_neigh_count",
        "px_city_neigh_room_avg_price",
        "px_city_neigh_room_median_price",
        "px_city_neigh_room_count",
        "px_city_market_room_avg_price",
        "px_city_market_room_median_price",
        "px_city_market_room_count",
        "px_city_acc_room_avg_price",
        "px_city_acc_room_median_price",
        "px_city_acc_room_count",
        "px_city_prop_avg_price",
        "px_city_prop_median_price",
        "px_city_prop_count",
        "px_city_avg_price",
        "px_city_median_price",
        "px_city_count",
    ]:
        row[proxy_feature] = np.nan

    return row


def predict_occupancy_model_payload(model: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    model_type = model["model_type"]

    if model_type == "single_pipeline":
        features = model["feature_columns"]
        model_frame = ensure_columns(frame, features)
        pred = model["pipeline"].predict(model_frame[features])
        if model.get("logit_target", False):
            pred = 1 / (1 + np.exp(-pred))
        return np.clip(pred, 0, 1)

    if model_type == "xgb_hgb_blend":
        features = model["feature_columns"]
        model_frame = ensure_columns(frame, features)
        xgb_pred = model["xgb_pipeline"].predict(model_frame[features])
        hgb_pred = model["hgb_pipeline"].predict(model_frame[features])
        pred = model["weight_xgb"] * xgb_pred + model["weight_hgb"] * hgb_pred
        return np.clip(pred, 0, 1)

    if model_type == "dynamic_top_model_blend":
        final_pred = np.zeros(len(frame), dtype=float)
        for component_model in model["component_models"]:
            component_name = component_model["component_name"]
            weight = float(model["weights"][component_name])
            component_pred = predict_occupancy_model_payload(component_model, frame)
            final_pred += weight * component_pred
        return np.clip(final_pred, 0, 1)

    raise ValueError(f"Unsupported occupancy model type: {model_type}")


def mortgage_payment(loan_amount: float, annual_interest_rate: float, loan_term_years: int) -> float:
    if loan_amount <= 0:
        return 0.0
    monthly_rate = annual_interest_rate / 12.0
    months = loan_term_years * 12
    if monthly_rate <= 0:
        return loan_amount / months
    return loan_amount * (monthly_rate * (1 + monthly_rate) ** months) / ((1 + monthly_rate) ** months - 1)


def build_net_range(
    low_summary: dict[str, Any],
    base_summary: dict[str, Any],
    high_summary: dict[str, Any],
    field_name: str,
) -> dict[str, Any]:
    return {
        "low": low_summary[field_name],
        "base": base_summary[field_name],
        "high": high_summary[field_name],
    }


def simulate_financials(
    payload: PropertyForecastInput,
    nightly_price: float,
    occupancy_rate: float,
) -> dict[str, Any]:
    operating = OPERATING_ASSUMPTIONS[payload.market_type]
    investor = INVESTOR_ASSUMPTIONS[payload.market_type]

    occupied_nights = occupancy_rate * 365.0
    bookings = occupied_nights / max(operating["avg_stay_nights"], 1.0)
    gross_revenue = nightly_price * occupied_nights

    platform_fees = gross_revenue * operating["platform_fee_pct"]
    management_fees = gross_revenue * operating["management_fee_pct"]
    cleaning_cost = bookings * operating["cleaning_cost_per_turnover"]
    laundry_cost = bookings * operating["laundry_per_turnover"]
    toiletries_cost = bookings * operating["toiletries_per_turnover"]
    base_utility_cost = (
        operating["base_monthly_electricity"]
        + operating["base_monthly_water"]
        + operating["internet_monthly"]
    ) * 12.0
    variable_utility_cost = occupied_nights * (
        operating["electricity_per_occupied_night"] + operating["water_per_occupied_night"]
    )
    total_utilities = base_utility_cost + variable_utility_cost
    insurance_cost = operating["monthly_insurance"] * 12.0
    condo_cost = operating["monthly_condo_fee"] * 12.0
    other_fixed_cost = operating["monthly_other_fixed_cost"] * 12.0
    maintenance_reserve = gross_revenue * operating["maintenance_reserve_pct"]
    accounting_cost = ANNUAL_ACCOUNTING_COST
    licensing_cost = ANNUAL_LICENSING_COST
    imi_cost = payload.property_acquisition_cost * investor["imi_rate_pct"]

    total_operating_cost = (
        platform_fees
        + management_fees
        + cleaning_cost
        + laundry_cost
        + toiletries_cost
        + base_utility_cost
        + variable_utility_cost
        + insurance_cost
        + condo_cost
        + other_fixed_cost
        + maintenance_reserve
        + accounting_cost
        + licensing_cost
        + imi_cost
    )
    noi = gross_revenue - total_operating_cost

    closing_cost = payload.property_acquisition_cost * investor["closing_cost_pct"]
    total_project_capex = payload.property_acquisition_cost + payload.furnishing_setup_cost + closing_cost
    loan_to_cost = LOAN_TO_COST[payload.financing_scenario]
    equity_required = total_project_capex if payload.financing_scenario == "cash_purchase" else total_project_capex * (1.0 - loan_to_cost)
    loan_amount = total_project_capex * loan_to_cost
    annual_interest_rate = 0.0 if payload.financing_scenario == "cash_purchase" else investor["annual_interest_rate"]
    monthly_debt_service = mortgage_payment(loan_amount, annual_interest_rate, LOAN_TERM_YEARS)
    annual_debt_service = monthly_debt_service * 12.0
    annual_interest_cost = loan_amount * annual_interest_rate
    annual_principal_repayment = max(annual_debt_service - annual_interest_cost, 0.0)
    monthly_interest_cost = annual_interest_cost / 12.0
    monthly_principal_repayment = annual_principal_repayment / 12.0

    taxable_income = noi - annual_interest_cost
    tax_due = max(taxable_income, 0.0) * EFFECTIVE_TAX_RATE

    annual_net_income_after_tax = noi - annual_debt_service - tax_due
    cash_on_equity_return = safe_div_value(annual_net_income_after_tax, equity_required)
    payback_years = safe_div_value(equity_required, annual_net_income_after_tax) if annual_net_income_after_tax > 0 else None

    monthly_gross_revenue = round_money(gross_revenue / 12.0)
    monthly_operating_cost = round_money(total_operating_cost / 12.0)
    monthly_noi = round_money(noi / 12.0)
    monthly_debt_service_rounded = round_money(monthly_debt_service)
    monthly_tax_due = round_money(tax_due / 12.0)
    monthly_net_income_after_tax = round_money(
        (monthly_noi or 0.0) - (monthly_debt_service_rounded or 0.0) - (monthly_tax_due or 0.0)
    )

    cost_breakdown = {
        "platform_fees": round_money(platform_fees),
        "management_fees": round_money(management_fees),
        "cleaning_cost": round_money(cleaning_cost),
        "laundry_cost": round_money(laundry_cost),
        "toiletries_cost": round_money(toiletries_cost),
        "base_utility_cost": round_money(base_utility_cost),
        "variable_utility_cost": round_money(variable_utility_cost),
        "total_utilities": round_money(total_utilities),
        "insurance_cost": round_money(insurance_cost),
        "condo_cost": round_money(condo_cost),
        "other_fixed_cost": round_money(other_fixed_cost),
        "maintenance_reserve": round_money(maintenance_reserve),
        "annual_accounting_cost": round_money(accounting_cost),
        "annual_licensing_cost": round_money(licensing_cost),
        "annual_imi_cost": round_money(imi_cost),
        "debt_service": round_money(annual_debt_service),
        "annual_interest_cost": round_money(annual_interest_cost),
        "annual_principal_repayment": round_money(annual_principal_repayment),
        "tax_due": round_money(tax_due),
    }

    tax_breakdown = {
        "taxable_income": round_money(taxable_income),
        "interest_deduction": round_money(annual_interest_cost),
        "effective_tax_rate": EFFECTIVE_TAX_RATE,
        "annual_tax_due": round_money(tax_due),
        "tax_note": "Tax is estimated on NOI after the interest deduction. Final cash flow subtracts the full bank payment and tax.",
        "disclaimer": "This is a simplified estimate, not tax advice.",
    }

    summary = {
        "annual_gross_revenue": round_money(gross_revenue),
        "monthly_gross_revenue": monthly_gross_revenue,
        "annual_operating_cost": round_money(total_operating_cost),
        "monthly_operating_cost": monthly_operating_cost,
        "annual_noi": round_money(noi),
        "monthly_noi": monthly_noi,
        "estimated_total_project_capex": round_money(total_project_capex),
        "estimated_equity_required": round_money(equity_required),
        "estimated_loan_amount": round_money(loan_amount),
        "annual_debt_service": round_money(annual_debt_service),
        "monthly_debt_service": monthly_debt_service_rounded,
        "annual_interest_cost": round_money(annual_interest_cost),
        "annual_principal_repayment": round_money(annual_principal_repayment),
        "monthly_interest_cost": round_money(monthly_interest_cost),
        "monthly_principal_repayment": round_money(monthly_principal_repayment),
        "annual_tax_due": round_money(tax_due),
        "monthly_tax_due": monthly_tax_due,
        "annual_net_income_after_tax": round_money(annual_net_income_after_tax),
        "monthly_net_income_after_tax": monthly_net_income_after_tax,
        "cash_on_equity_return": round(cash_on_equity_return, 4) if cash_on_equity_return is not None else None,
        "payback_years": round(payback_years, 2) if payback_years is not None else None,
        "projected_bookings": round(bookings, 1),
        "occupied_nights": round(occupied_nights, 1),
    }

    return {
        "summary": summary,
        "cost_breakdown": cost_breakdown,
        "tax_breakdown": tax_breakdown,
    }


def build_diagnosis(financials: dict[str, Any], scenario_name: str) -> dict[str, str]:
    monthly_net = financials["monthly_net_income_after_tax"] or 0.0
    monthly_debt = financials["monthly_debt_service"] or 0.0
    monthly_noi = financials["monthly_noi"] or 0.0

    if monthly_net >= 1000:
        headline = "Strong cash-flow forecast"
    elif monthly_net >= 500:
        headline = "Good, but still check financing"
    elif monthly_net >= 0:
        headline = "Positive, but margin is thin"
    else:
        headline = "Negative cash flow in this scenario"

    if scenario_name == "cash_purchase":
        financing_note = "No bank payment is used here, so this shows the property's operating strength."
    elif monthly_noi > 0 and monthly_debt > monthly_noi * 0.45:
        financing_note = "The bank payment takes a large part of NOI. Compare with a lower loan scenario."
    else:
        financing_note = "Debt pressure looks manageable in this scenario."

    return {
        "headline": headline,
        "financing_note": financing_note,
    }


def build_occupancy_ramp_scenario(
    payload: PropertyForecastInput,
    year1_occupancy: float,
) -> list[dict[str, Any]]:
    target = MARKET_STABILIZED_OCCUPANCY_TARGET[payload.market_type]
    stabilized_target = max(year1_occupancy, target)

    year1 = year1_occupancy
    year2 = year1 + 0.50 * (stabilized_target - year1)
    year3 = year1 + 0.80 * (stabilized_target - year1)

    return [
        {
            "year": 1,
            "occupancy_rate": year1,
            "scenario_note": "Launch-year forecast from the ML model.",
        },
        {
            "year": 2,
            "occupancy_rate": year2,
            "scenario_note": "Scenario assumes more reviews, better ranking, and stronger listing trust.",
        },
        {
            "year": 3,
            "occupancy_rate": year3,
            "scenario_note": "Scenario moves closer to stabilized market occupancy if quality stays high.",
        },
    ]


def build_pricing_guidance(payload: PropertyForecastInput, occupancy_rate: float) -> dict[str, Any]:
    target = MARKET_STABILIZED_OCCUPANCY_TARGET[payload.market_type]

    if occupancy_rate < target * 0.85:
        recommendation = "Focus on occupancy first. Keep pricing competitive until the listing builds reviews and trust."
    elif occupancy_rate <= target * 1.05:
        recommendation = "Keep pricing disciplined. Small seasonal changes are safer than large price increases."
    else:
        recommendation = "Occupancy is above the stabilized target, so there may be room to test higher prices carefully."

    return {
        "market_target_occupancy": round(target, 4),
        "current_occupancy": round(occupancy_rate, 4),
        "recommendation": recommendation,
        "note": "Price increases should be tested gradually. Higher prices can reduce occupancy if the listing is not yet established.",
    }


class ForecastEngine:
    def __init__(self) -> None:
        if sys.version_info < (3, 13):
            raise RuntimeError(
                "This dashboard must run with Python 3.13 because the deployed model artifacts were saved in the 3.13 ML environment. "
                "Start the app with: python3.13 -m uvicorn main:app --reload"
            )

        if version_tuple(np.__version__) < (2, 4):
            raise RuntimeError(
                "This dashboard requires numpy 2.4+ to load the deployed model artifacts. "
                "Start the app with the Python 3.13 environment: python3.13 -m uvicorn main:app --reload"
            )

        if version_tuple(sklearn.__version__) < (1, 8):
            raise RuntimeError(
                "This dashboard requires scikit-learn 1.8+ to load the deployed model artifacts. "
                "Start the app with the Python 3.13 environment: python3.13 -m uvicorn main:app --reload"
            )

        missing = [path for path in [PRICE_MODEL_PATH, OCCUPANCY_MODEL_PATH] if not path.exists()]
        if missing:
            missing_text = ", ".join(str(path) for path in missing)
            raise RuntimeError(f"Missing deployment model artifact(s): {missing_text}")

        self.price_bundle = joblib.load(PRICE_MODEL_PATH)
        self.occupancy_bundle = joblib.load(OCCUPANCY_MODEL_PATH)
        self.price_metadata = load_json(PRICE_METADATA_PATH)
        self.occupancy_metadata = load_json(OCCUPANCY_METADATA_PATH)

    @property
    def selected_price_model(self) -> str | None:
        if isinstance(self.price_bundle, dict) and self.price_bundle.get("selected_model"):
            return str(self.price_bundle["selected_model"])
        if self.price_metadata.get("selected_model"):
            return str(self.price_metadata["selected_model"])
        return None

    @property
    def selected_occupancy_model(self) -> str | None:
        if isinstance(self.occupancy_bundle, dict) and self.occupancy_bundle.get("selected_model"):
            return str(self.occupancy_bundle["selected_model"])
        if self.occupancy_metadata.get("selected_model"):
            return str(self.occupancy_metadata["selected_model"])
        return None

    def health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "price_model": PRICE_MODEL_PATH.name,
            "occupancy_model": OCCUPANCY_MODEL_PATH.name,
            "selected_price_model": self.selected_price_model,
            "selected_occupancy_model": self.selected_occupancy_model,
            "price_artifact_exists": PRICE_MODEL_PATH.exists(),
            "occupancy_artifact_exists": OCCUPANCY_MODEL_PATH.exists(),
        }

    def predict(self, payload: PropertyForecastInput) -> dict[str, Any]:
        validate_location_configuration(payload)

        warnings_list: list[str] = []
        if payload.property_acquisition_cost < 20_000:
            warnings_list.append("Acquisition cost seems unusually low. Please check the value.")

        auto = AutoAssumptions()

        price_first = self.predict_price(payload, auto)
        occupancy_first = self.predict_occupancy(payload, auto, price_first)
        auto = self.review_assumptions_from_occupancy(payload, occupancy_first)

        fair_price = max(10.0, self.predict_price(payload, auto))
        occupancy_rate = clamp(self.predict_occupancy(payload, auto, fair_price), 0.0, 1.0)
        auto = self.review_assumptions_from_occupancy(payload, occupancy_rate)

        price_low_68 = max(10.0, fair_price - PRICE_RMSE_68)
        price_high_68 = fair_price + PRICE_RMSE_68
        occupancy_low_68 = clamp(occupancy_rate - OCCUPANCY_RMSE_68, 0.0, 1.0)
        occupancy_high_68 = clamp(occupancy_rate + OCCUPANCY_RMSE_68, 0.0, 1.0)

        price_low_95 = max(10.0, fair_price - PRICE_RMSE_95)
        price_high_95 = fair_price + PRICE_RMSE_95
        occupancy_low_95 = clamp(occupancy_rate - OCCUPANCY_RMSE_95, 0.0, 1.0)
        occupancy_high_95 = clamp(occupancy_rate + OCCUPANCY_RMSE_95, 0.0, 1.0)

        base_result = simulate_financials(payload, fair_price, occupancy_rate)
        likely_low_result = simulate_financials(payload, price_low_68, occupancy_low_68)
        likely_high_result = simulate_financials(payload, price_high_68, occupancy_high_68)
        stress_low_result = simulate_financials(payload, price_low_95, occupancy_low_95)
        stress_high_result = simulate_financials(payload, price_high_95, occupancy_high_95)

        base_summary = base_result["summary"]
        likely_note = CONFIDENCE_NOTE

        if occupancy_rate < 0.15:
            warnings_list.append("Predicted occupancy is below 15%, so the forecast is highly sensitive.")
        if (base_summary["monthly_net_income_after_tax"] or 0.0) < 0:
            warnings_list.append("Monthly net is negative under the selected financing scenario.")
        if normalize_location(payload.city) in LIMITED_SUPPORT_CITIES:
            warnings_list.append("This location/market combination has limited support in the current options list.")

        statistical_evidence = {
            "price_model_r2": PRICE_MODEL_R2,
            "price_model_rmse": PRICE_MODEL_RMSE,
            "price_model_mae": PRICE_MODEL_MAE,
            "occupancy_model_r2": OCCUPANCY_MODEL_R2,
            "occupancy_model_rmse": OCCUPANCY_MODEL_RMSE,
            "occupancy_model_mae": OCCUPANCY_MODEL_MAE,
            "confidence_level_used": likely_note,
            "price_confidence_interval_68": {
                "low": round_money(price_low_68),
                "base": round_money(fair_price),
                "high": round_money(price_high_68),
            },
            "occupancy_confidence_interval_68": {
                "low": round(occupancy_low_68, 4),
                "base": round(occupancy_rate, 4),
                "high": round(occupancy_high_68, 4),
            },
            "price_confidence_interval_95": {
                "low": round_money(price_low_95),
                "base": round_money(fair_price),
                "high": round_money(price_high_95),
            },
            "occupancy_confidence_interval_95": {
                "low": round(occupancy_low_95, 4),
                "base": round(occupancy_rate, 4),
                "high": round(occupancy_high_95, 4),
            },
            "evidence_rating": evidence_rating(),
            "interpretation_note": INTERPRETATION_NOTE,
        }

        investor = INVESTOR_ASSUMPTIONS[payload.market_type]
        operating = OPERATING_ASSUMPTIONS[payload.market_type]

        scenario_comparison = []
        for scenario_name in SCENARIO_ORDER:
            scenario_payload = payload.model_copy(update={"financing_scenario": scenario_name})
            scenario_summary = simulate_financials(scenario_payload, fair_price, occupancy_rate)["summary"]
            scenario_comparison.append(
                {
                    "financing_scenario": scenario_name,
                    "scenario_label": SCENARIO_LABELS[scenario_name],
                    "is_selected": scenario_name == payload.financing_scenario,
                    "annual_net_income_after_tax": scenario_summary["annual_net_income_after_tax"],
                    "monthly_net_income_after_tax": scenario_summary["monthly_net_income_after_tax"],
                    "estimated_equity_required": scenario_summary["estimated_equity_required"],
                    "estimated_loan_amount": scenario_summary["estimated_loan_amount"],
                    "monthly_debt_service": scenario_summary["monthly_debt_service"],
                    "cash_on_equity_return": scenario_summary["cash_on_equity_return"],
                    "payback_years": scenario_summary["payback_years"],
                }
            )

        ramp_years = []
        for year_entry in build_occupancy_ramp_scenario(payload, occupancy_rate):
            scenario_financials = simulate_financials(payload, fair_price, year_entry["occupancy_rate"])
            scenario_summary = scenario_financials["summary"]
            avg_stay_nights = max(OPERATING_ASSUMPTIONS[payload.market_type]["avg_stay_nights"], 1.0)
            occupied_nights = float(year_entry["occupancy_rate"]) * 365.0
            bookings = occupied_nights / avg_stay_nights
            expected_reviews = bookings * REVIEW_CAPTURE_RATE
            ramp_years.append(
                {
                    "year": year_entry["year"],
                    "occupancy_rate": round(year_entry["occupancy_rate"], 4),
                    "occupied_nights": round(occupied_nights, 1),
                    "annual_gross_revenue": scenario_summary["annual_gross_revenue"],
                    "annual_net_income_after_tax": scenario_summary["annual_net_income_after_tax"],
                    "monthly_net_income_after_tax": scenario_summary["monthly_net_income_after_tax"],
                    "expected_reviews": round(expected_reviews, 1),
                    "scenario_note": year_entry["scenario_note"],
                }
            )

        stabilized_target = MARKET_STABILIZED_OCCUPANCY_TARGET[payload.market_type]

        return {
            "inputs": payload.model_dump(),
            "warnings": warnings_list,
            "predictions": {
                "nightly_price": round_money(fair_price),
                "occupancy_rate": round(occupancy_rate, 4),
                "occupied_nights": round(occupancy_rate * 365.0, 1),
                "expected_reviews_first_year": round(auto.number_of_reviews, 1),
                "expected_reviews_per_month": round(auto.reviews_per_month, 2),
            },
            "financials": base_summary,
            "cost_breakdown": base_result["cost_breakdown"],
            "tax_breakdown": base_result["tax_breakdown"],
            "confidence": {
                "method": likely_note,
                "price_range_68": statistical_evidence["price_confidence_interval_68"],
                "occupancy_range_68": statistical_evidence["occupancy_confidence_interval_68"],
                "price_range_95": statistical_evidence["price_confidence_interval_95"],
                "occupancy_range_95": statistical_evidence["occupancy_confidence_interval_95"],
                "monthly_net_range_68": build_net_range(
                    likely_low_result["summary"],
                    base_summary,
                    likely_high_result["summary"],
                    "monthly_net_income_after_tax",
                ),
                "annual_net_range_68": build_net_range(
                    likely_low_result["summary"],
                    base_summary,
                    likely_high_result["summary"],
                    "annual_net_income_after_tax",
                ),
                "monthly_net_range_95": build_net_range(
                    stress_low_result["summary"],
                    base_summary,
                    stress_high_result["summary"],
                    "monthly_net_income_after_tax",
                ),
                "annual_net_range_95": build_net_range(
                    stress_low_result["summary"],
                    base_summary,
                    stress_high_result["summary"],
                    "annual_net_income_after_tax",
                ),
            },
            "model_info": {
                "price_model_file": PRICE_MODEL_PATH.name,
                "occupancy_model_file": OCCUPANCY_MODEL_PATH.name,
                "selected_price_model": self.selected_price_model,
                "selected_occupancy_model": self.selected_occupancy_model,
            },
            "assumptions_detail": {
                "effective_tax_rate": EFFECTIVE_TAX_RATE,
                "loan_term_years": LOAN_TERM_YEARS,
                "annual_interest_rate": investor["annual_interest_rate"],
                "imi_rate_pct": investor["imi_rate_pct"],
                "closing_cost_pct": investor["closing_cost_pct"],
                "platform_fee_pct": operating["platform_fee_pct"],
                "management_fee_pct": operating["management_fee_pct"],
                "review_capture_rate": REVIEW_CAPTURE_RATE,
            },
            "statistical_evidence": statistical_evidence,
            "scenario_comparison": scenario_comparison,
            "diagnosis": build_diagnosis(base_summary, payload.financing_scenario),
            "pricing_guidance": build_pricing_guidance(payload, occupancy_rate),
            "three_year_scenario": {
                "method": "Occupancy ramp scenario toward stabilized market target.",
                "market_stabilized_target": round(stabilized_target, 4),
                "important_note": (
                    "This is a scenario assumption, not a guaranteed forecast. It assumes the host maintains high standards, "
                    "avoids overpricing, gains reviews, and improves listing visibility."
                ),
                "years": ramp_years,
            },
        }

    def predict_price(self, payload: PropertyForecastInput, auto: AutoAssumptions) -> float:
        row = build_feature_row(payload, auto, price=None, predicted_fair_price=None)
        features = self.price_bundle["feature_columns"]
        frame = ensure_columns(pd.DataFrame([row]), features)

        baseline = self.price_bundle["baseline"]
        baseline_pred = predict_price_target(
            baseline["pipeline"],
            frame,
            features,
            baseline["target_mode"],
        )

        segmented = self.price_bundle["segmented"]
        luxury_proba = segmented["classifier"].predict_proba(frame[features])[:, 1]
        normal_pred = predict_price_target(
            segmented["normal_pipe"],
            frame,
            features,
            segmented["target_mode"],
        )
        luxury_pred = predict_price_target(
            segmented["luxury_pipe"],
            frame,
            features,
            segmented["target_mode"],
        )
        segmented_pred = luxury_proba * luxury_pred + (1.0 - luxury_proba) * normal_pred

        blend = self.price_bundle["blending"]
        weight = blend_weight_for_price(float(baseline_pred[0]), blend)
        final_price = weight * float(segmented_pred[0]) + (1.0 - weight) * float(baseline_pred[0])
        return float(max(10.0, final_price))

    def predict_occupancy(
        self,
        payload: PropertyForecastInput,
        auto: AutoAssumptions,
        fair_price: float,
    ) -> float:
        row = build_feature_row(payload, auto, price=fair_price, predicted_fair_price=fair_price)
        frame = pd.DataFrame([row])
        model = self.occupancy_bundle["model"]
        pred = predict_occupancy_model_payload(model, frame)
        return clamp(float(pred[0]), 0.0, 1.0)

    def review_assumptions_from_occupancy(
        self,
        payload: PropertyForecastInput,
        occupancy_rate: float,
    ) -> AutoAssumptions:
        avg_stay = OPERATING_ASSUMPTIONS[payload.market_type]["avg_stay_nights"]
        occupied_nights = occupancy_rate * 365.0
        bookings = occupied_nights / max(avg_stay, 1.0)
        reviews = bookings * REVIEW_CAPTURE_RATE
        return AutoAssumptions(
            number_of_reviews=reviews,
            reviews_per_month=reviews / 12.0,
        )


app = FastAPI(title="Portugal Rental Forecast Dashboard", version="2.2.0")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")
engine = ForecastEngine()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    return engine.health_payload()


@app.get("/api/options")
def api_options() -> dict[str, Any]:
    return format_options_payload()


@app.post("/api/predict")
def predict(payload: PropertyForecastInput) -> dict[str, Any]:
    try:
        return engine.predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed. Check the input values and model artifacts. Details: {exc}",
        ) from exc
