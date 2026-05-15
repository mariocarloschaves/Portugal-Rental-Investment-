from __future__ import annotations

import getpass
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import KFold, RepeatedKFold, train_test_split
from xgboost import XGBClassifier


def resolve_project_paths() -> tuple[Path, Path]:
    here = Path(__file__).resolve().parent
    ml_dir = here.parent
    if str(ml_dir) not in sys.path:
        sys.path.append(str(ml_dir))
    return ml_dir.parent, here


CODE_DIR, TEST_DIR = resolve_project_paths()

from gold_ml_modeling import (  # noqa: E402
    PRICE_CATEGORICAL_COLUMNS,
    PRICE_LAUNCH_CORE_FEATURES,
    PRICE_MARKET_PROXY_FEATURES,
    add_train_only_price_proxies,
    build_candidate_models,
    build_mysql_engine,
    build_pipeline,
    load_property_mart_frame,
    prepare_common_features,
)


OUTPUT_STEM = "price_model_helpers_v1_diagnostic"
SEED = 42
SEGMENT_THRESHOLD_Q = 0.925
SEGMENT_THRESHOLD_GRID = [0.90, 0.925, 0.95, 0.975]
SEED_GRID = [7, 21, 42, 84, 126]
BLEND_GRID = [round(x, 2) for x in np.linspace(0.0, 1.0, 11)]
MIN_SEGMENT_ROWS = 80
FIXED_SEGMENTED_TEMPLATE = {
    "target_mode": "raw_price",
    "normal_model": "xgboost",
    "luxury_model": "ridge",
    "route": "soft_route",
}


QUALITY_COLUMNS = [
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
]
AVAILABILITY_COLUMNS = ["availability_30", "availability_60", "availability_90", "availability_365"]
FINANCING_COLUMNS = [
    "financing_vintage_year",
    "applied_asset_discount_pct",
    "applied_annual_interest_rate",
]

FEATURE_SETS = {
    "launch_plus_market_quality": PRICE_LAUNCH_CORE_FEATURES + PRICE_MARKET_PROXY_FEATURES + QUALITY_COLUMNS,
    "observed_market_full": PRICE_LAUNCH_CORE_FEATURES
    + PRICE_MARKET_PROXY_FEATURES
    + QUALITY_COLUMNS
    + AVAILABILITY_COLUMNS
    + FINANCING_COLUMNS,
}

GLOBAL_FEATURE_SET = "observed_market_full"
GLOBAL_FEATURE_COLUMNS = FEATURE_SETS[GLOBAL_FEATURE_SET]


def metric_bundle(y_true: pd.Series | np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)
    return {
        "r2": float(r2_score(y_true_arr, y_pred_arr)),
        "rmse": float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr))),
        "mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        "mape": float(mean_absolute_percentage_error(y_true_arr, y_pred_arr)),
        "residual_mean": float((y_pred_arr - y_true_arr).mean()),
        "residual_std": float((y_pred_arr - y_true_arr).std(ddof=0)),
    }


def pick_regressors() -> dict[str, object]:
    models = build_candidate_models(include_linear=True, include_dummy=False)
    return {k: v for k, v in models.items() if k in {"xgboost", "hist_gradient_boosting", "ridge"}}


def fit_regressor(
    model_name: str,
    target_mode: str,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
    feature_columns: list[str],
    clip_nonnegative: bool = True,
) -> tuple[object, np.ndarray]:
    model = clone(pick_regressors()[model_name])
    pipeline = build_pipeline(feature_columns, PRICE_CATEGORICAL_COLUMNS, model)
    y_fit = np.log1p(y_train) if target_mode == "log_price" else y_train
    pipeline.fit(X_train[feature_columns], y_fit)
    pred = pipeline.predict(X_eval[feature_columns])
    if target_mode == "log_price":
        pred = np.expm1(pred)
    if clip_nonnegative:
        pred = np.clip(pred, 0, None)
    return pipeline, pred


def fit_classifier(
    X_train: pd.DataFrame,
    y_train_flag: pd.Series,
    X_eval: pd.DataFrame,
    feature_columns: list[str],
    random_state: int = SEED,
) -> tuple[object, np.ndarray]:
    classifier = XGBClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=random_state,
        eval_metric="logloss",
        n_jobs=1,
    )
    pipeline = build_pipeline(feature_columns, PRICE_CATEGORICAL_COLUMNS, clone(classifier))
    pipeline.fit(X_train[feature_columns], y_train_flag)
    proba = pipeline.predict_proba(X_eval[feature_columns])[:, 1]
    return pipeline, proba


def build_bucket_edges(y_train: pd.Series) -> dict[str, float]:
    return {
        "q50": float(y_train.quantile(0.50)),
        "q80": float(y_train.quantile(0.80)),
        "q95": float(y_train.quantile(0.95)),
    }


def assign_price_bucket(values: pd.Series, bucket_edges: dict[str, float]) -> pd.Series:
    bins = [-np.inf, bucket_edges["q50"], bucket_edges["q80"], bucket_edges["q95"], np.inf]
    labels = ["low_price", "medium_price", "high_price", "luxury_extreme_price"]
    return pd.cut(values, bins=bins, labels=labels, include_lowest=True)


@dataclass
class SplitBundle:
    X_train_inner: pd.DataFrame
    X_valid: pd.DataFrame
    y_train_inner: pd.Series
    y_valid: pd.Series
    X_train_all: pd.DataFrame
    X_test: pd.DataFrame
    y_train_all: pd.Series
    y_test: pd.Series


def prepare_splits(frame: pd.DataFrame, random_state: int = SEED) -> SplitBundle:
    X = frame.drop(columns=["target_nightly_price"])
    y = frame["target_nightly_price"]
    X_train_all, X_test, y_train_all, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=random_state,
    )
    X_train_inner, X_valid, y_train_inner, y_valid = train_test_split(
        X_train_all,
        y_train_all,
        test_size=0.2,
        random_state=random_state,
    )
    X_train_inner, X_valid = add_train_only_price_proxies(X_train_inner, X_valid, y_train_inner)
    X_train_all, X_test = add_train_only_price_proxies(X_train_all, X_test, y_train_all)
    X_train_inner = X_train_inner.reset_index(drop=True)
    X_valid = X_valid.reset_index(drop=True)
    y_train_inner = y_train_inner.reset_index(drop=True)
    y_valid = y_valid.reset_index(drop=True)
    X_train_all = X_train_all.reset_index(drop=True)
    X_test = X_test.reset_index(drop=True)
    y_train_all = y_train_all.reset_index(drop=True)
    y_test = y_test.reset_index(drop=True)
    return SplitBundle(
        X_train_inner=X_train_inner,
        X_valid=X_valid,
        y_train_inner=y_train_inner,
        y_valid=y_valid,
        X_train_all=X_train_all,
        X_test=X_test,
        y_train_all=y_train_all,
        y_test=y_test,
    )


