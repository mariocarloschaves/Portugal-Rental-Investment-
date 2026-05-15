"""Load the project Bronze / Silver / Gold assets into MySQL.

This script populates the MySQL database created by
`sql/create_portugal_rental_warehouse_mysql.sql`.

Pipeline design:
- Bronze reads from raw Airbnb / Booking / Vrbo files
- Silver is rebuilt from Bronze
- Gold is rebuilt from Silver
- MySQL is populated from those rebuilt layers

Usage example:
    python "code files/data_exploration/load_mysql_warehouse.py" --layer all

Connection options are read from environment variables, except the password,
which I prompt for securely when it is not passed explicitly:
- MYSQL_HOST
- MYSQL_PORT
- MYSQL_USER
- MYSQL_DATABASE
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine, inspect, text
from pymysql.err import OperationalError as PyMySQLOperationalError

import preprocessing
import warehouse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BRONZE_DIR = DATA_DIR / "bronze" / "raw"
SILVER_DIR = DATA_DIR / "silver"
AIRBNB_BRONZE_DIR = BRONZE_DIR / "Airbnb"
BOOKING_BRONZE_DIR = BRONZE_DIR / "booking"
VRBO_BRONZE_DIR = BRONZE_DIR / "vrbo"


TABLE_LOAD_ORDER = [
    "bronze_airbnb_listings_raw",
    "bronze_airbnb_calendar_raw",
    "bronze_airbnb_reviews_raw",
    "bronze_airbnb_neighbourhoods_raw",
    "bronze_airbnb_neighbourhood_geo_raw",
    "bronze_booking_listings_raw",
    "bronze_vrbo_listings_raw",
    "silver_clean_master_listings",
    "silver_location_labels",
    "silver_build_summary",
    "silver_column_profile",
    "silver_null_audit",
    "gold_dim_date",
    "gold_dim_host",
    "gold_dim_location",
    "gold_dim_neighbourhood_geo",
    "gold_dim_platform",
    "gold_dim_property",
    "gold_bridge_property_platform",
    "gold_fact_listing_snapshot",
    "gold_fact_calendar_daily",
    "gold_fact_reviews",
    "gold_financial_assumptions",
    "gold_fact_financial_projection",
    "gold_mart_neighbourhood_snapshot",
    "gold_mart_property_profitability",
    "gold_mart_neighbourhood_profitability",
    "gold_ml_training_base",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Bronze / Silver / Gold data into MySQL.")
    parser.add_argument(
        "--layer",
        choices=["all", "bronze", "silver", "gold"],
        default="all",
        help="Choose which layer to load.",
    )
    parser.add_argument(
        "--truncate-first",
        action="store_true",
        help="Clear destination tables before inserting data.",
    )
    parser.add_argument(
        "--mysql-host",
        default=os.getenv("MYSQL_HOST", "localhost"),
        help="MySQL host. Defaults to MYSQL_HOST or localhost.",
    )
    parser.add_argument(
        "--mysql-port",
        default=int(os.getenv("MYSQL_PORT", "3306")),
        type=int,
        help="MySQL port. Defaults to MYSQL_PORT or 3306.",
    )
    parser.add_argument(
        "--mysql-user",
        default=os.getenv("MYSQL_USER", "root"),
        help="MySQL user. Defaults to MYSQL_USER or root.",
    )
    parser.add_argument(
        "--mysql-password",
        default=None,
        help="MySQL password. If omitted, I prompt for it securely.",
    )
    parser.add_argument(
        "--mysql-database",
        default=os.getenv("MYSQL_DATABASE", "portugal_rental_warehouse"),
        help="Target database. Defaults to MYSQL_DATABASE or portugal_rental_warehouse.",
    )
    args = parser.parse_args()
    if not args.mysql_password:
        args.mysql_password = getpass.getpass("MySQL password: ")
    return args


def create_mysql_engine(args: argparse.Namespace):
    password = args.mysql_password
    return create_engine(
        f"mysql+pymysql://{args.mysql_user}:{password}@{args.mysql_host}:{args.mysql_port}/{args.mysql_database}?charset=utf8mb4",
        connect_args={"local_infile": True},
    )


def get_table_columns(engine, table_name: str) -> list[str]:
    inspector = inspect(engine)
    return [column["name"] for column in inspector.get_columns(table_name)]


def align_frame_to_table(df: pd.DataFrame, table_columns: list[str], auto_increment_columns: set[str]) -> pd.DataFrame:
    usable_columns = [column for column in table_columns if column not in auto_increment_columns]
    aligned = df.copy()
    for column in usable_columns:
        if column not in aligned.columns:
            aligned[column] = None
    aligned = aligned[usable_columns]

    for column in aligned.columns:
        if aligned[column].dtype == "bool":
            aligned[column] = aligned[column].astype("Int64")
        elif aligned[column].dtype == "object":
            aligned[column] = aligned[column].where(aligned[column].notna(), None)
    return aligned


def _prepare_bulk_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize frame values before writing a bulk-load CSV."""
    prepared = df.copy()

    for column in prepared.columns:
        if pd.api.types.is_datetime64_any_dtype(prepared[column]):
            prepared[column] = prepared[column].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.api.types.is_bool_dtype(prepared[column]):
            prepared[column] = prepared[column].astype("Int64")

    return prepared


