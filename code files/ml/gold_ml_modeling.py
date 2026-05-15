from __future__ import annotations

import getpass
import json
from pathlib import Path
from urllib.parse import quote_plus

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sqlalchemy import create_engine, text
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

try:
    from lightgbm import LGBMRegressor

    LIGHTGBM_AVAILABLE = True
except Exception:
    LGBMRegressor = None
    LIGHTGBM_AVAILABLE = False


def resolve_base_dir() -> Path:
    module_dir = Path(__file__).resolve().parent
    candidates = [
        module_dir,
        module_dir.parent,
        Path.cwd(),
        Path.cwd() / "code files",
    ]
    for candidate in candidates:
        if (candidate / "data").exists():
            return candidate
    return module_dir.parent


BASE_DIR = resolve_base_dir()
MODEL_DIR = BASE_DIR / "data" / "gold" / "modeling"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
DEPLOYMENT_MODEL_DIR = MODEL_DIR / "deployment_models"
PREVIOUS_MODEL_DIR = MODEL_DIR / "previous_models"
DEPLOYMENT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
PREVIOUS_MODEL_DIR.mkdir(parents=True, exist_ok=True)


PROPERTY_MART_SQL = """
SELECT
    p.property_id,
    p.property_key,
    p.host_key,
    p.snapshot_date,
    p.city,
    p.region_group,
    p.market_segment,
    p.market_type,
    p.neighbourhood_cleansed,
    p.neighbourhood_group_cleansed,
    p.property_type,
    p.room_type,
    p.accommodates,
    p.bedrooms,
    p.beds,
    p.bathrooms,
    p.price,
    p.price_per_guest,
    p.price_per_bedroom,
    p.price_per_bed,
    dp.minimum_nights,
    dp.maximum_nights,
    p.instant_bookable,
    p.host_is_superhost,
    p.platform_count,
    p.number_of_reviews,
    p.reviews_per_month,
    p.review_scores_rating,
    p.review_scores_cleanliness,
    p.review_scores_location,
    p.review_scores_value,
    dp.has_wifi,
    dp.has_aircon,
    dp.has_pool,
    dp.has_parking,
    dp.has_washer,
    dp.has_dryer,
    dp.has_kitchen,
    dp.has_tv,
    dp.has_heating,
    p.availability_30,
    p.availability_60,
    p.availability_90,
    p.availability_365,
    p.projected_gross_revenue,
    p.monthly_projected_gross_revenue,
    p.projected_noi,
    p.monthly_projected_noi,
    p.financing_vintage_year,
    p.applied_asset_discount_pct,
    p.applied_annual_interest_rate,
    h.host_since,
    h.host_response_rate,
    h.host_acceptance_rate,
    h.host_listings_count,
    h.host_total_listings_count,
    p.occupancy_rate AS target_occupancy_rate,
    p.price AS target_nightly_price
FROM gold_mart_property_bi p
LEFT JOIN gold_dim_host h
    ON p.host_key = h.host_key
LEFT JOIN gold_dim_property dp
    ON p.property_key = dp.property_key
WHERE p.snapshot_date = (SELECT MAX(snapshot_date) FROM gold_mart_property_bi)
  AND p.investment_grade_flag = 1
  AND p.scenario_name = 'loan_90'
"""


OCCUPANCY_CATEGORICAL_COLUMNS = [
    "city",
    "region_group",
    "market_segment",
    "market_type",
    "neighbourhood_cleansed",
    "neighbourhood_group_cleansed",
    "property_type",
    "room_type",
]