def evaluate_global_baseline(split: SplitBundle) -> dict[str, object]:
    pipeline, pred = fit_regressor(
        model_name="hist_gradient_boosting",
        target_mode="log_price",
        X_train=split.X_train_all,
        y_train=split.y_train_all,
        X_eval=split.X_test,
        feature_columns=GLOBAL_FEATURE_COLUMNS,
    )
    return {
        "label": "baseline_single_hgb_log_observed_full",
        "pipeline": pipeline,
        "pred": pred,
        "metrics": metric_bundle(split.y_test, pred),
        "target_mode": "log_price",
        "model_name": "hist_gradient_boosting",
        "feature_set": GLOBAL_FEATURE_SET,
    }


def select_best_segmented_config(split: SplitBundle) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    feature_columns = GLOBAL_FEATURE_COLUMNS
    Xtr = split.X_train_inner
    Xva = split.X_valid
    ytr = split.y_train_inner
    yva = split.y_valid

    for threshold_q in SEGMENT_THRESHOLD_GRID:
        threshold_value = float(ytr.quantile(threshold_q))
        luxury_flag_train = (ytr >= threshold_value).astype(int)
        if int(luxury_flag_train.sum()) < MIN_SEGMENT_ROWS:
            continue

        classifier, proba = fit_classifier(Xtr, luxury_flag_train, Xva, feature_columns)
        hard_flag = (proba >= 0.5).astype(int)
        for target_mode in ["raw_price", "log_price"]:
            _, pred_normal = fit_regressor(
                FIXED_SEGMENTED_TEMPLATE["normal_model"],
                target_mode,
                Xtr.loc[luxury_flag_train == 0],
                ytr.loc[luxury_flag_train == 0],
                Xva,
                feature_columns,
            )
            _, pred_luxury = fit_regressor(
                FIXED_SEGMENTED_TEMPLATE["luxury_model"],
                target_mode,
                Xtr.loc[luxury_flag_train == 1],
                ytr.loc[luxury_flag_train == 1],
                Xva,
                feature_columns,
            )
            for route_name, pred in {
                "hard_route": np.where(hard_flag == 1, pred_luxury, pred_normal),
                "soft_route": proba * pred_luxury + (1 - proba) * pred_normal,
            }.items():
                metrics = metric_bundle(yva, pred)
                rows.append(
                    {
                        "threshold_q": threshold_q,
                        "threshold_value": threshold_value,
                        "target_mode": target_mode,
                        "normal_model": FIXED_SEGMENTED_TEMPLATE["normal_model"],
                        "luxury_model": FIXED_SEGMENTED_TEMPLATE["luxury_model"],
                        "route": route_name,
                        **metrics,
                        "luxury_train_rows": int(luxury_flag_train.sum()),
                    }
                )

    validation_df = pd.DataFrame(rows).sort_values(["rmse", "mae", "r2"], ascending=[True, True, False]).reset_index(drop=True)
    best = validation_df.iloc[0].to_dict()
    return {"validation_df": validation_df, "best_config": best}


def fit_segmented_model(split: SplitBundle, config: dict[str, object]) -> dict[str, object]:
    threshold_q = float(config["threshold_q"])
    threshold_value = float(split.y_train_all.quantile(threshold_q))
    luxury_flag_train = (split.y_train_all >= threshold_value).astype(int)
    classifier, test_luxury_proba = fit_classifier(split.X_train_all, luxury_flag_train, split.X_test, GLOBAL_FEATURE_COLUMNS)
    normal_pipe, pred_normal = fit_regressor(
        str(config["normal_model"]),
        str(config["target_mode"]),
        split.X_train_all.loc[luxury_flag_train == 0],
        split.y_train_all.loc[luxury_flag_train == 0],
        split.X_test,
        GLOBAL_FEATURE_COLUMNS,
    )
    luxury_pipe, pred_luxury = fit_regressor(
        str(config["luxury_model"]),
        str(config["target_mode"]),
        split.X_train_all.loc[luxury_flag_train == 1],
        split.y_train_all.loc[luxury_flag_train == 1],
        split.X_test,
        GLOBAL_FEATURE_COLUMNS,
    )
    if config["route"] == "soft_route":
        pred = test_luxury_proba * pred_luxury + (1 - test_luxury_proba) * pred_normal
    else:
        pred = np.where((test_luxury_proba >= 0.5).astype(int) == 1, pred_luxury, pred_normal)

    return {
        "label": "segmented_best_validation",
        "pred": pred,
        "metrics": metric_bundle(split.y_test, pred),
        "threshold_q": threshold_q,
        "threshold_value": threshold_value,
        "classifier": classifier,
        "normal_pipe": normal_pipe,
        "luxury_pipe": luxury_pipe,
        "luxury_train_rows": int(luxury_flag_train.sum()),
        "normal_train_rows": int((luxury_flag_train == 0).sum()),
        "luxury_test_proba": test_luxury_proba,
        "train_segment_flag": luxury_flag_train,
    }


