"""Build the Silver listings layer for the Portugal rental project.

Pipeline layout for this phase:
- Bronze: raw source files as downloaded from InsideAirbnb
- Silver: cleaned listings plus metadata and quality outputs
- Gold: warehouse tables and serving datasets
"""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_RAW_DIR = BRONZE_DIR / "raw"
AIRBNB_RAW_DIR = BRONZE_RAW_DIR / "Airbnb"

SILVER_DIR = DATA_DIR / "silver"
SILVER_LISTINGS_DIR = SILVER_DIR / "listings"
SILVER_METADATA_DIR = SILVER_DIR / "metadata"

for directory in [SILVER_LISTINGS_DIR, SILVER_METADATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

CITY_NAMES = ["lisbon", "porto"]

AMENITIES_MAP = {
    "has_wifi": "Wifi",
    "has_aircon": "Air conditioning",
    "has_pool": "Pool",
    "has_parking": "Parking",
    "has_washer": "Washer",
    "has_dryer": "Dryer",
    "has_kitchen": "Kitchen",
    "has_tv": "TV",
    "has_heating": "Heating",
}

BASE_COLUMNS = [
    "id",
    "name",
    "host_id",
    "city",
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
    "bathrooms",
    "price",
    "minimum_nights",
    "maximum_nights",
    "instant_bookable",
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
    "estimated_occupancy_l365d",
    "estimated_revenue_l365d",
]

SILVER_LISTINGS_PARQUET = SILVER_LISTINGS_DIR / "clean_master_listings.parquet"
SILVER_LISTINGS_CSV = SILVER_LISTINGS_DIR / "clean_master_listings.csv"
SILVER_NULL_AUDIT_CSV = SILVER_METADATA_DIR / "null_audit.csv"
SILVER_BUILD_SUMMARY_CSV = SILVER_METADATA_DIR / "build_summary.csv"
SILVER_BUILD_SUMMARY_JSON = SILVER_METADATA_DIR / "build_summary.json"
SILVER_COLUMN_PROFILE_CSV = SILVER_METADATA_DIR / "column_profile.csv"
SILVER_LOCATION_LABELS_TEMPLATE_CSV = SILVER_METADATA_DIR / "location_labels.csv"

LISBON_CITY_AREA = {"Lisboa"}
LISBON_URBAN_AREA = {"Amadora", "Loures", "Odivelas", "Sintra", "Vila Franca De Xira"}
LISBON_COAST_BEACH = {"Cascais", "Oeiras", "Lourinh", "Mafra", "Torres Vedras"}

PORTO_CITY_AREA = {"PORTO"}
PORTO_URBAN_AREA = {"GONDOMAR", "MAIA", "VALONGO"}
PORTO_COAST_BEACH = {"MATOSINHOS", "VILA NOVA DE GAIA", "ESPINHO", "PÓVOA DE VARZIM", "VILA DO CONDE"}


def load_master_listings() -> pd.DataFrame:
    """Load the Bronze listings files and combine them into one frame."""
    datasets = []

    for city in CITY_NAMES:
        city_dir = AIRBNB_RAW_DIR / city
        if not city_dir.exists():
            raise FileNotFoundError(
                f"Missing Bronze Airbnb directory for {city}: {city_dir}"
            )

        snapshot_dirs = sorted([path for path in city_dir.iterdir() if path.is_dir()])
        if not snapshot_dirs:
            raise FileNotFoundError(f"No snapshot folders found for {city}: {city_dir}")

        latest_snapshot_dir = snapshot_dirs[-1]
        file_path = latest_snapshot_dir / "listings.csv.gz"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Missing Bronze listings file for {city}: {file_path}"
            )

        city_df = pd.read_csv(file_path)
        city_df["city"] = city
        city_df["snapshot_date"] = latest_snapshot_dir.name
        datasets.append(city_df)

    return pd.concat(datasets, ignore_index=True)


def add_amenity_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Derive binary amenity flags used later in reporting and modeling."""
    df = df.copy()

    amenities_series = df.get("amenities", pd.Series("", index=df.index)).fillna("")
    for column_name, amenity in AMENITIES_MAP.items():
        df[column_name] = amenities_series.str.contains(
            amenity,
            case=False,
            na=False,
        ).astype("int8")

    return df


def parse_percent(series: pd.Series) -> pd.Series:
    """Convert percentage strings such as '95%' into numeric values."""
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).replace({"nan": None}),
        errors="coerce",
    )


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide while protecting against divide-by-zero issues."""
    denominator = denominator.replace({0: np.nan})
    return numerator / denominator