OCCUPANCY_BASE_FEATURES = [
    "city",
    "region_group",
    "market_segment",
    "market_type",
    "neighbourhood_cleansed",
    "neighbourhood_group_cleansed",
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
    "minimum_nights",
    "maximum_nights",
    "instant_bookable",
    "host_is_superhost",
    "platform_count",
    "number_of_reviews",
    "reviews_per_month",
    "review_scores_rating",
    "review_scores_cleanliness",
    "review_scores_location",
    "review_scores_value",
    "host_response_rate",
    "host_acceptance_rate",
    "host_listings_count",
    "host_total_listings_count",
    "host_tenure_days",
    "host_tenure_years",
    "review_score_blend",
    "amenity_count",
    "booking_flex_window",
    "beds_per_guest",
    "bathrooms_per_guest",
    "bedrooms_per_guest",
    "log_price",
    "financing_vintage_year",
    "applied_asset_discount_pct",
    "applied_annual_interest_rate",
]

OCCUPANCY_AVAILABILITY_FEATURES = [
    "availability_30",
    "availability_60",
    "availability_90",
    "availability_365",
]


PRICE_CATEGORICAL_COLUMNS = [
    "city",
    "region_group",
    "market_segment",
    "market_type",
    "neighbourhood_cleansed",
    "neighbourhood_group_cleansed",
    "property_type",
    "room_type",
]

PRICE_LAUNCH_CORE_FEATURES = [
    "city",
    "region_group",
    "market_segment",
    "market_type",
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
    "amenity_count",
    "booking_flex_window",
    "beds_per_guest",
    "bathrooms_per_guest",
    "bedrooms_per_guest",
    "snapshot_month",
    "snapshot_quarter",
    "is_summer",
    "is_shoulder_season",
]

PRICE_MARKET_PROXY_FEATURES = [
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
]


def build_mysql_engine():
    mysql_host = "localhost"
    mysql_port = 3306
    mysql_db = "portugal_rental_warehouse"
    mysql_user = "root"
    raw_mysql_password = getpass.getpass("MySQL password: ")
    mysql_password = quote_plus(raw_mysql_password)
    return create_engine(
        f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db}"
    )


def load_property_mart_frame(engine) -> pd.DataFrame:
    with engine.connect() as connection:
        frame = pd.read_sql(text(PROPERTY_MART_SQL), connection)
    return frame


def prepare_common_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")
    df["host_since"] = pd.to_datetime(df["host_since"], errors="coerce")

    df["host_tenure_days"] = (df["snapshot_date"] - df["host_since"]).dt.days.clip(lower=0)
    df["host_tenure_years"] = df["host_tenure_days"] / 365.25

    df["review_score_blend"] = df[
        [
            "review_scores_rating",
            "review_scores_cleanliness",
            "review_scores_location",
            "review_scores_value",
        ]
    ].mean(axis=1)

    amenity_flags = [
        "has_wifi",
        "has_aircon",
        "has_pool",
        "has_parking",
        "has_washer",
        "has_dryer",
        "has_kitchen",
        "has_tv",
        "has_heating",
    ]
    df["amenity_count"] = df[amenity_flags].fillna(0).sum(axis=1)

    df["booking_flex_window"] = df["maximum_nights"].fillna(0) - df["minimum_nights"].fillna(0)
    df["beds_per_guest"] = df["beds"].fillna(0) / df["accommodates"].replace({0: np.nan})
    df["bathrooms_per_guest"] = df["bathrooms"].fillna(0) / df["accommodates"].replace({0: np.nan})
    df["bedrooms_per_guest"] = df["bedrooms"].fillna(0) / df["accommodates"].replace({0: np.nan})
    df["log_price"] = np.log1p(df["price"].clip(lower=0))

    df["snapshot_month"] = df["snapshot_date"].dt.month
    df["snapshot_quarter"] = df["snapshot_date"].dt.quarter
    df["is_summer"] = df["snapshot_month"].isin([6, 7, 8]).astype(int)
    df["is_shoulder_season"] = df["snapshot_month"].isin([4, 5, 9, 10]).astype(int)

    return df