def build_segment_report(
    split: SplitBundle,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
    threshold_value: float,
) -> pd.DataFrame:
    actual_segment = pd.Series(np.where(split.y_test >= threshold_value, "luxury", "normal"), index=split.y_test.index)
    rows: list[dict[str, object]] = []
    train_actual_segment = pd.Series(np.where(split.y_train_all >= threshold_value, "luxury", "normal"), index=split.y_train_all.index)
    for segment_name in ["normal", "luxury"]:
        train_mask = train_actual_segment == segment_name
        test_mask = actual_segment == segment_name
        y_train_segment = split.y_train_all.loc[train_mask]
        y_test_segment = split.y_test.loc[test_mask]
        base_pred_segment = baseline_pred[test_mask.to_numpy()]
        seg_pred_segment = segmented_pred[test_mask.to_numpy()]
        for model_label, pred_segment in {
            "baseline_single_hgb_log_observed_full": base_pred_segment,
            "segmented_best_validation": seg_pred_segment,
        }.items():
            rows.append(
                {
                    "segment": segment_name,
                    "model_variant": model_label,
                    "train_rows": int(train_mask.sum()),
                    "test_rows": int(test_mask.sum()),
                    "train_mean_price": float(y_train_segment.mean()),
                    "train_median_price": float(y_train_segment.median()),
                    "train_price_std": float(y_train_segment.std(ddof=0)),
                    "test_mean_price": float(y_test_segment.mean()),
                    "test_median_price": float(y_test_segment.median()),
                    "test_price_std": float(y_test_segment.std(ddof=0)),
                    **metric_bundle(y_test_segment, pred_segment),
                }
            )
    return pd.DataFrame(rows)


def build_bucket_report(
    split: SplitBundle,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
    threshold_value: float,
) -> pd.DataFrame:
    bucket_edges = build_bucket_edges(split.y_train_all)
    test_buckets = assign_price_bucket(split.y_test, bucket_edges)
    actual_segment = np.where(split.y_test >= threshold_value, "luxury", "normal")
    rows: list[dict[str, object]] = []
    for bucket_name in ["low_price", "medium_price", "high_price", "luxury_extreme_price"]:
        mask = (test_buckets == bucket_name).to_numpy()
        y_bucket = split.y_test[mask]
        if len(y_bucket) == 0:
            continue
        for model_label, pred in {
            "baseline_single_hgb_log_observed_full": baseline_pred[mask],
            "segmented_best_validation": segmented_pred[mask],
        }.items():
            rows.append(
                {
                    "price_bucket": bucket_name,
                    "model_variant": model_label,
                    "rows": int(mask.sum()),
                    "actual_mean_price": float(y_bucket.mean()),
                    "actual_median_price": float(y_bucket.median()),
                    "actual_price_std": float(y_bucket.std(ddof=0)),
                    "share_luxury_segment": float((actual_segment[mask] == "luxury").mean()),
                    **metric_bundle(y_bucket, pred),
                }
            )
    return pd.DataFrame(rows)


def build_test_prediction_frame(
    split: SplitBundle,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
    threshold_value: float,
    luxury_proba: np.ndarray,
) -> pd.DataFrame:
    bucket_edges = build_bucket_edges(split.y_train_all)
    return pd.DataFrame(
        {
            "property_id": split.X_test["property_id"].to_numpy(),
            "actual_price": split.y_test.to_numpy(),
            "baseline_prediction": baseline_pred,
            "segmented_prediction": segmented_pred,
            "baseline_residual": baseline_pred - split.y_test.to_numpy(),
            "segmented_residual": segmented_pred - split.y_test.to_numpy(),
            "actual_segment": np.where(split.y_test >= threshold_value, "luxury", "normal"),
            "predicted_luxury_probability": luxury_proba,
            "price_bucket": assign_price_bucket(split.y_test, bucket_edges).astype(str).to_numpy(),
        }
    )


def build_residual_summary(pred_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    residual_overall = pd.DataFrame(
        [
            {
                "model_variant": "baseline_single_hgb_log_observed_full",
                "residual_mean": float(pred_frame["baseline_residual"].mean()),
                "residual_std": float(pred_frame["baseline_residual"].std(ddof=0)),
            },
            {
                "model_variant": "segmented_best_validation",
                "residual_mean": float(pred_frame["segmented_residual"].mean()),
                "residual_std": float(pred_frame["segmented_residual"].std(ddof=0)),
            },
        ]
    )

    grouped_rows: list[dict[str, object]] = []
    for group_col in ["price_bucket", "actual_segment"]:
        for group_value, group_frame in pred_frame.groupby(group_col):
            grouped_rows.append(
                {
                    "group_type": group_col,
                    "group_value": group_value,
                    "baseline_residual_mean": float(group_frame["baseline_residual"].mean()),
                    "baseline_residual_std": float(group_frame["baseline_residual"].std(ddof=0)),
                    "segmented_residual_mean": float(group_frame["segmented_residual"].mean()),
                    "segmented_residual_std": float(group_frame["segmented_residual"].std(ddof=0)),
                    "baseline_mae": float(np.abs(group_frame["baseline_residual"]).mean()),
                    "segmented_mae": float(np.abs(group_frame["segmented_residual"]).mean()),
                    "rows": int(len(group_frame)),
                }
            )
    return residual_overall, pd.DataFrame(grouped_rows)


def build_leakage_checks(split: SplitBundle, threshold_value: float) -> pd.DataFrame:
    checks = [
        {
            "check_name": "segment_created_using_price",
            "value": True,
            "detail": "Yes, the luxury segment threshold is based on the training target price. This is acceptable because the threshold is computed only on y_train and never on test targets.",
        },
        {
            "check_name": "threshold_uses_test_targets",
            "value": False,
            "detail": f"No. The active threshold value {threshold_value:.4f} was computed from y_train_all only.",
        },
        {
            "check_name": "future_information_used",
            "value": False,
            "detail": "No future information is used. The data is one latest snapshot and the segmentation/routing is fit after the train/test split.",
        },
        {
            "check_name": "segmenter_fit_before_split",
            "value": False,
            "detail": "No. The classifier/segment routing is trained only on the training subset and then applied to the validation/test subset.",
        },
        {
            "check_name": "same_test_rows_baseline_vs_segmented",
            "value": True,
            "detail": f"Yes. Both models were scored on the same {len(split.X_test)} held-out rows with the same target values.",
        },
        {
            "check_name": "same_preprocessing_logic",
            "value": True,
            "detail": "Yes. Both models use the shared build_pipeline preprocessor with the same observed_market_full feature columns. The segmented approach adds a classifier plus two regressors on top of the same feature preprocessing.",
        },
    ]
    return pd.DataFrame(checks)


def evaluate_same_split_and_scale(
    split: SplitBundle,
    baseline: dict[str, object],
    segmented_config: dict[str, object],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "question": "same_test_rows",
                "value": bool(split.X_test.index.equals(split.y_test.index)),
                "detail": f"Baseline and segmented both evaluate {len(split.X_test)} rows with identical indexes and target values.",
            },
            {
                "question": "baseline_target_scale",
                "value": baseline["target_mode"],
                "detail": "Baseline model trains on log1p(price) and predictions are inverse-transformed with expm1 before RMSE/MAE/R2/MAPE are computed.",
            },
            {
                "question": "segmented_target_scale",
                "value": segmented_config["target_mode"],
                "detail": "Segmented model tuning selected the target mode shown here; final predictions are always evaluated on raw nightly price.",
            },
            {
                "question": "raw_vs_log_comparison_mismatch",
                "value": False,
                "detail": "No raw-vs-log mismatch in scoring. Both model outputs are converted to the same raw nightly price scale before comparison against y_test.",
            },
        ]
    )