def _bulk_load_chunk(engine, table_name: str, df: pd.DataFrame) -> None:
    """Use MySQL LOAD DATA LOCAL INFILE for fast batch loading."""
    if df.empty:
        return

    prepared = _prepare_bulk_frame(df)

    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        suffix=".csv",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        prepared.to_csv(
            handle,
            index=False,
            header=False,
            sep="\t",
            na_rep="\\N",
            quoting=csv.QUOTE_MINIMAL,
            escapechar="\\",
        )

    columns_sql = ", ".join(f"`{column}`" for column in prepared.columns)
    infile_path = str(temp_path).replace("\\", "\\\\")
    load_sql = f"""
        LOAD DATA LOCAL INFILE '{infile_path}'
        INTO TABLE `{table_name}`
        CHARACTER SET utf8mb4
        FIELDS TERMINATED BY '\\t'
        OPTIONALLY ENCLOSED BY '"'
        ESCAPED BY '\\\\'
        LINES TERMINATED BY '\\n'
        ({columns_sql})
    """

    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        cursor.execute(load_sql)
        raw_connection.commit()
    finally:
        raw_connection.close()
        temp_path.unlink(missing_ok=True)


def _insert_chunk_fallback(engine, table_name: str, df: pd.DataFrame) -> None:
    """Fallback path when LOCAL INFILE is disabled on the MySQL server."""
    prepared = _prepare_bulk_frame(df)
    prepared = prepared.where(prepared.notna(), None)
    prepared.to_sql(
        table_name,
        engine,
        if_exists="append",
        index=False,
        chunksize=min(len(prepared), 5000),
        method="multi",
    )