def build_candidate_models(include_linear: bool = True, include_dummy: bool = True) -> dict[str, object]:
    candidate_models: dict[str, object] = {}

    if include_dummy:
        candidate_models["dummy_median"] = DummyRegressor(strategy="median")
    if include_linear:
        candidate_models["ridge"] = Ridge(alpha=1.0, random_state=42)

    candidate_models["random_forest"] = RandomForestRegressor(
        n_estimators=300,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=1,
    )
    candidate_models["hist_gradient_boosting"] = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_depth=6,
        max_iter=300,
        random_state=42,
    )
    candidate_models["catboost"] = CatBoostRegressor(
        iterations=400,
        learning_rate=0.05,
        depth=6,
        loss_function="RMSE",
        eval_metric="RMSE",
        verbose=0,
        random_seed=42,
    )
    candidate_models["xgboost"] = XGBRegressor(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=1,
    )

    if LIGHTGBM_AVAILABLE:
        candidate_models["lightgbm"] = LGBMRegressor(
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
        )

    return candidate_models


def build_pipeline(feature_columns: list[str], categorical_columns: list[str], model) -> Pipeline:
    numeric_columns = [column for column in feature_columns if column not in categorical_columns]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "encoder",
                            OneHotEncoder(
                                handle_unknown="infrequent_if_exist",
                                min_frequency=20,
                                sparse_output=False,
                            ),
                        ),
                    ]
                ),
                [column for column in categorical_columns if column in feature_columns],
            ),
            (
                "numeric",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                numeric_columns,
            ),
        ],
        remainder="drop",
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )


def add_train_only_price_proxies(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = X_train.copy()
    test = X_test.copy()

    train_with_target = train.copy()
    train_with_target["target_nightly_price"] = y_train.values
    for frame in (train_with_target, train, test):
        frame["accommodates_bucket"] = pd.cut(
            frame["accommodates"].fillna(0),
            bins=[-np.inf, 2, 4, 6, np.inf],
            labels=["1-2", "3-4", "5-6", "7+"],
        )

    group_specs = [
        (["city", "neighbourhood_cleansed"], "px_city_neigh"),
        (["city", "neighbourhood_cleansed", "room_type"], "px_city_neigh_room"),
        (["city", "market_type", "room_type"], "px_city_market_room"),
        (["city", "accommodates_bucket", "room_type"], "px_city_acc_room"),
        (["city", "property_type"], "px_city_prop"),
        (["city"], "px_city"),
    ]

    for keys, prefix in group_specs:
        stats = (
            train_with_target.groupby(keys, observed=False)
            .agg(
                **{
                    f"{prefix}_avg_price": ("target_nightly_price", "mean"),
                    f"{prefix}_median_price": ("target_nightly_price", "median"),
                    f"{prefix}_count": ("property_id", "count"),
                }
            )
            .reset_index()
        )
        train = train.merge(stats, on=keys, how="left")
        test = test.merge(stats, on=keys, how="left")

    train = train.drop(columns=["accommodates_bucket"])
    test = test.drop(columns=["accommodates_bucket"])

    return train, test


def add_full_price_proxies(frame: pd.DataFrame, target_column: str) -> pd.DataFrame:
    df = frame.copy()
    df["accommodates_bucket"] = pd.cut(
        df["accommodates"].fillna(0),
        bins=[-np.inf, 2, 4, 6, np.inf],
        labels=["1-2", "3-4", "5-6", "7+"],
    )

    group_specs = [
        (["city", "neighbourhood_cleansed"], "px_city_neigh"),
        (["city", "neighbourhood_cleansed", "room_type"], "px_city_neigh_room"),
        (["city", "market_type", "room_type"], "px_city_market_room"),
        (["city", "accommodates_bucket", "room_type"], "px_city_acc_room"),
        (["city", "property_type"], "px_city_prop"),
        (["city"], "px_city"),
    ]

    for keys, prefix in group_specs:
        stats = (
            df.groupby(keys, observed=False)
            .agg(
                **{
                    f"{prefix}_avg_price": (target_column, "mean"),
                    f"{prefix}_median_price": (target_column, "median"),
                    f"{prefix}_count": ("property_id", "count"),
                }
            )
            .reset_index()
        )
        df = df.merge(stats, on=keys, how="left")

    df = df.drop(columns=["accommodates_bucket"])
    return df


def run_model_benchmark(
    frame: pd.DataFrame,
    target_column: str,
    feature_sets: dict[str, list[str]],
    categorical_columns: list[str],
    candidate_models: dict[str, object],
    split_transform_fn=None,
) -> tuple[pd.DataFrame, dict[tuple[str, str], tuple[Pipeline, list[str], pd.DataFrame, pd.Series]]]:
    benchmark_rows: list[dict[str, object]] = []
    fitted_models: dict[tuple[str, str], tuple[Pipeline, list[str], pd.DataFrame, pd.Series]] = {}

    clean_frame = frame.copy().dropna(subset=[target_column])

    for feature_set_name, feature_columns in feature_sets.items():
        X = clean_frame.drop(columns=[target_column])
        y = clean_frame[target_column]

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
        )

        if split_transform_fn is not None:
            X_train, X_test = split_transform_fn(X_train.copy(), X_test.copy(), y_train.copy())

        X_train = X_train[feature_columns]
        X_test = X_test[feature_columns]

        for model_name, model in candidate_models.items():
            pipeline = build_pipeline(feature_columns, categorical_columns, clone(model))
            pipeline.fit(X_train, y_train)
            predictions = pipeline.predict(X_test)

            benchmark_rows.append(
                {
                    "feature_set": feature_set_name,
                    "model_name": model_name,
                    "mae": mean_absolute_error(y_test, predictions),
                    "rmse": np.sqrt(mean_squared_error(y_test, predictions)),
                    "r2": r2_score(y_test, predictions),
                    "train_rows": len(X_train),
                    "test_rows": len(X_test),
                }
            )
            fitted_models[(feature_set_name, model_name)] = (pipeline, feature_columns, X_test, y_test)

    benchmark_df = pd.DataFrame(benchmark_rows).sort_values(
        ["mae", "rmse", "r2"],
        ascending=[True, True, False],
    )
    return benchmark_df, fitted_models