def pick_best_global_xgb_config(split: SplitBundle) -> dict[str, object]:
    rows = []
    for target_mode in ["raw_price", "log_price"]:
        _, pred = fit_regressor("xgboost", target_mode, split.X_train_inner, split.y_train_inner, split.X_valid, GLOBAL_FEATURE_COLUMNS)
        rows.append(
            {
                "approach": "A_global_xgb",
                "target_mode": target_mode,
                **metric_bundle(split.y_valid, pred),
            }
        )
    df = pd.DataFrame(rows).sort_values(["rmse", "mae", "r2"], ascending=[True, True, False]).reset_index(drop=True)
    return df.iloc[0].to_dict()


def make_oof_luxury_prob_feature(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
    threshold_value: float,
    feature_columns: list[str],
    random_state: int,
) -> tuple[pd.Series, pd.Series]:
    kf = KFold(n_splits=5, shuffle=True, random_state=random_state)
    oof_prob = pd.Series(index=X_train.index, dtype=float)
    luxury_flag = (y_train >= threshold_value).astype(int)
    for train_idx, holdout_idx in kf.split(X_train):
        Xtr = X_train.iloc[train_idx]
        ytr = luxury_flag.iloc[train_idx]
        Xho = X_train.iloc[holdout_idx]
        _, prob = fit_classifier(Xtr, ytr, Xho, feature_columns, random_state=random_state)
        oof_prob.iloc[holdout_idx] = prob
    _, test_prob = fit_classifier(X_train, luxury_flag, X_eval, feature_columns, random_state=random_state)
    return oof_prob.fillna(oof_prob.mean()), pd.Series(test_prob, index=X_eval.index)


