"""Generate a lean MySQL load package for the Portugal rental warehouse.

This package intentionally excludes the massive calendar/review event tables.
It keeps the warehouse laptop-friendly while preserving the Bronze -> Silver ->
Gold dependency chain at a listings-centric grain.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd

import load_mysql_warehouse
import warehouse


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SQL_DIR = PROJECT_DIR / "sql"
SQL_BUILD_DIR = SQL_DIR / "build"
SQL_VALIDATION_DIR = SQL_DIR / "validation"
LOAD_SQL_PATH = SQL_BUILD_DIR / "02_load_portugal_rental_warehouse_lean_v3.sql"
VALIDATE_SQL_PATH = SQL_VALIDATION_DIR / "03_validate_portugal_rental_warehouse_lean.sql"
INSTALL_MD_PATH = SQL_DIR / "README.md"

LEAN_TABLE_ORDER = [
    "bronze_airbnb_listings_raw",
    "bronze_airbnb_neighbourhoods_raw",
    "bronze_airbnb_neighbourhood_geo_raw",
    "bronze_booking_listings_raw",
    "bronze_vrbo_listings_raw",
    "silver_clean_master_listings",
    "silver_location_labels",
    "silver_build_summary",
    "silver_column_profile",
    "silver_null_audit",
    "gold_dim_host",
    "gold_dim_location",
    "gold_dim_neighbourhood_geo",
    "gold_dim_platform",
    "gold_dim_property",
    "gold_bridge_property_platform",
    "gold_fact_listing_snapshot",
    "gold_mart_property_bi",
    "gold_mart_neighbourhood_bi",
    "gold_mart_host_bi",
]

TABLE_CONFIG = {
    "bronze_airbnb_listings_raw": {
        "auto_columns": {"bronze_listing_key"},
        "batch_size": 200,
    },
    "bronze_airbnb_neighbourhoods_raw": {
        "auto_columns": {"bronze_neighbourhood_key"},
        "batch_size": 500,
    },
    "bronze_airbnb_neighbourhood_geo_raw": {
        "auto_columns": {"bronze_neighbourhood_geo_key"},
        "batch_size": 50,
    },
    "bronze_booking_listings_raw": {
        "auto_columns": {"bronze_booking_key", "collected_at"},
        "batch_size": 500,
    },
    "bronze_vrbo_listings_raw": {
        "auto_columns": {"bronze_vrbo_key", "collected_at"},
        "batch_size": 500,
    },
    "silver_clean_master_listings": {
        "auto_columns": set(),
        "batch_size": 200,
    },
    "silver_location_labels": {
        "auto_columns": set(),
        "batch_size": 500,
    },
    "silver_build_summary": {
        "auto_columns": {"build_summary_key"},
        "batch_size": 100,
    },
    "silver_column_profile": {
        "auto_columns": {"column_profile_key"},
        "batch_size": 500,
    },
    "silver_null_audit": {
        "auto_columns": {"null_audit_key"},
        "batch_size": 500,
    },
    "gold_dim_host": {
        "auto_columns": set(),
        "batch_size": 500,
    },
    "gold_dim_location": {
        "auto_columns": set(),
        "batch_size": 500,
    },
    "gold_dim_neighbourhood_geo": {
        "auto_columns": set(),
        "batch_size": 100,
    },
    "gold_dim_platform": {
        "auto_columns": set(),
        "batch_size": 100,
    },
    "gold_dim_property": {
        "auto_columns": set(),
        "batch_size": 200,
    },
    "gold_bridge_property_platform": {
        "auto_columns": set(),
        "batch_size": 500,
    },
    "gold_fact_listing_snapshot": {
        "auto_columns": set(),
        "batch_size": 200,
    },
    "gold_mart_property_bi": {
        "auto_columns": set(),
        "batch_size": 200,
    },
    "gold_mart_neighbourhood_bi": {
        "auto_columns": set(),
        "batch_size": 500,
    },
    "gold_mart_host_bi": {
        "auto_columns": set(),
        "batch_size": 500,
    },
}


def _sql_literal(value: object) -> str:
    """Render a Python / pandas value as a SQL literal."""
    if value is None:
        return "NULL"
    if value is pd.NA:
        return "NULL"
    if isinstance(value, (pd.Timestamp, datetime, date)) and pd.isna(value):
        return "NULL"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "NULL"
    if isinstance(value, (np.floating,)):
        if np.isnan(value) or np.isinf(value):
            return "NULL"
        return repr(float(value))
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (np.bool_, bool)):
        return "1" if bool(value) else "0"
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return "NULL"
        if value.time() == datetime.min.time():
            return f"'{value.strftime('%Y-%m-%d')}'"
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(value, datetime):
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(value, date):
        return f"'{value.strftime('%Y-%m-%d')}'"
    if pd.isna(value):
        return "NULL"

    text = str(value)
    text = text.replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def _align_frame(df: pd.DataFrame, ordered_columns: list[str]) -> pd.DataFrame:
    frame = df.copy()
    for column in ordered_columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[ordered_columns]


def _latest_snapshot_dirs() -> list[tuple[str, str, Path]]:
    rows: list[tuple[str, str, Path]] = []
    for city in warehouse.CITY_NAMES:
        snapshot_dir = warehouse._get_airbnb_snapshot_dir(city)  # noqa: SLF001
        rows.append((city, snapshot_dir.name, snapshot_dir))
    return rows


def build_bronze_frames() -> dict[str, pd.DataFrame]:
    """Build the lean Bronze tables from the remaining raw source files."""
    listings_frames: list[pd.DataFrame] = []
    neighbourhood_frames: list[pd.DataFrame] = []
    geo_rows: list[dict[str, object]] = []

    for city, snapshot_date, snapshot_dir in _latest_snapshot_dirs():
        listing_file = snapshot_dir / "listings.csv.gz"
        listings = pd.read_csv(listing_file, compression="gzip", low_memory=False)
        listings["city"] = city
        listings["snapshot_date"] = snapshot_date
        listings["source_file"] = str(listing_file)
        listings["property_id"] = listings.get("id")
        listings["price_text"] = listings.get("price")
        listings["raw_payload"] = None
        listings_frames.append(
            listings[
                [
                    "city",
                    "snapshot_date",
                    "source_file",
                    "property_id",
                    "listing_url",
                    "name",
                    "host_id",
                    "host_name",
                    "host_since",
                    "host_is_superhost",
                    "host_response_rate",
                    "host_acceptance_rate",
                    "host_listings_count",
                    "host_total_listings_count",
                    "latitude",
                    "longitude",
                    "neighbourhood_cleansed",
                    "neighbourhood_group_cleansed",
                    "property_type",
                    "room_type",
                    "accommodates",
                    "bedrooms",
                    "beds",
                    "bathrooms_text",
                    "bathrooms",
                    "price_text",
                    "minimum_nights",
                    "maximum_nights",
                    "availability_30",
                    "availability_60",
                    "availability_90",
                    "availability_365",
                    "number_of_reviews",
                    "reviews_per_month",
                    "review_scores_rating",
                    "review_scores_cleanliness",
                    "review_scores_location",
                    "review_scores_value",
                    "instant_bookable",
                    "amenities",
                    "last_review",
                    "estimated_occupancy_l365d",
                    "estimated_revenue_l365d",
                    "raw_payload",
                ]
            ].copy()
        )

        neighbourhood_file = snapshot_dir / "neighbourhoods.csv"
        neighbourhoods = pd.read_csv(neighbourhood_file)
        neighbourhoods["city"] = city
        neighbourhoods["snapshot_date"] = snapshot_date
        neighbourhoods["source_file"] = str(neighbourhood_file)
        neighbourhoods["neighbourhood_group_cleansed"] = neighbourhoods.get("neighbourhood_group")
        neighbourhoods["neighbourhood_cleansed"] = neighbourhoods.get("neighbourhood")
        neighbourhoods["raw_payload"] = None
        neighbourhood_frames.append(
            neighbourhoods[
                [
                    "city",
                    "snapshot_date",
                    "source_file",
                    "neighbourhood_group_cleansed",
                    "neighbourhood_cleansed",
                    "raw_payload",
                ]
            ].copy()
        )

        geo_file = snapshot_dir / "neighbourhoods.geojson"
        payload = json.loads(geo_file.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            geo_rows.append(
                {
                    "city": city,
                    "snapshot_date": snapshot_date,
                    "source_file": str(geo_file),
                    "neighbourhood_group_cleansed": props.get("neighbourhood_group")
                    or props.get("neighbourhood_group_cleansed"),
                    "neighbourhood_cleansed": props.get("neighbourhood")
                    or props.get("neighbourhood_cleansed"),
                    "geometry_type": geometry.get("type"),
                    "geometry_json": json.dumps(geometry, ensure_ascii=False),
                    "raw_payload": json.dumps(feature, ensure_ascii=False),
                }
            )

    bronze_booking = pd.DataFrame()
    for csv_file in sorted(load_mysql_warehouse.BOOKING_BRONZE_DIR.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if not df.empty:
            bronze_booking = pd.concat([bronze_booking, df], ignore_index=True)
    if not bronze_booking.empty:
        bronze_booking["raw_payload"] = None

    bronze_vrbo = pd.DataFrame()
    for csv_file in sorted(load_mysql_warehouse.VRBO_BRONZE_DIR.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if not df.empty:
            bronze_vrbo = pd.concat([bronze_vrbo, df], ignore_index=True)
    if not bronze_vrbo.empty:
        bronze_vrbo["raw_payload"] = None

    return {
        "bronze_airbnb_listings_raw": pd.concat(listings_frames, ignore_index=True),
        "bronze_airbnb_neighbourhoods_raw": pd.concat(neighbourhood_frames, ignore_index=True),
        "bronze_airbnb_neighbourhood_geo_raw": pd.DataFrame(geo_rows),
        "bronze_booking_listings_raw": bronze_booking,
        "bronze_vrbo_listings_raw": bronze_vrbo,
    }


def build_gold_frames(silver_frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Build only the lean Gold tables that stay at listings/reference grain."""
    listings = silver_frames["silver_clean_master_listings"].copy()
    labels = silver_frames["silver_location_labels"].copy()

    bronze_ref = warehouse.load_bronze_listings_reference()
    neighbourhood_ref = warehouse.load_bronze_neighbourhood_reference()
    neighbourhood_geo = warehouse.load_bronze_neighbourhood_geo()
    external_sources = warehouse.load_cross_platform_sources()

    dim_host = warehouse.build_dim_host(listings)
    dim_location = warehouse.build_dim_location(listings, labels)
    dim_property = warehouse.build_dim_property(listings)
    dim_platform = warehouse.build_dim_platform(external_sources, airbnb_count=len(listings))
    dim_neighbourhood_geo = warehouse.build_dim_neighbourhood_geo(
        dim_location,
        neighbourhood_geo,
        neighbourhood_ref,
    )
    bridge_property_platform = warehouse.build_bridge_property_platform(
        listings,
        dim_property,
        bronze_ref,
        dim_platform,
        external_sources,
    )
    fact_listing_snapshot = warehouse.build_fact_listing_snapshot(
        listings,
        dim_host,
        dim_location,
        dim_property,
    )

    return {
        "gold_dim_host": dim_host,
        "gold_dim_location": dim_location,
        "gold_dim_neighbourhood_geo": dim_neighbourhood_geo,
        "gold_dim_platform": dim_platform,
        "gold_dim_property": dim_property,
        "gold_bridge_property_platform": bridge_property_platform,
        "gold_fact_listing_snapshot": fact_listing_snapshot,
    }