def clean_master_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Build the Silver curated listings table from the Bronze source frame."""
    amenity_columns = list(AMENITIES_MAP.keys())
    selected_columns = [column for column in BASE_COLUMNS + amenity_columns if column in df.columns]
    clean = df[selected_columns].copy()

    clean["price"] = pd.to_numeric(
        clean["price"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce",
    )

    clean["instant_bookable"] = clean["instant_bookable"].map({"t": 1, "f": 0}).astype("Int64")
    clean["host_is_superhost"] = clean["host_is_superhost"].map({"t": 1, "f": 0}).astype("Int64")
    clean["host_response_rate"] = parse_percent(clean["host_response_rate"])
    clean["host_acceptance_rate"] = parse_percent(clean["host_acceptance_rate"])
    clean["host_since"] = pd.to_datetime(clean["host_since"], errors="coerce")

    clean["occupancy_rate"] = safe_ratio(clean["estimated_occupancy_l365d"], pd.Series(365, index=clean.index))
    clean["occupancy_rate_alt"] = safe_ratio(365 - clean["availability_365"], pd.Series(365, index=clean.index))
    clean["price_per_guest"] = safe_ratio(clean["price"], clean["accommodates"])
    clean["price_per_bedroom"] = safe_ratio(clean["price"], clean["bedrooms"])
    clean["price_per_bed"] = safe_ratio(clean["price"], clean["beds"])

    return clean.rename(columns={"id": "property_id"})


def build_null_audit(df: pd.DataFrame) -> pd.DataFrame:
    """Create a metadata table describing null behavior per Silver column."""
    null_audit = (
        df.isna()
        .agg(["sum", "mean"])
        .T.reset_index()
        .rename(columns={"index": "column", "sum": "missing_rows", "mean": "missing_ratio"})
    )
    null_audit["missing_pct"] = (null_audit["missing_ratio"] * 100).round(2)
    return null_audit.sort_values(["missing_pct", "column"], ascending=[False, True]).reset_index(drop=True)


def build_column_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Create basic metadata about dtype, uniqueness, and completeness."""
    profile_rows = []
    for column in df.columns:
        profile_rows.append(
            {
                "column": column,
                "dtype": str(df[column].dtype),
                "row_count": int(len(df)),
                "non_null_rows": int(df[column].notna().sum()),
                "unique_values": int(df[column].nunique(dropna=True)),
            }
        )
    return pd.DataFrame(profile_rows).sort_values("column").reset_index(drop=True)


def build_summary(df: pd.DataFrame, source_rows: int) -> dict:
    """Create a compact JSON-style summary for the Silver build."""
    city_counts = df["city"].value_counts(dropna=False).sort_index().to_dict()
    return {
        "pipeline_layer": "silver",
        "dataset_name": "clean_master_listings",
        "source_layer": "bronze",
        "source_rows": int(source_rows),
        "silver_rows": int(len(df)),
        "column_count": int(len(df.columns)),
        "cities": {str(key): int(value) for key, value in city_counts.items()},
        "output_files": {
            "parquet": str(SILVER_LISTINGS_PARQUET),
            "csv": str(SILVER_LISTINGS_CSV),
            "null_audit": str(SILVER_NULL_AUDIT_CSV),
            "column_profile": str(SILVER_COLUMN_PROFILE_CSV),
            "location_labels": str(SILVER_LOCATION_LABELS_TEMPLATE_CSV),
        },
    }


def build_location_labels_template(df: pd.DataFrame) -> pd.DataFrame:
    """Create a Silver metadata template for market segmentation labels."""
    template = (
        df[
            [
                "city",
                "neighbourhood_cleansed",
                "neighbourhood_group_cleansed",
            ]
        ]
        .drop_duplicates()
        .sort_values(["city", "neighbourhood_cleansed", "neighbourhood_group_cleansed"])
        .reset_index(drop=True)
    )
    region_groups = []
    market_segments = []
    coastal_flags = []
    urban_flags = []

    for _, row in template.iterrows():
        city = str(row["city"])
        group = str(row["neighbourhood_group_cleansed"])

        region_group = f"{city}_inland"
        market_segment = "inland_town"
        coastal_flag = 0
        urban_flag = 0

        if city == "lisbon":
            if group in LISBON_CITY_AREA:
                region_group = "lisbon_core"
                market_segment = "city_area"
                urban_flag = 1
            elif group in LISBON_URBAN_AREA:
                region_group = "lisbon_metro"
                market_segment = "urban_area"
                urban_flag = 1
            elif group in LISBON_COAST_BEACH:
                region_group = "lisbon_coastal"
                market_segment = "coast_beach"
                coastal_flag = 1
        elif city == "porto":
            if group in PORTO_CITY_AREA:
                region_group = "porto_core"
                market_segment = "city_area"
                urban_flag = 1
            elif group in PORTO_URBAN_AREA:
                region_group = "porto_metro"
                market_segment = "urban_area"
                urban_flag = 1
            elif group in PORTO_COAST_BEACH:
                region_group = "porto_coastal"
                market_segment = "coast_beach"
                coastal_flag = 1

        region_groups.append(region_group)
        market_segments.append(market_segment)
        coastal_flags.append(coastal_flag)
        urban_flags.append(urban_flag)

    template["region_group"] = region_groups
    template["market_segment"] = market_segments
    template["coastal_flag"] = coastal_flags
    template["urban_flag"] = urban_flags
    return template


def save_silver_outputs(
    df: pd.DataFrame,
    null_audit: pd.DataFrame,
    column_profile: pd.DataFrame,
    location_labels: pd.DataFrame,
    summary: dict,
) -> dict:
    """Persist the Silver curated dataset and its metadata artifacts."""
    df.to_csv(SILVER_LISTINGS_CSV, index=False)
    null_audit.to_csv(SILVER_NULL_AUDIT_CSV, index=False)
    column_profile.to_csv(SILVER_COLUMN_PROFILE_CSV, index=False)
    location_labels.to_csv(SILVER_LOCATION_LABELS_TEMPLATE_CSV, index=False)

    try:
        df.to_parquet(SILVER_LISTINGS_PARQUET, index=False)
        summary["parquet_status"] = "written"
    except Exception as exc:
        summary["parquet_status"] = f"skipped: {exc}"

    pd.DataFrame([summary]).to_csv(SILVER_BUILD_SUMMARY_CSV, index=False)
    SILVER_BUILD_SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    bronze_listings = load_master_listings()
    listings_with_amenities = add_amenity_flags(bronze_listings)
    clean = clean_master_listings(listings_with_amenities)

    null_audit = build_null_audit(clean)
    column_profile = build_column_profile(clean)
    location_labels = build_location_labels_template(clean)
    summary = build_summary(clean, source_rows=len(bronze_listings))
    summary = save_silver_outputs(clean, null_audit, column_profile, location_labels, summary)

    print(f"Saved Silver listings layer to {SILVER_LISTINGS_DIR}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