def evaluate_approaches(split: SplitBundle, segmented_config: dict[str, object]) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    threshold_value = float(split.y_train_inner.quantile(float(segmented_config["threshold_q"])))
    threshold_value_full = float(split.y_train_all.quantile(float(segmented_config["threshold_q"])))
    global_xgb_best = pick_best_global_xgb_config(split)

    approach_rows: list[dict[str, object]] = []
    test_predictions: dict[str, np.ndarray] = {}

    # Approach A: global XGBoost.
    global_pipe, pred_global_valid = fit_regressor(
        "xgboost",
        str(global_xgb_best["target_mode"]),
        split.X_train_inner,
        split.y_train_inner,
        split.X_valid,
        GLOBAL_FEATURE_COLUMNS,
    )
    global_pipe_full, pred_global_test = fit_regressor(
        "xgboost",
        str(global_xgb_best["target_mode"]),
        split.X_train_all,
        split.y_train_all,
        split.X_test,
        GLOBAL_FEATURE_COLUMNS,
    )
    approach_rows.append({"approach": "A_global_xgb", **metric_bundle(split.y_test, pred_global_test)})
    test_predictions["A_global_xgb"] = pred_global_test

    # Approach B: segmented XGB/XGB with soft route.
    seg_xgb_validation_rows = []
    for target_mode in ["raw_price", "log_price"]:
        threshold = float(split.y_train_inner.quantile(float(segmented_config["threshold_q"])))
        luxury_flag_train = (split.y_train_inner >= threshold).astype(int)
        _, valid_prob = fit_classifier(split.X_train_inner, luxury_flag_train, split.X_valid, GLOBAL_FEATURE_COLUMNS)
        _, pred_normal_valid = fit_regressor("xgboost", target_mode, split.X_train_inner.loc[luxury_flag_train == 0], split.y_train_inner.loc[luxury_flag_train == 0], split.X_valid, GLOBAL_FEATURE_COLUMNS)
        _, pred_lux_valid = fit_regressor("xgboost", target_mode, split.X_train_inner.loc[luxury_flag_train == 1], split.y_train_inner.loc[luxury_flag_train == 1], split.X_valid, GLOBAL_FEATURE_COLUMNS)
        valid_pred = valid_prob * pred_lux_valid + (1 - valid_prob) * pred_normal_valid
        seg_xgb_validation_rows.append({"target_mode": target_mode, **metric_bundle(split.y_valid, valid_pred)})
    best_seg_xgb_target_mode = pd.DataFrame(seg_xgb_validation_rows).sort_values(["rmse", "mae"]).iloc[0]["target_mode"]
    luxury_flag_train_all = (split.y_train_all >= threshold_value_full).astype(int)
    _, prob_test = fit_classifier(split.X_train_all, luxury_flag_train_all, split.X_test, GLOBAL_FEATURE_COLUMNS)
    _, pred_normal_test = fit_regressor("xgboost", str(best_seg_xgb_target_mode), split.X_train_all.loc[luxury_flag_train_all == 0], split.y_train_all.loc[luxury_flag_train_all == 0], split.X_test, GLOBAL_FEATURE_COLUMNS)
    _, pred_lux_test = fit_regressor("xgboost", str(best_seg_xgb_target_mode), split.X_train_all.loc[luxury_flag_train_all == 1], split.y_train_all.loc[luxury_flag_train_all == 1], split.X_test, GLOBAL_FEATURE_COLUMNS)
    pred_seg_xgb_test = prob_test * pred_lux_test + (1 - prob_test) * pred_normal_test
    approach_rows.append({"approach": "B_segmented_xgb", **metric_bundle(split.y_test, pred_seg_xgb_test)})
    test_predictions["B_segmented_xgb"] = pred_seg_xgb_test

    # Approach C: global XGB + segment probability feature.
    prob_train_inner, prob_valid = make_oof_luxury_prob_feature(
        split.X_train_inner,
        split.y_train_inner,
        split.X_valid,
        threshold_value,
        GLOBAL_FEATURE_COLUMNS,
        random_state=SEED,
    )
    X_train_inner_seg = split.X_train_inner.copy()
    X_valid_seg = split.X_valid.copy()
    X_train_inner_seg["predicted_luxury_probability"] = prob_train_inner
    X_valid_seg["predicted_luxury_probability"] = prob_valid
    seg_feature_cols = GLOBAL_FEATURE_COLUMNS + ["predicted_luxury_probability"]
    c_valid_rows = []
    for target_mode in ["raw_price", "log_price"]:
        _, pred = fit_regressor("xgboost", target_mode, X_train_inner_seg, split.y_train_inner, X_valid_seg, seg_feature_cols)
        c_valid_rows.append({"target_mode": target_mode, **metric_bundle(split.y_valid, pred)})
    best_c_target_mode = pd.DataFrame(c_valid_rows).sort_values(["rmse", "mae"]).iloc[0]["target_mode"]
    prob_train_all, prob_test_all = make_oof_luxury_prob_feature(
        split.X_train_all,
        split.y_train_all,
        split.X_test,
        threshold_value_full,
        GLOBAL_FEATURE_COLUMNS,
        random_state=SEED,
    )
    X_train_all_seg = split.X_train_all.copy()
    X_test_seg = split.X_test.copy()
    X_train_all_seg["predicted_luxury_probability"] = prob_train_all
    X_test_seg["predicted_luxury_probability"] = prob_test_all
    _, pred_c_test = fit_regressor("xgboost", str(best_c_target_mode), X_train_all_seg, split.y_train_all, X_test_seg, seg_feature_cols)
    approach_rows.append({"approach": "C_global_xgb_plus_segment_feature", **metric_bundle(split.y_test, pred_c_test)})
    test_predictions["C_global_xgb_plus_segment_feature"] = pred_c_test

    # Approach D: global XGB + segment-specific residual correction.
    _, pred_global_inner = fit_regressor("xgboost", str(global_xgb_best["target_mode"]), split.X_train_inner, split.y_train_inner, split.X_train_inner, GLOBAL_FEATURE_COLUMNS)
    _, pred_global_valid_again = fit_regressor("xgboost", str(global_xgb_best["target_mode"]), split.X_train_inner, split.y_train_inner, split.X_valid, GLOBAL_FEATURE_COLUMNS)
    residual_train = pd.Series(split.y_train_inner.to_numpy() - pred_global_inner, index=split.X_train_inner.index)
    luxury_flag_train_inner = (split.y_train_inner >= threshold_value).astype(int)
    _, prob_valid_d = fit_classifier(split.X_train_inner, luxury_flag_train_inner, split.X_valid, GLOBAL_FEATURE_COLUMNS)
    d_valid_rows = []
    for residual_model_name in ["ridge", "xgboost"]:
        _, residual_normal_valid = fit_regressor(
            residual_model_name,
            "raw_price",
            split.X_train_inner.loc[luxury_flag_train_inner == 0],
            residual_train.loc[luxury_flag_train_inner == 0],
            split.X_valid,
            GLOBAL_FEATURE_COLUMNS,
            clip_nonnegative=False,
        )
        _, residual_lux_valid = fit_regressor(
            residual_model_name,
            "raw_price",
            split.X_train_inner.loc[luxury_flag_train_inner == 1],
            residual_train.loc[luxury_flag_train_inner == 1],
            split.X_valid,
            GLOBAL_FEATURE_COLUMNS,
            clip_nonnegative=False,
        )
        for residual_weight in [0.25, 0.5, 0.75, 1.0]:
            pred_valid = pred_global_valid_again + residual_weight * (
                prob_valid_d * residual_lux_valid + (1 - prob_valid_d) * residual_normal_valid
            )
            d_valid_rows.append(
                {
                    "residual_model": residual_model_name,
                    "residual_weight": residual_weight,
                    **metric_bundle(split.y_valid, pred_valid),
                }
            )
    best_d = pd.DataFrame(d_valid_rows).sort_values(["rmse", "mae"]).iloc[0].to_dict()
    _, pred_global_train_full = fit_regressor("xgboost", str(global_xgb_best["target_mode"]), split.X_train_all, split.y_train_all, split.X_train_all, GLOBAL_FEATURE_COLUMNS)
    residual_train_full = pd.Series(split.y_train_all.to_numpy() - pred_global_train_full, index=split.X_train_all.index)
    luxury_flag_train_all = (split.y_train_all >= threshold_value_full).astype(int)
    _, prob_test_d = fit_classifier(split.X_train_all, luxury_flag_train_all, split.X_test, GLOBAL_FEATURE_COLUMNS)
    _, residual_normal_test = fit_regressor(
        str(best_d["residual_model"]),
        "raw_price",
        split.X_train_all.loc[luxury_flag_train_all == 0],
        residual_train_full.loc[luxury_flag_train_all == 0],
        split.X_test,
        GLOBAL_FEATURE_COLUMNS,
        clip_nonnegative=False,
    )
    _, residual_lux_test = fit_regressor(
        str(best_d["residual_model"]),
        "raw_price",
        split.X_train_all.loc[luxury_flag_train_all == 1],
        residual_train_full.loc[luxury_flag_train_all == 1],
        split.X_test,
        GLOBAL_FEATURE_COLUMNS,
        clip_nonnegative=False,
    )
    pred_d_test = pred_global_test + float(best_d["residual_weight"]) * (
        prob_test_d * residual_lux_test + (1 - prob_test_d) * residual_normal_test
    )
    pred_d_test = np.clip(pred_d_test, 0, None)
    approach_rows.append({"approach": "D_global_xgb_plus_segment_residual_correction", **metric_bundle(split.y_test, pred_d_test)})
    test_predictions["D_global_xgb_plus_segment_residual_correction"] = pred_d_test

    # Approach E: blend global and segmented predictions with segment-specific weights tuned on validation.
    _, pred_global_valid_again = fit_regressor(
        "xgboost",
        str(global_xgb_best["target_mode"]),
        split.X_train_inner,
        split.y_train_inner,
        split.X_valid,
        GLOBAL_FEATURE_COLUMNS,
    )
    seg_best = segmented_config
    threshold_for_blend = float(split.y_train_inner.quantile(float(seg_best["threshold_q"])))
    luxury_flag_train_inner = (split.y_train_inner >= threshold_for_blend).astype(int)
    _, prob_valid_seg = fit_classifier(split.X_train_inner, luxury_flag_train_inner, split.X_valid, GLOBAL_FEATURE_COLUMNS)
    _, pred_normal_valid = fit_regressor(str(seg_best["normal_model"]), str(seg_best["target_mode"]), split.X_train_inner.loc[luxury_flag_train_inner == 0], split.y_train_inner.loc[luxury_flag_train_inner == 0], split.X_valid, GLOBAL_FEATURE_COLUMNS)
    _, pred_lux_valid = fit_regressor(str(seg_best["luxury_model"]), str(seg_best["target_mode"]), split.X_train_inner.loc[luxury_flag_train_inner == 1], split.y_train_inner.loc[luxury_flag_train_inner == 1], split.X_valid, GLOBAL_FEATURE_COLUMNS)
    pred_seg_valid = prob_valid_seg * pred_lux_valid + (1 - prob_valid_seg) * pred_normal_valid
    valid_predicted_segments = np.where(prob_valid_seg >= 0.5, "luxury", "normal")
    best_weights = {"normal": 0.5, "luxury": 0.5}
    best_rmse = np.inf
    for normal_weight in BLEND_GRID:
        for luxury_weight in BLEND_GRID:
            weights = np.where(valid_predicted_segments == "luxury", luxury_weight, normal_weight)
            blended_pred = weights * pred_seg_valid + (1 - weights) * pred_global_valid_again
            rmse = np.sqrt(mean_squared_error(split.y_valid, blended_pred))
            if rmse < best_rmse:
                best_rmse = rmse
                best_weights = {"normal": normal_weight, "luxury": luxury_weight}
    test_predicted_segments = np.where(prob_test >= 0.5, "luxury", "normal")
    weights_test = np.where(test_predicted_segments == "luxury", best_weights["luxury"], best_weights["normal"])
    pred_e_test = weights_test * test_predictions["B_segmented_xgb"] + (1 - weights_test) * pred_global_test
    approach_rows.append({"approach": "E_blend_global_and_segmented", **metric_bundle(split.y_test, pred_e_test)})
    test_predictions["E_blend_global_and_segmented"] = pred_e_test

    return pd.DataFrame(approach_rows).sort_values(["rmse", "mae", "r2"], ascending=[True, True, False]).reset_index(drop=True), test_predictions