def build_bi_marts(gold_frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Build lightweight BI marts from the existing lean Gold tables."""
    fact_listing_snapshot = gold_frames["gold_fact_listing_snapshot"].copy()
    dim_property = gold_frames["gold_dim_property"].copy()
    dim_location = gold_frames["gold_dim_location"].copy()
    dim_host = gold_frames["gold_dim_host"].copy()
    bridge = gold_frames["gold_bridge_property_platform"].copy()

    platform_counts = (
        bridge.loc[bridge["property_id"].notna()]
        .groupby("property_id", as_index=False)
        .agg(platform_count=("platform_key", "nunique"))
    )

    property_bi = (
        fact_listing_snapshot.merge(
            dim_property[
                [
                    "property_key",
                    "property_type",
                    "room_type",
                    "accommodates",
                    "bedrooms",
                    "beds",
                    "bathrooms",
                    "instant_bookable",
                ]
            ],
            on="property_key",
            how="left",
        )
        .merge(
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
            on="location_key",
            how="left",
        )
        .merge(
            dim_host[["host_key", "host_id", "host_is_superhost"]],
            on=["host_key", "host_id"],
            how="left",
        )
        .merge(platform_counts, on="property_id", how="left")
    )
    property_bi["platform_count"] = property_bi["platform_count"].fillna(1).astype("Int64")
    property_bi.insert(0, "property_bi_key", range(1, len(property_bi) + 1))

    property_bi = property_bi[
        [
            "property_bi_key",
            "global_property_id",
            "property_id",
            "property_key",
            "host_id",
            "host_key",
            "location_key",
            "city",
            "neighbourhood_cleansed",
            "neighbourhood_group_cleansed",
            "region_group",
            "market_segment",
            "coastal_flag",
            "urban_flag",
            "platform_count",
            "host_is_superhost",
            "instant_bookable",
            "property_type",
            "room_type",
            "accommodates",
            "bedrooms",
            "beds",
            "bathrooms",
            "price",
            "price_per_guest",
            "price_per_bedroom",
            "price_per_bed",
            "availability_30",
            "availability_60",
            "availability_90",
            "availability_365",
            "occupancy_rate",
            "occupancy_rate_alt",
            "estimated_occupancy_l365d",
            "estimated_revenue_l365d",
            "number_of_reviews",
            "reviews_per_month",
            "review_scores_rating",
            "review_scores_cleanliness",
            "review_scores_location",
            "review_scores_value",
            "last_review",
            "snapshot_date",
            "load_batch_date",
            "created_at",
        ]
    ]

    neighbourhood_bi = (
        property_bi.groupby(
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
            listing_count=("property_id", "count"),
            avg_price=("price", "mean"),
            avg_price_per_guest=("price_per_guest", "mean"),
            avg_price_per_bedroom=("price_per_bedroom", "mean"),
            avg_price_per_bed=("price_per_bed", "mean"),
            avg_occupancy_rate=("occupancy_rate", "mean"),
            avg_estimated_revenue=("estimated_revenue_l365d", "mean"),
            avg_number_of_reviews=("number_of_reviews", "mean"),
            avg_reviews_per_month=("reviews_per_month", "mean"),
            avg_review_score_rating=("review_scores_rating", "mean"),
            avg_review_score_cleanliness=("review_scores_cleanliness", "mean"),
            avg_review_score_location=("review_scores_location", "mean"),
            avg_review_score_value=("review_scores_value", "mean"),
            avg_platform_count=("platform_count", "mean"),
            superhost_share=("host_is_superhost", "mean"),
            instant_bookable_share=("instant_bookable", "mean"),
            avg_availability_30=("availability_30", "mean"),
            avg_availability_60=("availability_60", "mean"),
            avg_availability_90=("availability_90", "mean"),
            avg_availability_365=("availability_365", "mean"),
        )
        .round(4)
    )
    neighbourhood_bi.insert(0, "neighbourhood_bi_key", range(1, len(neighbourhood_bi) + 1))

    host_bi = (
        property_bi.groupby(["host_key", "host_id"], dropna=False, as_index=False)
        .agg(
            property_count=("property_id", "count"),
            city_count=("city", "nunique"),
            avg_price=("price", "mean"),
            avg_occupancy_rate=("occupancy_rate", "mean"),
            avg_estimated_revenue=("estimated_revenue_l365d", "mean"),
            avg_review_score_rating=("review_scores_rating", "mean"),
            avg_platform_count=("platform_count", "mean"),
            superhost_flag=("host_is_superhost", "max"),
        )
        .round(4)
    )
    host_bi.insert(0, "host_bi_key", range(1, len(host_bi) + 1))

    return {
        "gold_mart_property_bi": property_bi,
        "gold_mart_neighbourhood_bi": neighbourhood_bi,
        "gold_mart_host_bi": host_bi,
    }


def normalize_table_frames(table_frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Align generated frame column names with the lean SQL schema."""
    normalized = dict(table_frames)

    if "silver_column_profile" in normalized:
        normalized["silver_column_profile"] = normalized["silver_column_profile"].rename(
            columns={"column": "column_name"}
        )

    if "silver_null_audit" in normalized:
        normalized["silver_null_audit"] = normalized["silver_null_audit"].rename(
            columns={"column": "column_name"}
        )

    if "gold_bridge_property_platform" in normalized:
        normalized["gold_bridge_property_platform"] = normalized["gold_bridge_property_platform"].drop(
            columns=["property_platform_key"],
            errors="ignore",
        )

    return normalized


def write_insert_block(handle, table_name: str, df: pd.DataFrame) -> int:
    config = TABLE_CONFIG[table_name]
    columns = [column for column in df.columns if column not in config["auto_columns"]]
    frame = _align_frame(df, columns).copy()
    if frame.empty:
        return 0

    batch_size = config["batch_size"]
    column_sql = ", ".join(f"`{column}`" for column in columns)
    rows_written = 0

    for start in range(0, len(frame), batch_size):
        chunk = frame.iloc[start : start + batch_size]
        values_sql = []
        for _, row in chunk.iterrows():
            values_sql.append("(" + ", ".join(_sql_literal(row[column]) for column in columns) + ")")
        handle.write(f"INSERT INTO `{table_name}` ({column_sql}) VALUES\n")
        handle.write(",\n".join(values_sql))
        handle.write(";\n\n")
        rows_written += len(chunk)

    return rows_written


def write_load_sql(table_frames: dict[str, pd.DataFrame]) -> dict[str, int]:
    row_counts: dict[str, int] = {}

    SQL_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    with LOAD_SQL_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("-- 02_load_portugal_rental_warehouse_lean.sql\n")
        handle.write("-- Generated automatically by export_mysql_stage_files_lean.py\n\n")
        handle.write("USE portugal_rental_warehouse;\n")
        handle.write("SET NAMES utf8mb4;\n")
        handle.write("SET SQL_SAFE_UPDATES = 0;\n")
        handle.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

        for table_name in reversed(LEAN_TABLE_ORDER):
            handle.write(f"DELETE FROM `{table_name}`;\n")
        handle.write("\n")

        for table_name in LEAN_TABLE_ORDER:
            frame = table_frames[table_name]
            row_counts[table_name] = write_insert_block(handle, table_name, frame)

        handle.write("SET FOREIGN_KEY_CHECKS = 1;\n")
        handle.write("SET SQL_SAFE_UPDATES = 1;\n")

    return row_counts


def write_validation_sql(table_frames: dict[str, pd.DataFrame]) -> None:
    SQL_VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    with VALIDATE_SQL_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("-- 03_validate_portugal_rental_warehouse_lean.sql\n\n")
        handle.write("USE portugal_rental_warehouse;\n\n")
        for table_name in LEAN_TABLE_ORDER:
            expected = len(table_frames[table_name])
            handle.write(
                f"SELECT '{table_name}' AS table_name, COUNT(*) AS row_count, {expected} AS expected_rows "
                f"FROM `{table_name}`;\n"
            )


def write_install_doc(row_counts: dict[str, int]) -> None:
    doc = f"""# Lean MySQL Install Package

This is the laptop-friendly warehouse package.

It keeps:
- listings-level Bronze data
- Silver curated listings and metadata
- lean Gold dimensions and listing snapshot fact

It excludes:
- raw calendar event tables
- raw review event tables
- daily calendar facts
- review facts
- heavy financial projection and ML feature marts

## Files

- `sql/build/01_create_portugal_rental_warehouse_lean.sql`
- `sql/build/02_load_portugal_rental_warehouse_lean_v3.sql`
- `sql/validation/03_validate_portugal_rental_warehouse_lean.sql`
- `sql/build/04_build_gold_bi_extensions_v14.sql`
- `sql/validation/05_validate_gold_bi_extensions_v14.sql`

## Run order in MySQL Workbench

1. Open and run `sql/build/01_create_portugal_rental_warehouse_lean.sql`
2. Open and run `sql/build/02_load_portugal_rental_warehouse_lean_v3.sql`
3. Open and run `sql/validation/03_validate_portugal_rental_warehouse_lean.sql`
4. Open and run `sql/build/04_build_gold_bi_extensions_v14.sql`
5. Open and run `sql/validation/05_validate_gold_bi_extensions_v14.sql`

## Expected rows

{chr(10).join(f"- `{table}`: `{count}`" for table, count in row_counts.items())}
"""
    INSTALL_MD_PATH.write_text(doc, encoding="utf-8")


def main() -> None:
    silver_frames = load_mysql_warehouse.build_silver_frames_from_bronze()
    bronze_frames = build_bronze_frames()
    gold_frames = build_gold_frames(silver_frames)
    bi_frames = build_bi_marts(gold_frames)

    table_frames = {
        **bronze_frames,
        **silver_frames,
        **gold_frames,
        **bi_frames,
    }
    table_frames = normalize_table_frames(table_frames)

    row_counts = write_load_sql(table_frames)
    write_validation_sql(table_frames)
    write_install_doc(row_counts)

    print("Lean MySQL package generated:")
    print(f"  create:   {SQL_BUILD_DIR / '01_create_portugal_rental_warehouse_lean.sql'}")
    print(f"  load:     {LOAD_SQL_PATH}")
    print(f"  validate: {VALIDATE_SQL_PATH}")
    print(f"  install:  {INSTALL_MD_PATH}")
    print("Row counts:")
    for table_name in LEAN_TABLE_ORDER:
        print(f"  {table_name}: {row_counts[table_name]:,}")


if __name__ == "__main__":
    main()