def append_frame(engine, table_name: str, df: pd.DataFrame, auto_increment_columns: set[str], chunksize: int = 50000) -> int:
    if df.empty:
        return 0
    table_columns = get_table_columns(engine, table_name)
    aligned = align_frame_to_table(df, table_columns, auto_increment_columns)

    total_chunks = max(1, (len(aligned) + chunksize - 1) // chunksize)
    for chunk_number, start in enumerate(range(0, len(aligned), chunksize), start=1):
        stop = start + chunksize
        print(f"  -> {table_name}: loading chunk {chunk_number}/{total_chunks} ({min(stop, len(aligned)):,}/{len(aligned):,} rows)")
        chunk = aligned.iloc[start:stop].copy()
        try:
            _bulk_load_chunk(engine, table_name, chunk)
        except (OperationalError, PyMySQLOperationalError) as exc:
            error_text = str(exc).lower()
            if "loading local data is disabled" not in error_text and "3948" not in error_text:
                raise
            print(f"     LOCAL INFILE unavailable for {table_name}. Falling back to slower insert mode for this session.")
            _insert_chunk_fallback(engine, table_name, chunk)

    return len(aligned)


def truncate_tables(engine, layer: str) -> None:
    if layer == "bronze":
        target_tables = [name for name in TABLE_LOAD_ORDER if name.startswith("bronze_")]
    elif layer == "silver":
        target_tables = [name for name in TABLE_LOAD_ORDER if name.startswith("silver_")]
    elif layer == "gold":
        target_tables = [name for name in TABLE_LOAD_ORDER if name.startswith("gold_")]
    else:
        target_tables = TABLE_LOAD_ORDER

    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table_name in reversed(target_tables):
            connection.execute(text(f"TRUNCATE TABLE `{table_name}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def iter_snapshot_dirs(base_path: Path) -> Iterable[tuple[str, str, Path]]:
    if not base_path.exists():
        return
    for city_dir in sorted(path for path in base_path.iterdir() if path.is_dir()):
        city = city_dir.name.lower()
        for snapshot_dir in sorted(path for path in city_dir.iterdir() if path.is_dir()):
            yield city, snapshot_dir.name, snapshot_dir


def find_file(snapshot_dir: Path, suffix: str) -> Path | None:
    matches = sorted(path for path in snapshot_dir.iterdir() if path.is_file() and path.name.endswith(suffix))
    return matches[0] if matches else None


def load_airbnb_raw_files(engine) -> None:
    auto_columns = {
        "bronze_airbnb_listings_raw": {"bronze_listing_key"},
        "bronze_airbnb_calendar_raw": {"bronze_calendar_key"},
        "bronze_airbnb_reviews_raw": {"bronze_review_key"},
        "bronze_airbnb_neighbourhoods_raw": {"bronze_neighbourhood_key"},
        "bronze_airbnb_neighbourhood_geo_raw": {"bronze_neighbourhood_geo_key"},
    }

    for city, snapshot_date, snapshot_dir in iter_snapshot_dirs(AIRBNB_BRONZE_DIR):
        listing_file = find_file(snapshot_dir, "listings.csv.gz")
        if listing_file:
            for chunk in pd.read_csv(listing_file, compression="gzip", chunksize=5000, low_memory=False):
                chunk["city"] = city
                chunk["snapshot_date"] = snapshot_date
                chunk["source_file"] = str(listing_file)
                chunk["raw_payload"] = None
                append_frame(engine, "bronze_airbnb_listings_raw", chunk, auto_columns["bronze_airbnb_listings_raw"])

        calendar_file = find_file(snapshot_dir, "calendar.csv.gz")
        if calendar_file:
            for chunk in pd.read_csv(calendar_file, compression="gzip", chunksize=20000, low_memory=False):
                chunk["city"] = city
                chunk["snapshot_date"] = snapshot_date
                chunk["source_file"] = str(calendar_file)
                chunk["calendar_date"] = chunk.get("date")
                chunk["price_text"] = chunk.get("price")
                chunk["adjusted_price_text"] = chunk.get("adjusted_price")
                chunk["raw_payload"] = None
                append_frame(engine, "bronze_airbnb_calendar_raw", chunk, auto_columns["bronze_airbnb_calendar_raw"])

        reviews_file = find_file(snapshot_dir, "reviews.csv.gz")
        if reviews_file:
            for chunk in pd.read_csv(reviews_file, compression="gzip", chunksize=20000, low_memory=False):
                chunk["city"] = city
                chunk["snapshot_date"] = snapshot_date
                chunk["source_file"] = str(reviews_file)
                chunk["review_date"] = chunk.get("date")
                chunk["raw_payload"] = None
                append_frame(engine, "bronze_airbnb_reviews_raw", chunk, auto_columns["bronze_airbnb_reviews_raw"])

        neighbourhood_file = find_file(snapshot_dir, "neighbourhoods.csv")
        if neighbourhood_file:
            df = pd.read_csv(neighbourhood_file)
            df["city"] = city
            df["snapshot_date"] = snapshot_date
            df["source_file"] = str(neighbourhood_file)
            df["raw_payload"] = None
            append_frame(engine, "bronze_airbnb_neighbourhoods_raw", df, auto_columns["bronze_airbnb_neighbourhoods_raw"])

        geo_file = find_file(snapshot_dir, "neighbourhoods.geojson")
        if geo_file:
            payload = json.loads(geo_file.read_text(encoding="utf-8"))
            rows = []
            for feature in payload.get("features", []):
                props = feature.get("properties", {})
                rows.append(
                    {
                        "city": city,
                        "snapshot_date": snapshot_date,
                        "source_file": str(geo_file),
                        "neighbourhood_group_cleansed": props.get("neighbourhood_group") or props.get("neighbourhood_group_cleansed"),
                        "neighbourhood_cleansed": props.get("neighbourhood") or props.get("neighbourhood_cleansed"),
                        "geometry_type": feature.get("geometry", {}).get("type"),
                        "geometry_json": json.dumps(feature.get("geometry")),
                        "raw_payload": json.dumps(feature),
                    }
                )
            append_frame(
                engine,
                "bronze_airbnb_neighbourhood_geo_raw",
                pd.DataFrame(rows),
                auto_columns["bronze_airbnb_neighbourhood_geo_raw"],
            )


def load_platform_raw_files(engine) -> None:
    platform_specs = [
        ("bronze_booking_listings_raw", BOOKING_BRONZE_DIR, {"bronze_booking_key"}),
        ("bronze_vrbo_listings_raw", VRBO_BRONZE_DIR, {"bronze_vrbo_key"}),
    ]
    for table_name, folder, auto_columns in platform_specs:
        if not folder.exists():
            continue
        csv_files = sorted(folder.glob("*.csv"))
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)
            if df.empty:
                continue
            df["raw_payload"] = None
            append_frame(engine, table_name, df, auto_columns)


def load_silver_files(engine) -> None:
    auto_columns = {
        "silver_clean_master_listings": set(),
        "silver_location_labels": set(),
        "silver_build_summary": {"build_summary_key"},
        "silver_column_profile": {"column_profile_key"},
        "silver_null_audit": {"null_audit_key"},
    }
    file_map = {
        "silver_clean_master_listings": SILVER_DIR / "listings" / "clean_master_listings.csv",
        "silver_location_labels": SILVER_DIR / "metadata" / "location_labels.csv",
        "silver_build_summary": SILVER_DIR / "metadata" / "build_summary.csv",
        "silver_column_profile": SILVER_DIR / "metadata" / "column_profile.csv",
        "silver_null_audit": SILVER_DIR / "metadata" / "null_audit.csv",
    }
    for table_name, path in file_map.items():
        if path.exists():
            df = pd.read_csv(path)
            append_frame(engine, table_name, df, auto_columns[table_name])


def build_silver_frames_from_bronze() -> dict[str, pd.DataFrame]:
    """Build Silver tables in memory directly from Bronze raw files."""
    bronze_listings = preprocessing.load_master_listings()
    listings_with_amenities = preprocessing.add_amenity_flags(bronze_listings)
    clean = preprocessing.clean_master_listings(listings_with_amenities)
    if "load_batch_date" not in clean.columns:
        clean["load_batch_date"] = pd.Timestamp.today().normalize()
    if "snapshot_date" not in clean.columns:
        clean["snapshot_date"] = pd.Timestamp.today().normalize()
    if "created_at" not in clean.columns:
        clean["created_at"] = pd.Timestamp.now()
    if "record_source" not in clean.columns:
        clean["record_source"] = warehouse.DEFAULT_PLATFORM_NAME
    if "source_system" not in clean.columns:
        clean["source_system"] = "inside_airbnb"
    if "occupancy_rate_alt" not in clean.columns and "availability_365" in clean.columns:
        clean["occupancy_rate_alt"] = (365 - pd.to_numeric(clean["availability_365"], errors="coerce")) / 365
    clean["has_host_response_rate"] = clean["host_response_rate"].notna().astype("Int64")
    clean["has_host_acceptance_rate"] = clean["host_acceptance_rate"].notna().astype("Int64")
    null_audit = preprocessing.build_null_audit(clean)
    column_profile = preprocessing.build_column_profile(clean)
    location_labels = preprocessing.build_location_labels_template(clean)
    summary = preprocessing.build_summary(clean, source_rows=len(bronze_listings))
    summary_frame = pd.DataFrame([summary])
    return {
        "silver_clean_master_listings": clean,
        "silver_location_labels": location_labels,
        "silver_build_summary": summary_frame,
        "silver_column_profile": column_profile,
        "silver_null_audit": null_audit,
    }


def rebuild_silver_from_bronze(persist_to_disk: bool = True) -> dict[str, pd.DataFrame]:
    """Rebuild the Silver layer from Bronze raw files.

    By default this preserves the existing script behavior and writes Silver
    outputs to disk. When persist_to_disk is False, the rebuilt Silver tables
    are returned in memory, which helps in notebook flows where a CSV may be
    locked by another application.
    """
    silver_frames = build_silver_frames_from_bronze()
    if persist_to_disk:
        summary_dict = silver_frames["silver_build_summary"].iloc[0].to_dict()
        preprocessing.save_silver_outputs(
            silver_frames["silver_clean_master_listings"],
            silver_frames["silver_null_audit"],
            silver_frames["silver_column_profile"],
            silver_frames["silver_location_labels"],
            summary_dict,
        )
    return silver_frames


def load_silver_frames(engine, silver_frames: dict[str, pd.DataFrame]) -> None:
    """Load in-memory Silver tables into MySQL."""
    auto_columns = {
        "silver_clean_master_listings": set(),
        "silver_location_labels": set(),
        "silver_build_summary": {"build_summary_key"},
        "silver_column_profile": {"column_profile_key"},
        "silver_null_audit": {"null_audit_key"},
    }
    for table_name, frame in silver_frames.items():
        append_frame(engine, table_name, frame, auto_columns[table_name])

def load_gold_from_pipeline(engine, silver_frames: dict[str, pd.DataFrame] | None = None) -> None:
    """Rebuild Gold from Silver and load the resulting tables into MySQL."""
    if silver_frames is None:
        _, gold_tables, _ = warehouse.assemble_warehouse_tables()
    else:
        _, gold_tables, _ = warehouse.assemble_warehouse_tables_from_silver(
            silver_frames["silver_clean_master_listings"],
            silver_frames["silver_location_labels"],
        )
    table_map = {
        "dim_date": "gold_dim_date",
        "dim_host": "gold_dim_host",
        "dim_location": "gold_dim_location",
        "dim_neighbourhood_geo": "gold_dim_neighbourhood_geo",
        "dim_platform": "gold_dim_platform",
        "dim_property": "gold_dim_property",
        "bridge_property_platform": "gold_bridge_property_platform",
        "fact_listing_snapshot": "gold_fact_listing_snapshot",
        "fact_calendar_daily": "gold_fact_calendar_daily",
        "fact_reviews": "gold_fact_reviews",
        "financial_assumptions": "gold_financial_assumptions",
        "fact_financial_projection": "gold_fact_financial_projection",
        "mart_neighbourhood_snapshot": "gold_mart_neighbourhood_snapshot",
        "mart_property_profitability": "gold_mart_property_profitability",
        "mart_neighbourhood_profitability": "gold_mart_neighbourhood_profitability",
        "ml_training_base": "gold_ml_training_base",
    }
    auto_columns = {target: set() for target in table_map.values()}
    for gold_name, mysql_table in table_map.items():
        frame = gold_tables[gold_name]
        append_frame(engine, mysql_table, frame, auto_columns[mysql_table], chunksize=2000)


def load_project_pipeline_to_mysql(
    engine,
    layer: str = "all",
    truncate_first: bool = True,
    persist_silver_to_disk: bool = False,
) -> None:
    """Run the full Bronze -> Silver -> Gold pipeline into MySQL.

    The default notebook-friendly mode keeps Silver in memory so a locked CSV
    does not block the load.
    """
    if truncate_first:
        truncate_tables(engine, layer)

    print("Rebuilding Silver layer from Bronze raw files...")
    silver_frames = rebuild_silver_from_bronze(persist_to_disk=persist_silver_to_disk)

    if layer in {"all", "bronze"}:
        print("Loading Bronze layer...")
        load_airbnb_raw_files(engine)
        load_platform_raw_files(engine)

    if layer in {"all", "silver"}:
        print("Loading Silver layer...")
        load_silver_frames(engine, silver_frames)

    if layer in {"all", "gold"}:
        print("Rebuilding Gold layer from Silver outputs and loading it into MySQL...")
        load_gold_from_pipeline(engine, silver_frames=silver_frames)


def summarize_row_counts(engine, layer: str) -> None:
    if layer == "all":
        tables = TABLE_LOAD_ORDER
    else:
        tables = [name for name in TABLE_LOAD_ORDER if name.startswith(f"{layer}_")]
    with engine.begin() as connection:
        for table_name in tables:
            count = connection.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()
            print(f"{table_name}: {count}")


def main() -> None:
    args = parse_args()
    engine = create_mysql_engine(args)

    if args.truncate_first:
        truncate_tables(engine, args.layer)

    print("Rebuilding Silver layer from Bronze raw files...")
    rebuild_silver_from_bronze()

    if args.layer in {"all", "bronze"}:
        print("Loading Bronze layer...")
        load_airbnb_raw_files(engine)
        load_platform_raw_files(engine)

    if args.layer in {"all", "silver"}:
        print("Loading Silver layer...")
        load_silver_files(engine)

    if args.layer in {"all", "gold"}:
        print("Rebuilding Gold layer from Silver outputs and loading it into MySQL...")
        load_gold_from_pipeline(engine)

    print("Load complete. Row counts:")
    summarize_row_counts(engine, args.layer)


if __name__ == "__main__":
    main()