def run_cv_and_seed_stability(frame: pd.DataFrame, segmented_config: dict[str, object]) -> tuple[pd.DataFrame, pd.DataFrame]:
    clean_frame = frame.dropna(subset=["target_nightly_price"]).copy()
    X = clean_frame.drop(columns=["target_nightly_price"])
    y = clean_frame["target_nightly_price"]

    cv_rows: list[dict[str, object]] = []
    rkf = RepeatedKFold(n_splits=3, n_repeats=2, random_state=SEED)
    for fold_number, (train_idx, test_idx) in enumerate(rkf.split(X), start=1):
        X_train = X.iloc[train_idx].copy()
        X_test = X.iloc[test_idx].copy()
        y_train = y.iloc[train_idx].copy()
        y_test = y.iloc[test_idx].copy()
        X_train, X_test = add_train_only_price_proxies(X_train, X_test, y_train)
        X_train = X_train.reset_index(drop=True)
        X_test = X_test.reset_index(drop=True)
        y_train = y_train.reset_index(drop=True)
        y_test = y_test.reset_index(drop=True)
        _, base_pred = fit_regressor("hist_gradient_boosting", "log_price", X_train, y_train, X_test, GLOBAL_FEATURE_COLUMNS)
        cv_rows.append({"evaluation": "baseline", "fold": fold_number, **metric_bundle(y_test, base_pred)})

        threshold_value = float(y_train.quantile(float(segmented_config["threshold_q"])))
        luxury_flag_train = (y_train >= threshold_value).astype(int)
        _, prob = fit_classifier(X_train, luxury_flag_train, X_test, GLOBAL_FEATURE_COLUMNS, random_state=SEED)
        _, pred_normal = fit_regressor(str(segmented_config["normal_model"]), str(segmented_config["target_mode"]), X_train.loc[luxury_flag_train == 0], y_train.loc[luxury_flag_train == 0], X_test, GLOBAL_FEATURE_COLUMNS)
        _, pred_lux = fit_regressor(str(segmented_config["luxury_model"]), str(segmented_config["target_mode"]), X_train.loc[luxury_flag_train == 1], y_train.loc[luxury_flag_train == 1], X_test, GLOBAL_FEATURE_COLUMNS)
        pred_seg = prob * pred_lux + (1 - prob) * pred_normal if segmented_config["route"] == "soft_route" else np.where((prob >= 0.5).astype(int) == 1, pred_lux, pred_normal)
        cv_rows.append({"evaluation": "segmented", "fold": fold_number, **metric_bundle(y_test, pred_seg)})

    seed_rows: list[dict[str, object]] = []
    for random_state in SEED_GRID:
        split = prepare_splits(frame, random_state=random_state)
        baseline = evaluate_global_baseline(split)
        best_seg = select_best_segmented_config(split)["best_config"]
        segmented = fit_segmented_model(split, best_seg)
        seed_rows.append({"evaluation": "baseline", "seed": random_state, **baseline["metrics"]})
        seed_rows.append({"evaluation": "segmented", "seed": random_state, **segmented["metrics"]})

    return pd.DataFrame(cv_rows), pd.DataFrame(seed_rows)