def fit_full_pipeline(
    frame: pd.DataFrame,
    target_column: str,
    feature_columns: list[str],
    categorical_columns: list[str],
    model,
    full_transform_fn=None,
) -> Pipeline:
    clean_frame = frame.copy().dropna(subset=[target_column])
    if full_transform_fn is not None:
        clean_frame = full_transform_fn(clean_frame.copy(), target_column)
    X = clean_frame[feature_columns]
    y = clean_frame[target_column]
    pipeline = build_pipeline(feature_columns, categorical_columns, clone(model))
    pipeline.fit(X, y)
    return pipeline


def permutation_importance_table(
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    n_repeats: int = 10,
) -> pd.DataFrame:
    importance = permutation_importance(
        pipeline,
        X_test,
        y_test,
        n_repeats=n_repeats,
        random_state=42,
        scoring="neg_mean_absolute_error",
    )
    return (
        pd.DataFrame(
            {
                "feature": X_test.columns,
                "importance_mean": importance.importances_mean,
                "importance_std": importance.importances_std,
            }
        )
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )


def save_model_bundle(
    pipeline: Pipeline,
    feature_columns: list[str],
    target_column: str,
    output_stem: str,
    metadata: dict[str, object],
) -> tuple[Path, Path]:
    model_path = MODEL_DIR / f"{output_stem}.joblib"
    metadata_path = MODEL_DIR / f"{output_stem}_metadata.json"

    joblib.dump(
        {
            "pipeline": pipeline,
            "feature_columns": feature_columns,
            "target_column": target_column,
        },
        model_path,
    )

    metadata_payload = {
        "feature_columns": feature_columns,
        "target_column": target_column,
        **metadata,
    }
    metadata_path.write_text(json.dumps(metadata_payload, indent=2), encoding="utf-8")
    return model_path, metadata_path
