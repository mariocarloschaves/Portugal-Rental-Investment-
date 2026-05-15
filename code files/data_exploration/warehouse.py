"""Build the Gold warehouse layer for the Portugal rental project.

Pipeline layout:
- Bronze: raw source files from InsideAirbnb
- Silver: curated listings and metadata
- Gold: warehouse v1 with dimensions, facts, marts, validations, and model tables
"""

from __future__ import annotations

from pathlib import Path
import re
import json
import sqlite3
import unicodedata
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

BRONZE_DIR = DATA_DIR / "bronze" / "raw"
AIRBNB_RAW_DIR = BRONZE_DIR / "Airbnb"
SILVER_DIR = DATA_DIR / "silver"
SILVER_LISTINGS_DIR = SILVER_DIR / "listings"
SILVER_METADATA_DIR = SILVER_DIR / "metadata"

GOLD_DIR = DATA_DIR / "gold"
GOLD_WAREHOUSE_DIR = GOLD_DIR / "warehouse_v1"
GOLD_METADATA_DIR = GOLD_DIR / "metadata"

for directory in [GOLD_WAREHOUSE_DIR, GOLD_METADATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

DB_PATH = GOLD_WAREHOUSE_DIR / "portugal_rental_warehouse_v1.db"
LOCATION_LABELS_PATH = SILVER_METADATA_DIR / "location_labels.csv"
GOLD_BUILD_SUMMARY_CSV = GOLD_METADATA_DIR / "warehouse_build_summary.csv"
GOLD_BUILD_SUMMARY_JSON = GOLD_METADATA_DIR / "warehouse_build_summary.json"
GOLD_VALIDATION_REPORT_CSV = GOLD_METADATA_DIR / "warehouse_validation_report.csv"
GOLD_VALIDATION_REPORT_JSON = GOLD_METADATA_DIR / "warehouse_validation_report.json"
GOLD_PLATFORM_MATCH_SUMMARY_CSV = GOLD_METADATA_DIR / "platform_match_summary.csv"

CITY_NAMES = ["lisbon", "porto"]
DEFAULT_PLATFORM_NAME = "airbnb"
PLATFORM_SOURCE_PATHS = {
    "booking.com": BRONZE_DIR / "booking" / "listings.csv",
    "vrbo": BRONZE_DIR / "vrbo" / "listings.csv",
}
PLATFORM_TEMPLATE_COLUMNS = [
    "platform_listing_id",
    "title",
    "city",
    "neighbourhood_cleansed",
    "neighbourhood_group_cleansed",
    "latitude",
    "longitude",
    "accommodates",
    "price",
    "listing_url",
]
DEFAULT_PURCHASE_PRICE = 150000.0
DEFAULT_DOWN_PAYMENT_PCT = 0.20
DEFAULT_INTEREST_RATE = 0.04
DEFAULT_LOAN_YEARS = 30
DEFAULT_MANAGEMENT_FEE_PCT = 0.15
DEFAULT_MAINTENANCE_PCT = 0.05
DEFAULT_UTILITIES_MONTHLY = 150.0
DEFAULT_TAX_RATE = 0.06
DEFAULT_PLATFORM_FEE_PCT = 0.03
DEFAULT_VAT_RATE = 0.06
DEFAULT_CORPORATE_TAX_RATE = 0.19
DEFAULT_MUNICIPAL_DERRAMA_RATE = 0.015
DEFAULT_INTERNET_MONTHLY = 32.0
DEFAULT_CLEANING_COST_PER_TURNOVER = 35.0
DEFAULT_AVG_STAY_NIGHTS = 4.0

CITY_FINANCIAL_DEFAULTS = {
    "lisbon": {
        "imi_rate": 0.003,
        "tourist_tax_per_guest_night": 4.0,
        "tourist_tax_cap_nights": 7,
        "tourist_tax_min_age": 13,
        "municipal_derrama_rate": 0.015,
        "electricity_monthly_base": 58.0,
        "water_monthly_base": 24.0,
        "gas_monthly_base": 18.0,
        "internet_monthly_base": 32.0,
        "avg_stay_nights_assumption": 4.0,
        "purchase_price_base": 220000.0,
        "purchase_price_per_bedroom": 65000.0,
    },
    "porto": {
        "imi_rate": 0.00324,
        "tourist_tax_per_guest_night": 3.0,
        "tourist_tax_cap_nights": 7,
        "tourist_tax_min_age": 13,
        "municipal_derrama_rate": 0.015,
        "electricity_monthly_base": 52.0,
        "water_monthly_base": 22.0,
        "gas_monthly_base": 16.0,
        "internet_monthly_base": 32.0,
        "avg_stay_nights_assumption": 4.0,
        "purchase_price_base": 175000.0,
        "purchase_price_per_bedroom": 50000.0,
    },
}
MARKET_SEGMENT_PRICE_MULTIPLIER = {
    "city_area": 1.15,
    "coast_beach": 1.10,
    "urban_area": 1.00,
    "inland_town": 0.90,
}
MARKET_SEGMENT_UTILITY_MULTIPLIER = {
    "city_area": 1.08,
    "coast_beach": 1.05,
    "urban_area": 1.00,
    "inland_town": 0.95,
}


def _get_airbnb_snapshot_dir(city: str, snapshot_date: str | None = None) -> Path:
    """Return the target Airbnb snapshot directory for a city.

    If snapshot_date is omitted, the latest snapshot folder is used.
    """
    city_dir = AIRBNB_RAW_DIR / city
    if not city_dir.exists():
        raise FileNotFoundError(f"Missing Airbnb Bronze directory for {city}: {city_dir}")

    snapshot_dirs = sorted([path for path in city_dir.iterdir() if path.is_dir()])
    if not snapshot_dirs:
        raise FileNotFoundError(f"No Airbnb snapshot folders found for {city}: {city_dir}")

    if snapshot_date is None:
        return snapshot_dirs[-1]

    target = city_dir / snapshot_date
    if not target.exists():
        raise FileNotFoundError(f"Missing Airbnb snapshot folder for {city}: {target}")
    return target


def ensure_cross_platform_templates() -> None:
    """Create optional Bronze templates for future cross-platform source drops."""
    for platform_name, path in PLATFORM_SOURCE_PATHS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            pd.DataFrame(columns=PLATFORM_TEMPLATE_COLUMNS).to_csv(path, index=False)


def _normalize_text(value: object) -> str:
    """Normalize text for cross-platform string comparison."""
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_similarity(left: str, right: str) -> float:
    """Compute a simple title similarity score between two normalized strings."""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _distance_score(
    lat_left: float,
    lon_left: float,
    lat_right: float,
    lon_right: float,
) -> float:
    """Score coordinate proximity without relying on external geo libraries."""
    values = [lat_left, lon_left, lat_right, lon_right]
    if any(pd.isna(value) for value in values):
        return 0.0

    distance = ((lat_left - lat_right) ** 2 + (lon_left - lon_right) ** 2) ** 0.5
    if distance <= 0.002:
        return 1.0
    if distance <= 0.005:
        return 0.8
    if distance <= 0.01:
        return 0.5
    return 0.0


def _value_similarity(left: float, right: float, tolerance: float) -> float:
    """Score how close two numeric values are given an allowed tolerance."""
    if pd.isna(left) or pd.isna(right):
        return 0.0
    if left == right:
        return 1.0
    if abs(left - right) <= tolerance:
        return 0.8
    return 0.0


def load_cross_platform_sources() -> pd.DataFrame:
    """Load optional external platform sources from Bronze template locations."""
    frames = []

    for platform_name, path in PLATFORM_SOURCE_PATHS.items():
        if not path.exists():
            continue

        df = pd.read_csv(path)
        if df.empty:
            continue

        missing = set(PLATFORM_TEMPLATE_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(
                f"{path.name} is missing required columns for {platform_name}: "
                + ", ".join(sorted(missing))
            )

        df = df[PLATFORM_TEMPLATE_COLUMNS].copy()
        df["platform_name"] = platform_name
        df["platform_listing_id"] = df["platform_listing_id"].astype(str)
        df["city"] = df["city"].astype(str).str.strip().str.lower()
        for column in ["latitude", "longitude", "accommodates", "price"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df["normalized_title"] = df["title"].map(_normalize_text)
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=PLATFORM_TEMPLATE_COLUMNS + ["platform_name", "normalized_title"])

    return pd.concat(frames, ignore_index=True)


def load_silver_listings() -> pd.DataFrame:
    """Load the curated Silver listings dataset that feeds Gold."""
    parquet_path = SILVER_LISTINGS_DIR / "clean_master_listings.parquet"
    csv_path = SILVER_LISTINGS_DIR / "clean_master_listings.csv"

    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(
            "Missing Silver listings dataset. "
            f"Expected {parquet_path} or {csv_path}."
        )

    for column in ["host_since", "last_review", "load_batch_date"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")

    if "load_batch_date" not in df.columns:
        df["load_batch_date"] = pd.Timestamp.today().normalize()
    if "snapshot_date" not in df.columns:
        df["snapshot_date"] = pd.Timestamp.today().normalize()
    if "created_at" not in df.columns:
        df["created_at"] = pd.Timestamp.now()
    if "record_source" not in df.columns:
        df["record_source"] = DEFAULT_PLATFORM_NAME
    if "source_system" not in df.columns:
        df["source_system"] = "inside_airbnb"
    if "occupancy_rate_alt" not in df.columns and "availability_365" in df.columns:
        df["occupancy_rate_alt"] = (365 - pd.to_numeric(df["availability_365"], errors="coerce")) / 365

    df["has_host_response_rate"] = df["host_response_rate"].notna().astype("Int64")
    df["has_host_acceptance_rate"] = df["host_acceptance_rate"].notna().astype("Int64")
    return df


def load_location_labels() -> pd.DataFrame:
    """Load Silver market segmentation labels used by Gold dimensions and marts."""
    if LOCATION_LABELS_PATH.exists():
        labels = pd.read_csv(LOCATION_LABELS_PATH)
        expected = {"city", "neighbourhood_cleansed"}
        missing = expected - set(labels.columns)
        if missing:
            raise ValueError(
                "location_labels.csv is missing required columns: "
                + ", ".join(sorted(missing))
            )
        return labels

    return pd.DataFrame(
        columns=[
            "city",
            "neighbourhood_cleansed",
            "neighbourhood_group_cleansed",
            "region_group",
            "market_segment",
            "coastal_flag",
            "urban_flag",
        ]
    )


def load_bronze_listings_reference() -> pd.DataFrame:
    """Load a small Bronze reference table for listing_url and city lineage."""
    frames = []
    for city in CITY_NAMES:
        path = _get_airbnb_snapshot_dir(city) / "listings.csv.gz"
        df = pd.read_csv(path, usecols=["id", "listing_url"])
        df["city"] = city
        frames.append(df.rename(columns={"id": "property_id"}))
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["property_id"])


def load_bronze_calendar() -> pd.DataFrame:
    """Load Bronze calendar files and standardize them for Gold facts."""
    frames = []
    for city in CITY_NAMES:
        path = _get_airbnb_snapshot_dir(city) / "calendar.csv.gz"
        df = pd.read_csv(path)
        df["city"] = city
        frames.append(df)
    calendar = pd.concat(frames, ignore_index=True)
    calendar = calendar.rename(columns={"listing_id": "property_id"})
    calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce")
    calendar["available_flag"] = calendar["available"].map({"t": 1, "f": 0}).astype("Int64")
    for col in ["price", "adjusted_price"]:
        calendar[col] = pd.to_numeric(
            calendar[col].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
            errors="coerce",
        )
    return calendar


def load_bronze_reviews() -> pd.DataFrame:
    """Load Bronze reviews files and standardize them for Gold facts."""
    frames = []
    for city in CITY_NAMES:
        path = _get_airbnb_snapshot_dir(city) / "reviews.csv.gz"
        df = pd.read_csv(path)
        df["city"] = city
        frames.append(df)
    reviews = pd.concat(frames, ignore_index=True)
    reviews = reviews.rename(columns={"listing_id": "property_id", "id": "review_id"})
    reviews["date"] = pd.to_datetime(reviews["date"], errors="coerce")
    reviews["comment_length"] = reviews["comments"].fillna("").str.len()
    return reviews


def load_bronze_neighbourhood_reference() -> pd.DataFrame:
    """Load neighbourhood CSV reference files from Bronze."""
    frames = []
    for city in CITY_NAMES:
        path = _get_airbnb_snapshot_dir(city) / "neighbourhoods.csv"
        df = pd.read_csv(path)
        df["city"] = city
        frames.append(df)
    ref = pd.concat(frames, ignore_index=True)
    return ref.rename(
        columns={
            "neighbourhood_group": "neighbourhood_group_cleansed",
            "neighbourhood": "neighbourhood_cleansed",
        }
    )


def load_bronze_neighbourhood_geo() -> pd.DataFrame:
    """Load Bronze neighbourhood GeoJSON features into a tabular Gold reference."""
    rows = []
    for city in CITY_NAMES:
        path = _get_airbnb_snapshot_dir(city) / "neighbourhoods.geojson"
        geo = json.loads(path.read_text(encoding="utf-8"))
        for feature in geo.get("features", []):
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            rows.append(
                {
                    "city": city,
                    "neighbourhood_cleansed": properties.get("neighbourhood"),
                    "neighbourhood_group_cleansed": properties.get("neighbourhood_group"),
                    "geometry_type": geometry.get("type"),
                    "geometry_json": json.dumps(geometry, ensure_ascii=False),
                }
            )
    return pd.DataFrame(rows)


def _normalize_nullable_ints(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Cast indicator-style fields to nullable integers."""
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    return df


def _build_global_property_id(property_id: pd.Series) -> pd.Series:
    """Create a stable internal global property id placeholder for phase one."""
    return "airbnb_" + property_id.astype(str)


def build_dim_date(calendar: pd.DataFrame, reviews: pd.DataFrame, listings: pd.DataFrame) -> pd.DataFrame:
    """Create a reusable date dimension from all currently available dates."""
    dates = pd.concat(
        [
            pd.Series(calendar["date"].dropna().unique()),
            pd.Series(reviews["date"].dropna().unique()),
            pd.Series(pd.to_datetime(listings["load_batch_date"], errors="coerce").dropna().unique()),
            pd.Series(pd.to_datetime(listings["snapshot_date"], errors="coerce").dropna().unique()),
        ],
        ignore_index=True,
    ).dropna()

    dim_date = pd.DataFrame({"date": pd.to_datetime(pd.Series(dates).drop_duplicates()).sort_values()})
    dim_date["date_key"] = dim_date["date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["year"] = dim_date["date"].dt.year
    dim_date["quarter"] = dim_date["date"].dt.quarter
    dim_date["month"] = dim_date["date"].dt.month
    dim_date["week"] = dim_date["date"].dt.isocalendar().week.astype(int)
    dim_date["day_of_week"] = dim_date["date"].dt.dayofweek
    return dim_date[
        ["date_key", "date", "year", "quarter", "month", "week", "day_of_week"]
    ].reset_index(drop=True)


def build_dim_host(listings: pd.DataFrame) -> pd.DataFrame:
    """Create the host dimension at one row per host."""
    dim_host = (
        listings[
            [
                "host_id",
                "host_since",
                "host_is_superhost",
                "host_response_rate",
                "host_acceptance_rate",
                "host_listings_count",
                "host_total_listings_count",
                "has_host_response_rate",
                "has_host_acceptance_rate",
                "source_system",
                "snapshot_date",
                "load_batch_date",
                "created_at",
            ]
        ]
        .drop_duplicates(subset=["host_id"])
        .sort_values("host_id")
        .reset_index(drop=True)
    )
    dim_host.insert(0, "host_key", range(1, len(dim_host) + 1))
    return _normalize_nullable_ints(dim_host, ["host_is_superhost"])


def build_dim_location(listings: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Create the location dimension at city + neighbourhood-group grain."""
    dim_location = (
        listings[
            [
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "latitude",
                "longitude",
                "source_system",
                "snapshot_date",
                "load_batch_date",
                "created_at",
            ]
        ]
        .groupby(
            [
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "source_system",
                "snapshot_date",
                "load_batch_date",
                "created_at",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            latitude_centroid=("latitude", "median"),
            longitude_centroid=("longitude", "median"),
        )
    )

    merge_cols = [col for col in ["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"] if col in labels.columns]
    if merge_cols:
        dim_location = dim_location.merge(labels, on=merge_cols, how="left")

    dim_location["region_group"] = dim_location.get("region_group", pd.Series(index=dim_location.index, dtype="object")).fillna(dim_location["city"])
    dim_location["market_segment"] = dim_location.get("market_segment", pd.Series(index=dim_location.index, dtype="object")).fillna("unclassified")
    dim_location["coastal_flag"] = dim_location.get("coastal_flag", pd.Series(index=dim_location.index, dtype="float64")).fillna(0)
    dim_location["urban_flag"] = dim_location.get("urban_flag", pd.Series(index=dim_location.index, dtype="float64")).fillna(0)
    dim_location = _normalize_nullable_ints(dim_location, ["coastal_flag", "urban_flag"])
    dim_location.insert(0, "location_key", range(1, len(dim_location) + 1))
    return dim_location.sort_values(["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"]).reset_index(drop=True)


def build_dim_property(listings: pd.DataFrame) -> pd.DataFrame:
    """Create the property dimension at one row per property."""
    property_columns = [
        "property_id",
        "host_id",
        "city",
        "neighbourhood_cleansed",
        "neighbourhood_group_cleansed",
        "property_type",
        "room_type",
        "accommodates",
        "bedrooms",
        "beds",
        "bathrooms",
        "minimum_nights",
        "maximum_nights",
        "instant_bookable",
        "has_wifi",
        "has_aircon",
        "has_pool",
        "has_parking",
        "has_washer",
        "has_dryer",
        "has_kitchen",
        "has_tv",
        "has_heating",
        "latitude",
        "longitude",
        "record_source",
        "source_system",
        "snapshot_date",
        "load_batch_date",
        "created_at",
    ]
    dim_property = (
        listings[property_columns]
        .drop_duplicates(subset=["property_id"])
        .sort_values("property_id")
        .reset_index(drop=True)
    )
    dim_property.insert(0, "property_key", range(1, len(dim_property) + 1))
    dim_property.insert(1, "global_property_id", _build_global_property_id(dim_property["property_id"]))
    return _normalize_nullable_ints(
        dim_property,
        [
            "instant_bookable",
            "has_wifi",
            "has_aircon",
            "has_pool",
            "has_parking",
            "has_washer",
            "has_dryer",
            "has_kitchen",
            "has_tv",
            "has_heating",
        ],
    )


def build_dim_platform(external_sources: pd.DataFrame, airbnb_count: int) -> pd.DataFrame:
    """Create the platform dimension with current source availability."""
    rows = [
        {
            "platform_key": 1,
            "platform_name": DEFAULT_PLATFORM_NAME,
            "platform_type": "short_term_rental_marketplace",
            "source_listing_count": airbnb_count,
            "source_status": "active",
        }
    ]

    for idx, platform_name in enumerate(PLATFORM_SOURCE_PATHS.keys(), start=2):
        listing_count = int((external_sources["platform_name"] == platform_name).sum()) if not external_sources.empty else 0
        rows.append(
            {
                "platform_key": idx,
                "platform_name": platform_name,
                "platform_type": "short_term_rental_marketplace",
                "source_listing_count": listing_count,
                "source_status": "active" if listing_count > 0 else "template_ready",
            }
        )

    return pd.DataFrame(rows)


def build_dim_neighbourhood_geo(dim_location: pd.DataFrame, geo: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Create a geographic reference dimension for mapping use cases."""
    geo_dim = dim_location.merge(
        geo,
        on=["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"],
        how="left",
    ).merge(
        ref.drop_duplicates(subset=["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"]),
        on=["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"],
        how="left",
        suffixes=("", "_ref"),
    )
    geo_dim.insert(0, "geo_key", range(1, len(geo_dim) + 1))
    return geo_dim


def build_bridge_property_platform(
    listings: pd.DataFrame,
    dim_property: pd.DataFrame,
    bronze_ref: pd.DataFrame,
    dim_platform: pd.DataFrame,
    external_sources: pd.DataFrame,
) -> pd.DataFrame:
    """Create the cross-platform bridge table using heuristic listing matching."""
    platform_key = int(dim_platform.loc[dim_platform["platform_name"] == DEFAULT_PLATFORM_NAME, "platform_key"].iloc[0])
    airbnb_bridge = dim_property[["global_property_id", "property_id", "property_key"]].merge(
        bronze_ref[["property_id", "listing_url"]],
        on="property_id",
        how="left",
    )
    airbnb_bridge["platform_key"] = platform_key
    airbnb_bridge["platform_listing_id"] = airbnb_bridge["property_id"].astype(str)
    airbnb_bridge["listing_url"] = airbnb_bridge["listing_url"].fillna(
        "https://www.airbnb.com/rooms/" + airbnb_bridge["property_id"].astype(str)
    )
    airbnb_bridge["match_confidence"] = 1.0
    airbnb_bridge["match_status"] = "native_platform"
    airbnb_bridge["platform_name"] = DEFAULT_PLATFORM_NAME

    airbnb_source = (
        listings[
            [
                "property_id",
                "name",
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "latitude",
                "longitude",
                "accommodates",
                "price",
            ]
        ]
        .drop_duplicates(subset=["property_id"])
        .merge(dim_property[["property_id", "property_key", "global_property_id"]], on="property_id", how="left")
    )
    airbnb_source["normalized_title"] = airbnb_source["name"].map(_normalize_text)

    external_rows = []
    if not external_sources.empty:
        for _, source_row in external_sources.iterrows():
            candidates = airbnb_source.loc[airbnb_source["city"] == source_row["city"]].copy()
            if candidates.empty:
                external_rows.append(
                    {
                        "global_property_id": f"{source_row['platform_name']}_{source_row['platform_listing_id']}",
                        "property_id": pd.NA,
                        "property_key": pd.NA,
                        "listing_url": source_row["listing_url"],
                        "platform_key": int(
                            dim_platform.loc[
                                dim_platform["platform_name"] == source_row["platform_name"],
                                "platform_key",
                            ].iloc[0]
                        ),
                        "platform_listing_id": source_row["platform_listing_id"],
                        "match_confidence": 0.0,
                        "match_status": "unmatched_external",
                        "platform_name": source_row["platform_name"],
                    }
                )
                continue

            candidates["title_similarity"] = candidates["normalized_title"].map(
                lambda title: _title_similarity(title, source_row["normalized_title"])
            )
            candidates["distance_score"] = candidates.apply(
                lambda row: _distance_score(
                    row["latitude"],
                    row["longitude"],
                    source_row["latitude"],
                    source_row["longitude"],
                ),
                axis=1,
            )
            candidates["accommodates_score"] = candidates["accommodates"].map(
                lambda value: _value_similarity(value, source_row["accommodates"], 1)
            )
            candidates["price_score"] = candidates["price"].map(
                lambda value: _value_similarity(value, source_row["price"], 25)
            )
            candidates["neighbourhood_score"] = candidates["neighbourhood_cleansed"].map(
                lambda value: 1.0 if _normalize_text(value) == _normalize_text(source_row["neighbourhood_cleansed"]) else 0.0
            )
            candidates["match_confidence"] = (
                0.35 * candidates["title_similarity"]
                + 0.35 * candidates["distance_score"]
                + 0.15 * candidates["accommodates_score"]
                + 0.10 * candidates["price_score"]
                + 0.05 * candidates["neighbourhood_score"]
            )
            best = candidates.sort_values("match_confidence", ascending=False).iloc[0]
            platform_key = int(
                dim_platform.loc[
                    dim_platform["platform_name"] == source_row["platform_name"],
                    "platform_key",
                ].iloc[0]
            )
            matched = float(best["match_confidence"]) >= 0.75
            external_rows.append(
                {
                    "global_property_id": best["global_property_id"] if matched else f"{source_row['platform_name']}_{source_row['platform_listing_id']}",
                    "property_id": int(best["property_id"]) if matched else pd.NA,
                    "property_key": int(best["property_key"]) if matched else pd.NA,
                    "listing_url": source_row["listing_url"],
                    "platform_key": platform_key,
                    "platform_listing_id": source_row["platform_listing_id"],
                    "match_confidence": round(float(best["match_confidence"]), 4),
                    "match_status": "matched" if matched else "unmatched_external",
                    "platform_name": source_row["platform_name"],
                }
            )

    bridge = pd.concat([airbnb_bridge, pd.DataFrame(external_rows)], ignore_index=True)
    bridge.insert(0, "property_platform_key", range(1, len(bridge) + 1))
    return bridge[
        [
            "property_platform_key",
            "global_property_id",
            "property_id",
            "property_key",
            "platform_name",
            "listing_url",
            "platform_key",
            "platform_listing_id",
            "match_confidence",
            "match_status",
        ]
    ]


def build_fact_listing_snapshot(
    listings: pd.DataFrame,
    dim_host: pd.DataFrame,
    dim_location: pd.DataFrame,
    dim_property: pd.DataFrame,
) -> pd.DataFrame:
    """Create the main Gold listing fact table."""
    fact = listings.merge(
        dim_host[["host_id", "host_key"]],
        on="host_id",
        how="left",
    ).merge(
        dim_location[["location_key", "city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"]],
        on=["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"],
        how="left",
    ).merge(
        dim_property[["property_id", "property_key", "global_property_id"]],
        on="property_id",
        how="left",
    )

    fact["snapshot_date_key"] = pd.to_datetime(fact["snapshot_date"], errors="coerce").dt.strftime("%Y%m%d")
    fact["snapshot_date_key"] = pd.to_numeric(fact["snapshot_date_key"], errors="coerce").astype("Int64")
    fact["load_batch_date_key"] = pd.to_datetime(fact["load_batch_date"], errors="coerce").dt.strftime("%Y%m%d")
    fact["load_batch_date_key"] = pd.to_numeric(fact["load_batch_date_key"], errors="coerce").astype("Int64")

    required_defaults = {
        "occupancy_rate_alt": pd.NA,
        "review_scores_value": pd.NA,
        "last_review": pd.NaT,
    }
    for column, default_value in required_defaults.items():
        if column not in fact.columns:
            fact[column] = default_value

    fact = fact[
        [
            "global_property_id",
            "property_id",
            "property_key",
            "host_id",
            "host_key",
            "location_key",
            "source_system",
            "snapshot_date",
            "snapshot_date_key",
            "load_batch_date",
            "load_batch_date_key",
            "created_at",
            "price",
            "availability_30",
            "availability_60",
            "availability_90",
            "availability_365",
            "estimated_occupancy_l365d",
            "occupancy_rate",
            "occupancy_rate_alt",
            "estimated_revenue_l365d",
            "number_of_reviews",
            "reviews_per_month",
            "review_scores_rating",
            "review_scores_cleanliness",
            "review_scores_location",
            "review_scores_value",
            "price_per_guest",
            "price_per_bedroom",
            "price_per_bed",
            "last_review",
        ]
    ].copy()

    fact.insert(0, "snapshot_key", range(1, len(fact) + 1))
    return fact


def build_fact_calendar_daily(
    calendar: pd.DataFrame,
    dim_property: pd.DataFrame,
    dim_date: pd.DataFrame,
) -> pd.DataFrame:
    """Create the daily calendar fact table from Bronze calendar data."""
    fact = calendar.merge(
        dim_property[["property_id", "property_key", "global_property_id"]],
        on="property_id",
        how="left",
    )
    date_map = dim_date[["date", "date_key"]].copy()
    fact = fact.merge(date_map, on="date", how="left")
    fact = fact[
        [
            "global_property_id",
            "property_id",
            "property_key",
            "city",
            "date_key",
            "date",
            "available_flag",
            "price",
            "adjusted_price",
            "minimum_nights",
            "maximum_nights",
        ]
    ].copy()
    fact = fact.rename(
        columns={
            "price": "daily_price",
            "adjusted_price": "daily_adjusted_price",
            "minimum_nights": "min_nights",
            "maximum_nights": "max_nights",
        }
    )
    fact.insert(0, "calendar_daily_key", range(1, len(fact) + 1))
    return fact


def build_fact_reviews(
    reviews: pd.DataFrame,
    dim_property: pd.DataFrame,
    dim_date: pd.DataFrame,
) -> pd.DataFrame:
    """Create the reviews fact table from Bronze review data."""
    fact = reviews.merge(
        dim_property[["property_id", "property_key", "global_property_id"]],
        on="property_id",
        how="left",
    ).merge(
        dim_date[["date", "date_key"]],
        on="date",
        how="left",
    )
    fact = fact[
        [
            "global_property_id",
            "property_id",
            "property_key",
            "review_id",
            "date_key",
            "date",
            "reviewer_id",
            "reviewer_name",
            "comment_length",
        ]
    ].copy()
    fact.insert(0, "review_fact_key", range(1, len(fact) + 1))
    return fact


def _monthly_mortgage_payment(loan_amount: float, annual_interest_rate: float, loan_years: int) -> float:
    """Compute a simple monthly mortgage payment."""
    monthly_rate = annual_interest_rate / 12
    periods = loan_years * 12
    if loan_amount <= 0:
        return 0.0
    if monthly_rate == 0:
        return loan_amount / periods
    return loan_amount * (monthly_rate * (1 + monthly_rate) ** periods) / ((1 + monthly_rate) ** periods - 1)


def _estimate_purchase_price(city: str, market_segment: str, bedrooms: float) -> float:
    """Estimate a first-pass acquisition price proxy for finance modeling.

    This remains an underwriting assumption, not a legal/tax fact. It is used so
    ROI outputs are less distorted than a single flat purchase price.
    """

    city_defaults = CITY_FINANCIAL_DEFAULTS.get(str(city).lower(), {})
    base_price = city_defaults.get("purchase_price_base", DEFAULT_PURCHASE_PRICE)
    bedroom_uplift = city_defaults.get("purchase_price_per_bedroom", 50000.0)
    segment_multiplier = MARKET_SEGMENT_PRICE_MULTIPLIER.get(str(market_segment), 1.0)
    bedroom_count = max(float(bedrooms) if not pd.isna(bedrooms) else 1.0, 1.0)
    return round((base_price + (bedroom_count - 1) * bedroom_uplift) * segment_multiplier, 2)


def _estimate_guest_count(accommodates: float) -> int:
    """Convert capacity into a conservative taxable-guest estimate."""

    if pd.isna(accommodates) or accommodates <= 0:
        return 1
    return max(1, int(round(float(accommodates) * 0.7)))


def build_financial_assumptions(dim_property: pd.DataFrame, dim_location: pd.DataFrame) -> pd.DataFrame:
    """Create property-level financial assumptions with explicit Portuguese cost rules."""

    assumptions = dim_property[
        [
            "global_property_id",
            "property_id",
            "property_key",
            "city",
            "neighbourhood_cleansed",
            "neighbourhood_group_cleansed",
            "accommodates",
            "bedrooms",
            "minimum_nights",
        ]
    ].merge(
        dim_location[
            [
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "market_segment",
                "region_group",
            ]
        ],
        on=["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"],
        how="left",
    )
    assumptions["market_segment"] = assumptions["market_segment"].fillna("urban_area")
    assumptions["region_group"] = assumptions["region_group"].fillna("unclassified")
    assumptions["city_defaults"] = assumptions["city"].map(
        lambda city: CITY_FINANCIAL_DEFAULTS.get(str(city).lower(), {})
    )
    assumptions["utility_multiplier"] = assumptions["market_segment"].map(
        MARKET_SEGMENT_UTILITY_MULTIPLIER
    ).fillna(1.0)
    assumptions["purchase_price"] = assumptions.apply(
        lambda row: _estimate_purchase_price(row["city"], row["market_segment"], row["bedrooms"]),
        axis=1,
    )
    assumptions["down_payment_pct"] = DEFAULT_DOWN_PAYMENT_PCT
    assumptions["loan_amount"] = assumptions["purchase_price"] * (1 - assumptions["down_payment_pct"])
    assumptions["interest_rate"] = DEFAULT_INTEREST_RATE
    assumptions["loan_years"] = DEFAULT_LOAN_YEARS
    assumptions["management_fee_pct"] = DEFAULT_MANAGEMENT_FEE_PCT
    assumptions["maintenance_pct"] = DEFAULT_MAINTENANCE_PCT
    assumptions["platform_fee_pct"] = DEFAULT_PLATFORM_FEE_PCT
    assumptions["vat_rate"] = DEFAULT_VAT_RATE
    assumptions["corporate_tax_rate"] = DEFAULT_CORPORATE_TAX_RATE
    assumptions["imi_rate"] = assumptions["city_defaults"].map(
        lambda value: value.get("imi_rate", 0.003)
    )
    assumptions["municipal_derrama_rate"] = assumptions["city_defaults"].map(
        lambda value: value.get("municipal_derrama_rate", DEFAULT_MUNICIPAL_DERRAMA_RATE)
    )
    assumptions["tourist_tax_per_guest_night"] = assumptions["city_defaults"].map(
        lambda value: value.get("tourist_tax_per_guest_night", 0.0)
    )
    assumptions["tourist_tax_cap_nights"] = assumptions["city_defaults"].map(
        lambda value: value.get("tourist_tax_cap_nights", 0)
    )
    assumptions["tourist_tax_min_age"] = assumptions["city_defaults"].map(
        lambda value: value.get("tourist_tax_min_age", 13)
    )
    assumptions["electricity_monthly_base"] = assumptions["city_defaults"].map(
        lambda value: value.get("electricity_monthly_base", DEFAULT_UTILITIES_MONTHLY * 0.39)
    ) * assumptions["utility_multiplier"]
    assumptions["water_monthly_base"] = assumptions["city_defaults"].map(
        lambda value: value.get("water_monthly_base", DEFAULT_UTILITIES_MONTHLY * 0.16)
    ) * assumptions["utility_multiplier"]
    assumptions["gas_monthly_base"] = assumptions["city_defaults"].map(
        lambda value: value.get("gas_monthly_base", DEFAULT_UTILITIES_MONTHLY * 0.12)
    ) * assumptions["utility_multiplier"]
    assumptions["internet_monthly_base"] = assumptions["city_defaults"].map(
        lambda value: value.get("internet_monthly_base", DEFAULT_INTERNET_MONTHLY)
    )
    assumptions["utilities_monthly"] = (
        assumptions["electricity_monthly_base"]
        + assumptions["water_monthly_base"]
        + assumptions["gas_monthly_base"]
        + assumptions["internet_monthly_base"]
    ).round(2)
    assumptions["cleaning_cost_per_turnover"] = (
        DEFAULT_CLEANING_COST_PER_TURNOVER
        + assumptions["bedrooms"].fillna(1).clip(lower=1).sub(1) * 10
    ).round(2)
    assumptions["avg_stay_nights_assumption"] = assumptions.apply(
        lambda row: max(
            float(row["minimum_nights"]) if not pd.isna(row["minimum_nights"]) else 1.0,
            row["city_defaults"].get("avg_stay_nights_assumption", DEFAULT_AVG_STAY_NIGHTS),
        ),
        axis=1,
    )
    assumptions["guest_count_estimate"] = assumptions["accommodates"].map(_estimate_guest_count)
    assumptions["annual_imi_tax"] = (assumptions["purchase_price"] * assumptions["imi_rate"]).round(2)
    assumptions["monthly_imi_tax"] = (assumptions["annual_imi_tax"] / 12).round(2)
    assumptions["tax_rate"] = (
        assumptions["vat_rate"]
        + assumptions["corporate_tax_rate"]
        + assumptions["municipal_derrama_rate"]
    )
    assumptions["assumption_version"] = "finance_v2_portugal_rules"
    assumptions["assumption_notes"] = (
        "VAT/tourist-tax based on Portuguese official sources; utilities and purchase price remain model assumptions."
    )
    assumptions["source_system"] = DEFAULT_PLATFORM_NAME
    assumptions["snapshot_date"] = pd.Timestamp.today().normalize()
    assumptions["load_batch_date"] = pd.Timestamp.today().normalize()
    assumptions["created_at"] = pd.Timestamp.now()
    assumptions = assumptions.drop(columns=["city_defaults", "utility_multiplier"])
    assumptions.insert(0, "financial_assumption_key", range(1, len(assumptions) + 1))
    return assumptions


def build_fact_financial_projection(
    fact_listing_snapshot: pd.DataFrame,
    financial_assumptions: pd.DataFrame,
    dim_date: pd.DataFrame,
) -> pd.DataFrame:
    """Create a month-level financial projection fact table."""
    monthly_dates = dim_date[["date_key", "date", "year", "month"]].drop_duplicates()
    monthly_dates = monthly_dates.sort_values("date").drop_duplicates(subset=["year", "month"]).head(12).reset_index(drop=True)

    base = fact_listing_snapshot[
        [
            "global_property_id",
            "property_id",
            "property_key",
            "occupancy_rate",
            "occupancy_rate_alt",
            "estimated_occupancy_l365d",
            "estimated_revenue_l365d",
        ]
    ].merge(
        financial_assumptions[
            [
                "financial_assumption_key",
                "global_property_id",
                "purchase_price",
                "loan_amount",
                "interest_rate",
                "loan_years",
                "management_fee_pct",
                "maintenance_pct",
                "platform_fee_pct",
                "utilities_monthly",
                "city",
                "accommodates",
                "minimum_nights",
                "electricity_monthly_base",
                "water_monthly_base",
                "gas_monthly_base",
                "internet_monthly_base",
                "cleaning_cost_per_turnover",
                "avg_stay_nights_assumption",
                "guest_count_estimate",
                "tourist_tax_per_guest_night",
                "tourist_tax_cap_nights",
                "imi_rate",
                "monthly_imi_tax",
                "vat_rate",
                "corporate_tax_rate",
                "municipal_derrama_rate",
            ]
        ],
        on="global_property_id",
        how="left",
    )

    base["key"] = 1
    monthly_dates = monthly_dates.copy()
    monthly_dates["key"] = 1
    projection = base.merge(monthly_dates, on="key", how="inner").drop(columns=["key"])

    projection["days_in_month"] = pd.to_datetime(
        dict(year=projection["year"], month=projection["month"], day=1)
    ).dt.days_in_month
    projection["estimated_revenue"] = projection["estimated_revenue_l365d"].fillna(0) / 12
    projection["occupancy_rate_finance"] = (
        projection["occupancy_rate"]
        .fillna(projection["occupancy_rate_alt"])
        .fillna(projection["estimated_occupancy_l365d"] / 365)
        .clip(lower=0, upper=1)
    )
    projection["occupied_nights_estimate"] = (
        projection["days_in_month"] * projection["occupancy_rate_finance"]
    ).round(2)
    projection["turnovers_estimate"] = np.ceil(
        projection["occupied_nights_estimate"] / projection["avg_stay_nights_assumption"].clip(lower=1)
    )
    projection["platform_fee_cost"] = projection["estimated_revenue"] * projection["platform_fee_pct"]
    projection["management_fee_cost"] = projection["estimated_revenue"] * projection["management_fee_pct"]
    projection["maintenance_cost"] = projection["estimated_revenue"] * projection["maintenance_pct"]
    projection["cleaning_cost"] = projection["turnovers_estimate"] * projection["cleaning_cost_per_turnover"]
    projection["tourist_tax_nights_estimate"] = np.minimum(
        projection["occupied_nights_estimate"],
        projection["tourist_tax_cap_nights"] * projection["turnovers_estimate"],
    )
    projection["tourist_tax_cost"] = (
        projection["tourist_tax_nights_estimate"]
        * projection["guest_count_estimate"]
        * projection["tourist_tax_per_guest_night"]
    )
    projection["vat_cost"] = projection["estimated_revenue"] * projection["vat_rate"]
    projection["estimated_expenses_pre_tax"] = (
        projection["platform_fee_cost"]
        + projection["management_fee_cost"]
        + projection["maintenance_cost"]
        + projection["cleaning_cost"]
        + projection["tourist_tax_cost"]
        + projection["utilities_monthly"]
        + projection["monthly_imi_tax"]
        + projection["vat_cost"]
    )
    projection["mortgage_payment"] = projection.apply(
        lambda row: _monthly_mortgage_payment(row["loan_amount"], row["interest_rate"], int(row["loan_years"])),
        axis=1,
    )
    projection["taxable_profit_before_income_tax"] = (
        projection["estimated_revenue"] - projection["estimated_expenses_pre_tax"] - projection["mortgage_payment"]
    )
    projection["income_tax_cost"] = np.where(
        projection["taxable_profit_before_income_tax"] > 0,
        projection["taxable_profit_before_income_tax"]
        * (projection["corporate_tax_rate"] + projection["municipal_derrama_rate"]),
        0.0,
    )
    projection["estimated_expenses"] = projection["estimated_expenses_pre_tax"] + projection["income_tax_cost"]
    projection["net_revenue"] = projection["estimated_revenue"] - projection["estimated_expenses"]
    projection["net_cash_flow"] = (
        projection["net_revenue"] - projection["mortgage_payment"]
    )
    projection["break_even_occupancy"] = np.where(
        projection["estimated_revenue"] > 0,
        (
            projection["occupancy_rate_finance"]
            * ((projection["estimated_expenses"] + projection["mortgage_payment"]) / projection["estimated_revenue"])
        ).clip(lower=0, upper=1),
        np.nan,
    )
    projection["cumulative_cash_flow"] = projection.groupby("global_property_id")["net_cash_flow"].cumsum()
    projection["payback_status"] = np.where(projection["cumulative_cash_flow"] >= 0, "paid_back", "in_progress")
    projection.insert(0, "financial_projection_key", range(1, len(projection) + 1))
    return projection[
        [
            "financial_projection_key",
            "financial_assumption_key",
            "global_property_id",
            "property_id",
            "property_key",
            "year",
            "month",
            "date_key",
            "days_in_month",
            "estimated_revenue",
            "occupied_nights_estimate",
            "turnovers_estimate",
            "platform_fee_cost",
            "management_fee_cost",
            "maintenance_cost",
            "cleaning_cost",
            "tourist_tax_cost",
            "monthly_imi_tax",
            "vat_cost",
            "income_tax_cost",
            "estimated_expenses",
            "net_revenue",
            "mortgage_payment",
            "break_even_occupancy",
            "net_cash_flow",
            "cumulative_cash_flow",
            "payback_status",
        ]
    ]


def build_mart_neighbourhood_snapshot(
    listings: pd.DataFrame,
    dim_location: pd.DataFrame,
    fact_financial_projection: pd.DataFrame,
    bridge_property_platform: pd.DataFrame,
) -> pd.DataFrame:
    """Create a denormalized neighbourhood reporting mart."""
    monthly_profit = (
        fact_financial_projection.groupby("property_id", as_index=False)
        .agg(avg_monthly_net_cash_flow=("net_cash_flow", "mean"))
    )
    platform_counts = (
        bridge_property_platform.loc[bridge_property_platform["property_id"].notna()]
        .groupby("property_id", as_index=False)
        .agg(platform_count=("platform_key", "nunique"))
    )

    mart_source = (
        listings.merge(monthly_profit, on="property_id", how="left")
        .merge(platform_counts, on="property_id", how="left")
    )
    mart = (
        mart_source.groupby(
            ["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"],
            dropna=False,
            as_index=False,
        )
        .agg(
            listing_count=("property_id", "count"),
            avg_price=("price", "mean"),
            median_price=("price", "median"),
            avg_price_per_guest=("price_per_guest", "mean"),
            avg_occupancy_rate=("occupancy_rate", "mean"),
            median_occupancy_rate=("occupancy_rate", "median"),
            avg_estimated_revenue=("estimated_revenue_l365d", "mean"),
            median_estimated_revenue=("estimated_revenue_l365d", "median"),
            avg_review_score=("review_scores_rating", "mean"),
            avg_platform_count=("platform_count", "mean"),
            avg_monthly_net_cash_flow=("avg_monthly_net_cash_flow", "mean"),
        )
        .round(4)
    )

    mart["avg_platform_count"] = mart["avg_platform_count"].fillna(1.0)

    mart = mart.merge(
        dim_location[
            [
                "location_key",
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "region_group",
                "market_segment",
                "coastal_flag",
                "urban_flag",
            ]
        ],
        on=["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"],
        how="left",
    )
    mart.insert(0, "neighbourhood_snapshot_key", range(1, len(mart) + 1))
    return mart


def build_mart_property_profitability(
    fact_listing_snapshot: pd.DataFrame,
    dim_property: pd.DataFrame,
    dim_location: pd.DataFrame,
    fact_financial_projection: pd.DataFrame,
    financial_assumptions: pd.DataFrame,
    bridge_property_platform: pd.DataFrame,
) -> pd.DataFrame:
    """Create a dashboard-ready property profitability mart."""
    profitability = (
        fact_financial_projection.groupby(["global_property_id", "property_id", "property_key"], as_index=False)
        .agg(
            estimated_cost=("estimated_expenses", "mean"),
            net_revenue=("net_revenue", "mean"),
            net_cash_flow=("net_cash_flow", "mean"),
            cumulative_cash_flow=("cumulative_cash_flow", "max"),
            avg_monthly_revenue=("estimated_revenue", "mean"),
            break_even_occupancy=("break_even_occupancy", "mean"),
        )
    )
    platform_counts = (
        bridge_property_platform.loc[bridge_property_platform["property_id"].notna()]
        .groupby("property_id", as_index=False)
        .agg(platform_count=("platform_key", "nunique"))
    )

    mart = fact_listing_snapshot[
        ["global_property_id", "property_id", "property_key", "location_key", "estimated_revenue_l365d"]
    ].merge(
        profitability,
        on=["global_property_id", "property_id", "property_key"],
        how="left",
    ).merge(
        dim_property[["property_key", "city"]],
        on="property_key",
        how="left",
    ).merge(
        financial_assumptions[["property_key", "purchase_price"]],
        on="property_key",
        how="left",
    ).merge(
        dim_location[["location_key", "market_segment"]],
        on="location_key",
        how="left",
    ).merge(
        platform_counts,
        on="property_id",
        how="left",
    )
    mart["ROI"] = np.where(
        mart["purchase_price"] > 0,
        mart["net_cash_flow"] * 12 / mart["purchase_price"],
        np.nan,
    )
    mart["payback_years"] = np.where(
        mart["net_cash_flow"] > 0,
        mart["purchase_price"] / (mart["net_cash_flow"] * 12),
        np.nan,
    )
    mart["platform_count"] = mart["platform_count"].fillna(1)
    mart = mart.rename(columns={"estimated_revenue_l365d": "estimated_revenue"})
    mart.insert(0, "property_profitability_key", range(1, len(mart) + 1))
    return mart[
        [
            "property_profitability_key",
            "global_property_id",
            "property_id",
            "property_key",
            "city",
            "market_segment",
            "platform_count",
            "purchase_price",
            "estimated_revenue",
            "estimated_cost",
            "net_revenue",
            "net_cash_flow",
            "break_even_occupancy",
            "ROI",
            "payback_years",
        ]
    ]


def build_mart_neighbourhood_profitability(
    mart_property_profitability: pd.DataFrame,
    fact_listing_snapshot: pd.DataFrame,
    dim_location: pd.DataFrame,
) -> pd.DataFrame:
    """Create a neighbourhood-level financial mart for investment comparison.

    This is the finance-specific rollup that Step 4 needs. It keeps profitability
    analysis at neighbourhood grain instead of collapsing everything into city-wide
    averages that would hide inner-city vs outer-market differences.
    """

    source = mart_property_profitability.merge(
        fact_listing_snapshot[["property_id", "location_key"]],
        on="property_id",
        how="left",
    ).merge(
        dim_location[
            [
                "location_key",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "region_group",
                "coastal_flag",
                "urban_flag",
            ]
        ],
        on="location_key",
        how="left",
    )

    mart = (
        source.groupby(
            [
                "location_key",
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
                "region_group",
                "market_segment",
                "coastal_flag",
                "urban_flag",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            property_count=("property_id", "count"),
            avg_purchase_price=("purchase_price", "mean"),
            median_purchase_price=("purchase_price", "median"),
            avg_estimated_revenue=("estimated_revenue", "mean"),
            median_estimated_revenue=("estimated_revenue", "median"),
            avg_estimated_cost=("estimated_cost", "mean"),
            avg_net_revenue=("net_revenue", "mean"),
            avg_net_cash_flow=("net_cash_flow", "mean"),
            median_net_cash_flow=("net_cash_flow", "median"),
            avg_break_even_occupancy=("break_even_occupancy", "mean"),
            avg_roi=("ROI", "mean"),
            median_roi=("ROI", "median"),
            avg_payback_years=("payback_years", "mean"),
            avg_platform_count=("platform_count", "mean"),
        )
        .round(4)
    )
    mart.insert(0, "neighbourhood_profitability_key", range(1, len(mart) + 1))
    return mart


def build_ml_training_base(
    fact_listing_snapshot: pd.DataFrame,
    dim_property: pd.DataFrame,
    dim_host: pd.DataFrame,
    dim_location: pd.DataFrame,
    fact_calendar_daily: pd.DataFrame,
    fact_reviews: pd.DataFrame,
    bridge_property_platform: pd.DataFrame,
) -> pd.DataFrame:
    """Create a Gold flat table for ML training with calendar/review signals."""
    calendar_features = (
        fact_calendar_daily.groupby("property_id", as_index=False)
        .agg(
            calendar_observed_days=("calendar_daily_key", "count"),
            calendar_available_days=("available_flag", "sum"),
            calendar_avg_daily_price=("daily_price", "mean"),
            calendar_median_daily_price=("daily_price", "median"),
            calendar_avg_min_nights=("min_nights", "mean"),
            calendar_avg_max_nights=("max_nights", "mean"),
        )
    )
    calendar_features["calendar_blocked_days"] = (
        calendar_features["calendar_observed_days"] - calendar_features["calendar_available_days"]
    )
    calendar_features["calendar_availability_rate"] = np.where(
        calendar_features["calendar_observed_days"] > 0,
        calendar_features["calendar_available_days"] / calendar_features["calendar_observed_days"],
        np.nan,
    )

    reviews_features = (
        fact_reviews.groupby("property_id", as_index=False)
        .agg(
            review_fact_count=("review_fact_key", "count"),
            review_unique_reviewers=("reviewer_id", "nunique"),
            avg_review_comment_length=("comment_length", "mean"),
        )
    )

    platform_features = (
        bridge_property_platform.groupby("property_id", as_index=False)
        .agg(platform_count=("platform_key", "nunique"))
    )

    ml_base = (
        fact_listing_snapshot.merge(
            dim_property.drop(columns=["latitude", "longitude", "record_source"]),
            on=["global_property_id", "property_id", "property_key"],
            how="left",
            suffixes=("", "_property"),
        )
        .merge(
            dim_host,
            on=["host_id", "host_key"],
            how="left",
            suffixes=("", "_host"),
        )
        .merge(
            dim_location,
            on="location_key",
            how="left",
            suffixes=("", "_location"),
        )
        .merge(calendar_features, on="property_id", how="left")
        .merge(reviews_features, on="property_id", how="left")
        .merge(platform_features, on="property_id", how="left")
    )

    ml_base["platform_count"] = ml_base["platform_count"].fillna(1)
    return ml_base


def run_validations(
    dim_host: pd.DataFrame,
    dim_property: pd.DataFrame,
    fact_listing_snapshot: pd.DataFrame,
) -> pd.DataFrame:
    """Run the first round of Gold data-quality validations."""
    validation_rows = [
        {
            "validation_name": "duplicate_property_id_dim_property",
            "status": "pass" if dim_property["property_id"].duplicated().sum() == 0 else "fail",
            "value": int(dim_property["property_id"].duplicated().sum()),
        },
        {
            "validation_name": "duplicate_host_id_dim_host",
            "status": "pass" if dim_host["host_id"].duplicated().sum() == 0 else "fail",
            "value": int(dim_host["host_id"].duplicated().sum()),
        },
        {
            "validation_name": "null_property_key_fact_listing_snapshot",
            "status": "pass" if fact_listing_snapshot["property_key"].isna().sum() == 0 else "fail",
            "value": int(fact_listing_snapshot["property_key"].isna().sum()),
        },
        {
            "validation_name": "negative_price_fact_listing_snapshot",
            "status": "pass" if ((fact_listing_snapshot["price"].dropna() < 0).sum() == 0) else "fail",
            "value": int((fact_listing_snapshot["price"].dropna() < 0).sum()),
        },
        {
            "validation_name": "occupancy_rate_out_of_range",
            "status": "pass"
            if (((fact_listing_snapshot["occupancy_rate"].dropna() < 0) | (fact_listing_snapshot["occupancy_rate"].dropna() > 1)).sum() == 0)
            else "fail",
            "value": int(((fact_listing_snapshot["occupancy_rate"].dropna() < 0) | (fact_listing_snapshot["occupancy_rate"].dropna() > 1)).sum()),
        },
    ]
    return pd.DataFrame(validation_rows)


def create_indexes(engine) -> None:
    """Add the first round of practical indexes for Gold queries."""
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_dim_property_property_id ON dim_property(property_id)",
        "CREATE INDEX IF NOT EXISTS idx_dim_host_host_id ON dim_host(host_id)",
        "CREATE INDEX IF NOT EXISTS idx_dim_location_city_neighbourhood ON dim_location(city, neighbourhood_cleansed)",
        "CREATE INDEX IF NOT EXISTS idx_dim_date_date_key ON dim_date(date_key)",
        "CREATE INDEX IF NOT EXISTS idx_fact_listing_snapshot_property_id ON fact_listing_snapshot(property_id)",
        "CREATE INDEX IF NOT EXISTS idx_fact_calendar_daily_property_id ON fact_calendar_daily(property_id)",
        "CREATE INDEX IF NOT EXISTS idx_fact_reviews_property_id ON fact_reviews(property_id)",
        "CREATE INDEX IF NOT EXISTS idx_ml_training_base_property_id ON ml_training_base(property_id)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def write_tables(engine, tables: dict[str, pd.DataFrame], chunksize: int = 50000) -> None:
    """Write Gold tables to SQLite in chunks to avoid memory spikes."""
    for table_name, df in tables.items():
        df.to_sql(
            table_name,
            engine,
            index=False,
            if_exists="replace",
            chunksize=chunksize,
        )


def export_metadata(
    silver_listings: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    validation_report: pd.DataFrame,
    bridge_property_platform: pd.DataFrame,
) -> pd.DataFrame:
    """Write Gold row-count and validation metadata."""
    summary_rows = []
    for table_name, df in tables.items():
        summary_rows.append({"layer": "gold", "table_name": table_name, "row_count": len(df)})
    summary_rows.append({"layer": "silver", "table_name": "clean_master_listings", "row_count": len(silver_listings)})

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(GOLD_BUILD_SUMMARY_CSV, index=False)
    GOLD_BUILD_SUMMARY_JSON.write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")

    validation_report.to_csv(GOLD_VALIDATION_REPORT_CSV, index=False)
    GOLD_VALIDATION_REPORT_JSON.write_text(validation_report.to_json(orient="records", indent=2), encoding="utf-8")

    platform_summary = (
        bridge_property_platform.groupby(["platform_name", "match_status"], as_index=False)
        .agg(
            bridge_rows=("property_platform_key", "count"),
            avg_match_confidence=("match_confidence", "mean"),
        )
        .round(4)
    )
    platform_summary.to_csv(GOLD_PLATFORM_MATCH_SUMMARY_CSV, index=False)
    return summary


def assemble_warehouse_tables_from_silver(
    listings: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    """Assemble Gold tables from already-prepared Silver inputs.

    This keeps the intended dependency chain explicit:
    Bronze -> Silver -> Gold.
    """
    ensure_cross_platform_templates()
    bronze_ref = load_bronze_listings_reference()
    calendar = load_bronze_calendar()
    reviews = load_bronze_reviews()
    neighbourhood_ref = load_bronze_neighbourhood_reference()
    neighbourhood_geo = load_bronze_neighbourhood_geo()
    external_sources = load_cross_platform_sources()

    dim_date = build_dim_date(calendar, reviews, listings)
    dim_host = build_dim_host(listings)
    dim_location = build_dim_location(listings, labels)
    dim_property = build_dim_property(listings)
    dim_platform = build_dim_platform(external_sources, airbnb_count=len(listings))
    dim_neighbourhood_geo = build_dim_neighbourhood_geo(dim_location, neighbourhood_geo, neighbourhood_ref)
    bridge_property_platform = build_bridge_property_platform(
        listings,
        dim_property,
        bronze_ref,
        dim_platform,
        external_sources,
    )

    fact_listing_snapshot = build_fact_listing_snapshot(listings, dim_host, dim_location, dim_property)
    fact_calendar_daily = build_fact_calendar_daily(calendar, dim_property, dim_date)
    fact_reviews = build_fact_reviews(reviews, dim_property, dim_date)

    financial_assumptions = build_financial_assumptions(dim_property, dim_location)
    fact_financial_projection = build_fact_financial_projection(fact_listing_snapshot, financial_assumptions, dim_date)

    mart_neighbourhood_snapshot = build_mart_neighbourhood_snapshot(
        listings,
        dim_location,
        fact_financial_projection,
        bridge_property_platform,
    )
    mart_property_profitability = build_mart_property_profitability(
        fact_listing_snapshot,
        dim_property,
        dim_location,
        fact_financial_projection,
        financial_assumptions,
        bridge_property_platform,
    )
    mart_neighbourhood_profitability = build_mart_neighbourhood_profitability(
        mart_property_profitability,
        fact_listing_snapshot,
        dim_location,
    )
    ml_training_base = build_ml_training_base(
        fact_listing_snapshot,
        dim_property,
        dim_host,
        dim_location,
        fact_calendar_daily,
        fact_reviews,
        bridge_property_platform,
    )

    tables = {
        "dim_date": dim_date,
        "dim_host": dim_host,
        "dim_location": dim_location,
        "dim_property": dim_property,
        "dim_platform": dim_platform,
        "dim_neighbourhood_geo": dim_neighbourhood_geo,
        "bridge_property_platform": bridge_property_platform,
        "fact_listing_snapshot": fact_listing_snapshot,
        "fact_calendar_daily": fact_calendar_daily,
        "fact_reviews": fact_reviews,
        "financial_assumptions": financial_assumptions,
        "fact_financial_projection": fact_financial_projection,
        "mart_neighbourhood_snapshot": mart_neighbourhood_snapshot,
        "mart_property_profitability": mart_property_profitability,
        "mart_neighbourhood_profitability": mart_neighbourhood_profitability,
        "ml_training_base": ml_training_base,
    }

    validation_report = run_validations(dim_host, dim_property, fact_listing_snapshot)

    return listings, tables, validation_report


def assemble_warehouse_tables() -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    """Assemble the Gold warehouse tables from Bronze and Silver inputs.

    This is the pure build step for the intended pipeline:
    Bronze raw files -> Silver curated outputs -> Gold tables.
    It returns the in-memory Gold tables so callers can persist them wherever
    they need, such as SQLite for local work or MySQL for deployment.
    """
    listings = load_silver_listings()
    labels = load_location_labels()
    return assemble_warehouse_tables_from_silver(listings, labels)


def build_warehouse() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the complete Gold warehouse v1 from Silver and Bronze inputs."""
    listings, tables, validation_report = assemble_warehouse_tables()

    engine = create_engine(f"sqlite:///{DB_PATH}")
    write_tables(engine, tables)
    create_indexes(engine)
    summary = export_metadata(listings, tables, validation_report, bridge_property_platform)
    return summary, validation_report


def inspect_database() -> None:
    """Print the Gold table inventory for quick checks after a build."""
    with sqlite3.connect(DB_PATH) as connection:
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name",
            connection,
        )
        print("Gold warehouse tables:")
        print(tables.to_string(index=False))


def main() -> None:
    """Run the full Gold warehouse build."""
    summary, validation_report = build_warehouse()
    print(f"Built Gold warehouse at {DB_PATH}")
    print(summary.to_string(index=False))
    print("\nValidation report:")
    print(validation_report.to_string(index=False))
    inspect_database()


if __name__ == "__main__":
    main()