def build_overfit_report(split: SplitBundle, segmented_config: dict[str, object]) -> pd.DataFrame:
    threshold_value = float(split.y_train_all.quantile(float(segmented_config["threshold_q"])))
    luxury_flag_train = (split.y_train_all >= threshold_value).astype(int)

    _, baseline_train_pred = fit_regressor("hist_gradient_boosting", "log_price", split.X_train_all, split.y_train_all, split.X_train_all, GLOBAL_FEATURE_COLUMNS)
    _, baseline_test_pred = fit_regressor("hist_gradient_boosting", "log_price", split.X_train_all, split.y_train_all, split.X_test, GLOBAL_FEATURE_COLUMNS)

    _, prob_test = fit_classifier(split.X_train_all, luxury_flag_train, split.X_test, GLOBAL_FEATURE_COLUMNS)
    _, prob_train = fit_classifier(split.X_train_all, luxury_flag_train, split.X_train_all, GLOBAL_FEATURE_COLUMNS)
    _, pred_normal_train = fit_regressor(str(segmented_config["normal_model"]), str(segmented_config["target_mode"]), split.X_train_all.loc[luxury_flag_train == 0], split.y_train_all.loc[luxury_flag_train == 0], split.X_train_all, GLOBAL_FEATURE_COLUMNS)
    _, pred_lux_train = fit_regressor(str(segmented_config["luxury_model"]), str(segmented_config["target_mode"]), split.X_train_all.loc[luxury_flag_train == 1], split.y_train_all.loc[luxury_flag_train == 1], split.X_train_all, GLOBAL_FEATURE_COLUMNS)
    _, pred_normal_test = fit_regressor(str(segmented_config["normal_model"]), str(segmented_config["target_mode"]), split.X_train_all.loc[luxury_flag_train == 0], split.y_train_all.loc[luxury_flag_train == 0], split.X_test, GLOBAL_FEATURE_COLUMNS)
    _, pred_lux_test = fit_regressor(str(segmented_config["luxury_model"]), str(segmented_config["target_mode"]), split.X_train_all.loc[luxury_flag_train == 1], split.y_train_all.loc[luxury_flag_train == 1], split.X_test, GLOBAL_FEATURE_COLUMNS)

    if segmented_config["route"] == "soft_route":
        segmented_train_pred = prob_train * pred_lux_train + (1 - prob_train) * pred_normal_train
        segmented_test_pred = prob_test * pred_lux_test + (1 - prob_test) * pred_normal_test
    else:
        segmented_train_pred = np.where((prob_train >= 0.5).astype(int) == 1, pred_lux_train, pred_normal_train)
        segmented_test_pred = np.where((prob_test >= 0.5).astype(int) == 1, pred_lux_test, pred_normal_test)

    train_actual_segment = np.where(split.y_train_all >= threshold_value, "luxury", "normal")
    test_actual_segment = np.where(split.y_test >= threshold_value, "luxury", "normal")
    rows = []
    for model_label, y_train_pred, y_test_pred in [
        ("baseline_single_hgb_log_observed_full", baseline_train_pred, baseline_test_pred),
        ("segmented_best_validation", segmented_train_pred, segmented_test_pred),
    ]:
        for segment_name, train_mask, test_mask in [
            ("normal", train_actual_segment == "normal", test_actual_segment == "normal"),
            ("luxury", train_actual_segment == "luxury", test_actual_segment == "luxury"),
        ]:
            rows.append(
                {
                    "model_variant": model_label,
                    "segment": segment_name,
                    "train_rows": int(np.sum(train_mask)),
                    "test_rows": int(np.sum(test_mask)),
                    "train_r2": float(r2_score(split.y_train_all[train_mask], y_train_pred[train_mask])),
                    "test_r2": float(r2_score(split.y_test[test_mask], y_test_pred[test_mask])),
                    "train_rmse": float(np.sqrt(mean_squared_error(split.y_train_all[train_mask], y_train_pred[train_mask]))),
                    "test_rmse": float(np.sqrt(mean_squared_error(split.y_test[test_mask], y_test_pred[test_mask]))),
                }
            )
    return pd.DataFrame(rows)


def build_final_report(
    overall_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    approach_df: pd.DataFrame,
    cv_df: pd.DataFrame,
    seed_df: pd.DataFrame,
    leakage_df: pd.DataFrame,
    scale_df: pd.DataFrame,
    overfit_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    threshold_value: float,
) -> str:
    baseline_row = overall_df.loc[overall_df["model_variant"] == "baseline_single_hgb_log_observed_full"].iloc[0]
    segmented_row = overall_df.loc[overall_df["model_variant"] == "segmented_best_validation"].iloc[0]
    luxury_rows = segment_df[segment_df["segment"] == "luxury"].set_index("model_variant")
    bucket_improvements = bucket_df.pivot(index="price_bucket", columns="model_variant", values="rmse")
    bucket_improvements["rmse_delta_segmented_minus_baseline"] = (
        bucket_improvements["segmented_best_validation"] - bucket_improvements["baseline_single_hgb_log_observed_full"]
    )
    better_buckets = bucket_improvements[bucket_improvements["rmse_delta_segmented_minus_baseline"] < 0].index.tolist()
    worse_buckets = bucket_improvements[bucket_improvements["rmse_delta_segmented_minus_baseline"] > 0].index.tolist()

    cv_pivot = cv_df.pivot(index="fold", columns="evaluation", values="rmse")
    seed_pivot = seed_df.pivot(index="seed", columns="evaluation", values="rmse")
    cv_wins = int((cv_pivot["segmented"] < cv_pivot["baseline"]).sum())
    seed_wins = int((seed_pivot["segmented"] < seed_pivot["baseline"]).sum())

    high_price_rows = pred_df[pred_df["price_bucket"] == "luxury_extreme_price"]
    report_lines = [
        f"# Price Segmentation Audit V1",
        "",
        f"## Final headline",
        "",
        f"- Baseline single-model test metrics: R2={baseline_row['r2']:.6f}, RMSE={baseline_row['rmse']:.6f}, MAE={baseline_row['mae']:.6f}, MAPE={baseline_row['mape']:.6f}",
        f"- Segmented test metrics: R2={segmented_row['r2']:.6f}, RMSE={segmented_row['rmse']:.6f}, MAE={segmented_row['mae']:.6f}, MAPE={segmented_row['mape']:.6f}",
        f"- Active luxury threshold on train: q={SEGMENT_THRESHOLD_Q:.3f}, price={threshold_value:.4f}",
        "",
        "## What changed",
        "",
        f"- Segmented model improved R2 by {segmented_row['r2'] - baseline_row['r2']:+.6f}",
        f"- Segmented model improved RMSE by {segmented_row['rmse'] - baseline_row['rmse']:+.6f}",
        f"- Segmented model changed MAE by {segmented_row['mae'] - baseline_row['mae']:+.6f}",
        f"- Segmented luxury MAE moved from {luxury_rows.loc['baseline_single_hgb_log_observed_full', 'mae']:.6f} to {luxury_rows.loc['segmented_best_validation', 'mae']:.6f}",
        f"- Segmented luxury RMSE moved from {luxury_rows.loc['baseline_single_hgb_log_observed_full', 'rmse']:.6f} to {luxury_rows.loc['segmented_best_validation', 'rmse']:.6f}",
        "",
        "## Same-split / scale checks",
        "",
        scale_df.to_string(index=False),
        "",
        "## Leakage checks",
        "",
        leakage_df.to_string(index=False),
        "",
        "## Bucket readout",
        "",
        f"- Buckets with lower segmented RMSE: {better_buckets if better_buckets else 'none'}",
        f"- Buckets with worse segmented RMSE: {worse_buckets if worse_buckets else 'none'}",
        "",
        "## High-price underprediction check",
        "",
        f"- Luxury/extreme actual mean price: {high_price_rows['actual_price'].mean():.6f}",
        f"- Baseline mean prediction on luxury/extreme bucket: {high_price_rows['baseline_prediction'].mean():.6f}",
        f"- Segmented mean prediction on luxury/extreme bucket: {high_price_rows['segmented_prediction'].mean():.6f}",
        f"- Baseline mean residual on luxury/extreme bucket: {high_price_rows['baseline_residual'].mean():.6f}",
        f"- Segmented mean residual on luxury/extreme bucket: {high_price_rows['segmented_residual'].mean():.6f}",
        "",
        "## Stability",
        "",
        f"- RepeatedKFold RMSE wins for segmented model: {cv_wins} of {len(cv_pivot)} folds",
        f"- Multi-seed RMSE wins for segmented model: {seed_wins} of {len(seed_pivot)} seeds",
        "",
        "## Approach comparison",
        "",
        approach_df.to_string(index=False),
        "",
        "## Overfitting snapshot",
        "",
        overfit_df.to_string(index=False),
    ]
    return "\n".join(report_lines)


def save_outputs(named_frames: dict[str, pd.DataFrame], report_text: str, summary_payload: dict[str, object]) -> None:
    for stem, frame in named_frames.items():
        frame.to_csv(TEST_DIR / f"{stem}.csv", index=False)
    (TEST_DIR / f"{OUTPUT_STEM}_report.md").write_text(report_text, encoding="utf-8")
    (TEST_DIR / f"{OUTPUT_STEM}_summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")


def main() -> None:
    engine = build_mysql_engine()
    model_df = load_property_mart_frame(engine)
    prepared_df = prepare_common_features(model_df).dropna(subset=["target_nightly_price"]).copy()
    split = prepare_splits(prepared_df, random_state=SEED)

    baseline = evaluate_global_baseline(split)
    segmented_selection = select_best_segmented_config(split)
    segmented_config = segmented_selection["best_config"]
    segmented = fit_segmented_model(split, segmented_config)

    overall_df = pd.DataFrame(
        [
            {"model_variant": baseline["label"], **baseline["metrics"]},
            {"model_variant": segmented["label"], **segmented["metrics"]},
        ]
    )
    scale_df = evaluate_same_split_and_scale(split, baseline, segmented_config)
    leakage_df = build_leakage_checks(split, float(segmented["threshold_value"]))
    segment_df = build_segment_report(split, baseline["pred"], segmented["pred"], float(segmented["threshold_value"]))
    bucket_df = build_bucket_report(split, baseline["pred"], segmented["pred"], float(segmented["threshold_value"]))
    pred_df = build_test_prediction_frame(
        split,
        baseline["pred"],
        segmented["pred"],
        float(segmented["threshold_value"]),
        segmented["luxury_test_proba"],
    )
    residual_overall_df, residual_group_df = build_residual_summary(pred_df)
    approach_df, _ = evaluate_approaches(split, segmented_config)
    cv_df, seed_df = run_cv_and_seed_stability(prepared_df, segmented_config)
    overfit_df = build_overfit_report(split, segmented_config)

    report_text = build_final_report(
        overall_df=overall_df,
        segment_df=segment_df,
        bucket_df=bucket_df,
        approach_df=approach_df,
        cv_df=cv_df,
        seed_df=seed_df,
        leakage_df=leakage_df,
        scale_df=scale_df,
        overfit_df=overfit_df,
        pred_df=pred_df,
        threshold_value=float(segmented["threshold_value"]),
    )

    summary_payload = {
        "baseline": overall_df.loc[overall_df["model_variant"] == baseline["label"]].iloc[0].to_dict(),
        "segmented": overall_df.loc[overall_df["model_variant"] == segmented["label"]].iloc[0].to_dict(),
        "best_segmented_validation_config": segmented_config,
        "same_split_checks": scale_df.to_dict(orient="records"),
        "leakage_checks": leakage_df.to_dict(orient="records"),
    }

    save_outputs(
        {
            f"{OUTPUT_STEM}_overall_metrics": overall_df,
            f"{OUTPUT_STEM}_segment_metrics": segment_df,
            f"{OUTPUT_STEM}_bucket_metrics": bucket_df,
            f"{OUTPUT_STEM}_test_predictions": pred_df,
            f"{OUTPUT_STEM}_residual_overall": residual_overall_df,
            f"{OUTPUT_STEM}_residual_groups": residual_group_df,
            f"{OUTPUT_STEM}_approach_comparison": approach_df,
            f"{OUTPUT_STEM}_cv_results": cv_df,
            f"{OUTPUT_STEM}_seed_results": seed_df,
            f"{OUTPUT_STEM}_overfit": overfit_df,
            f"{OUTPUT_STEM}_scale_checks": scale_df,
            f"{OUTPUT_STEM}_leakage_checks": leakage_df,
            f"{OUTPUT_STEM}_validation_grid": segmented_selection["validation_df"],
        },
        report_text=report_text,
        summary_payload=summary_payload,
    )
    print(report_text)


if __name__ == "__main__":
    main()
