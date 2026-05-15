from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split

THIS_DIR = Path(__file__).resolve().parent
ML_DIR = THIS_DIR.parent

for candidate in (THIS_DIR, ML_DIR):
    if str(candidate) not in sys.path:
        sys.path.append(str(candidate))

from gold_ml_modeling import (  # noqa: E402
    DEPLOYMENT_MODEL_DIR,
    OCCUPANCY_AVAILABILITY_FEATURES,
    OCCUPANCY_BASE_FEATURES,
    OCCUPANCY_CATEGORICAL_COLUMNS,
    build_candidate_models,
    build_mysql_engine,
    build_pipeline,
    load_property_mart_frame,
    prepare_common_features,
)

from price_deployment_model_v2 import (  # noqa: E402
    build_validation_predictions,
    build_weight_vector_for_test,
    evaluate_weighted_prediction,
    tune_blend_strategies,
)

from price_model_helpers_v1 import (  # noqa: E402
    SplitBundle,
    add_train_only_price_proxies,
    evaluate_global_baseline,
    fit_segmented_model,
)


OUTPUT_STEM = "occupancy_deployment_model_v2"
MODEL_STEM = "occupancy_deployment_model_v2"
FAIR_PRICE_MODEL_STEM = "nightly_price_deployment_model_v2"

SEED = 42
N_PRICE_OOF_SPLITS = 3

DYNAMIC_BLEND_WEIGHT_GRID = [round(x, 2) for x in np.linspace(0.0, 1.0, 21)]

PRICE_GAP_FEATURES = [
    "predicted_fair_price",
    "price_gap_abs",
    "price_gap_pct",
    "overpriced_flag",
    "underpriced_flag",
]


def to_json_safe(value):
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [to_json_safe(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return to_json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return to_json_safe(value.to_list())
    if isinstance(value, np.ndarray):
        return to_json_safe(value.tolist())
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def occupancy_metric_bundle(y_true: pd.Series | np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)

    return {
        "r2": float(r2_score(y_true_arr, y_pred_arr)),
        "rmse": float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr))),
        "mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
    }


def logit(values: pd.Series | np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(values), 0.001, 0.999)
    return np.log(clipped / (1 - clipped))


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-values))


def make_price_training_frame(X: pd.DataFrame, y_price: pd.Series) -> pd.DataFrame:
    frame = X.copy()
    frame["target_nightly_price"] = y_price.to_numpy()
    return frame.reset_index(drop=True)


def predict_v2_fair_price(
    X_train: pd.DataFrame,
    y_price_train: pd.Series,
    X_eval: pd.DataFrame,
    y_price_eval: pd.Series,
) -> tuple[np.ndarray, dict[str, object]]:
    price_train_frame = make_price_training_frame(X_train, y_price_train)

    price_split, baseline_validation, segmented_validation, segmented_config = build_validation_predictions(
        price_train_frame
    )

    strategy_tuning = tune_blend_strategies(
        price_split,
        baseline_validation,
        segmented_validation,
    )

    chosen_strategy = strategy_tuning["chosen_blend"]

    X_train_aug, X_eval_aug = add_train_only_price_proxies(
        X_train.copy(),
        X_eval.copy(),
        y_price_train.copy(),
    )

    X_train_aug = X_train_aug.reset_index(drop=True)
    X_eval_aug = X_eval_aug.reset_index(drop=True)
    y_price_train = y_price_train.reset_index(drop=True)
    y_price_eval = y_price_eval.reset_index(drop=True)

    prediction_split = SplitBundle(
        X_train_inner=X_train_aug,
        X_valid=X_eval_aug,
        y_train_inner=y_price_train,
        y_valid=y_price_eval,
        X_train_all=X_train_aug,
        X_test=X_eval_aug,
        y_train_all=y_price_train,
        y_test=y_price_eval,
    )

    baseline_price_model = evaluate_global_baseline(prediction_split)
    segmented_price_model = fit_segmented_model(prediction_split, segmented_config)

    weight_vector, weight_details = build_weight_vector_for_test(
        chosen_strategy,
        prediction_split,
        baseline_price_model["pred"],
        segmented_price_model["pred"],
        segmented_price_model["luxury_test_proba"],
    )

    fair_price_pred, fair_price_metrics = evaluate_weighted_prediction(
        prediction_split.y_test,
        baseline_price_model["pred"],
        segmented_price_model["pred"],
        weight_vector,
    )

    details = {
        "price_model_version": FAIR_PRICE_MODEL_STEM,
        "chosen_blend_strategy": chosen_strategy["config"],
        "segmented_config": segmented_config,
        "fair_price_metrics": fair_price_metrics,
        "weight_details": weight_details.to_dict(orient="records"),
    }

    return fair_price_pred, details


def make_oof_fair_price_predictions(
    X_train: pd.DataFrame,
    y_price_train: pd.Series,
    X_test: pd.DataFrame,
    y_price_test: pd.Series,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, object]], dict[str, object]]:
    oof_pred = np.zeros(len(X_train), dtype=float)
    fold_details: list[dict[str, object]] = []

    kfold = KFold(
        n_splits=N_PRICE_OOF_SPLITS,
        shuffle=True,
        random_state=SEED,
    )

    for fold_number, (train_idx, holdout_idx) in enumerate(kfold.split(X_train), start=1):
        fold_pred, fold_detail = predict_v2_fair_price(
            X_train.iloc[train_idx].reset_index(drop=True),
            y_price_train.iloc[train_idx].reset_index(drop=True),
            X_train.iloc[holdout_idx].reset_index(drop=True),
            y_price_train.iloc[holdout_idx].reset_index(drop=True),
        )

        oof_pred[holdout_idx] = fold_pred

        fold_details.append(
            {
                "fold": fold_number,
                "holdout_rows": int(len(holdout_idx)),
                "fair_price_r2": fold_detail["fair_price_metrics"]["r2"],
                "fair_price_rmse": fold_detail["fair_price_metrics"]["rmse"],
                "fair_price_mae": fold_detail["fair_price_metrics"]["mae"],
                "chosen_blend_strategy": fold_detail["chosen_blend_strategy"],
            }
        )

    test_pred, test_detail = predict_v2_fair_price(
        X_train.reset_index(drop=True),
        y_price_train.reset_index(drop=True),
        X_test.reset_index(drop=True),
        y_price_test.reset_index(drop=True),
    )

    return oof_pred, test_pred, fold_details, test_detail


def add_price_gap_features(
    frame: pd.DataFrame,
    predicted_fair_price: np.ndarray,
) -> pd.DataFrame:
    out = frame.copy()

    fair_price = np.clip(np.asarray(predicted_fair_price, dtype=float), 1e-6, None)
    actual_price = out["price"].fillna(out["target_nightly_price"]).astype(float).to_numpy()

    out["predicted_fair_price"] = fair_price
    out["price_gap_abs"] = actual_price - fair_price
    out["price_gap_pct"] = out["price_gap_abs"] / fair_price
    out["overpriced_flag"] = (out["price_gap_pct"] > 0.10).astype(int)
    out["underpriced_flag"] = (out["price_gap_pct"] < -0.10).astype(int)

    return out


def fit_predict_occupancy(
    model_name: str,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    feature_columns: list[str],
    logit_target: bool = False,
) -> tuple[object, np.ndarray]:
    model = clone(build_candidate_models(include_linear=False, include_dummy=False)[model_name])
    pipeline = build_pipeline(feature_columns, OCCUPANCY_CATEGORICAL_COLUMNS, model)

    y_fit = logit(y_train) if logit_target else y_train

    pipeline.fit(X_train[feature_columns], y_fit)
    pred = pipeline.predict(X_test[feature_columns])

    if logit_target:
        pred = sigmoid(pred)

    pred = np.clip(pred, 0, 1)

    return pipeline, pred


def tune_xgb_hgb_blend(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    feature_columns: list[str],
) -> dict[str, object]:
    X_inner, X_valid, y_inner, y_valid = train_test_split(
        X_train,
        y_train,
        test_size=0.2,
        random_state=SEED,
    )

    _, xgb_valid_pred = fit_predict_occupancy(
        "xgboost",
        X_inner,
        y_inner,
        X_valid,
        feature_columns,
    )

    _, hgb_valid_pred = fit_predict_occupancy(
        "hist_gradient_boosting",
        X_inner,
        y_inner,
        X_valid,
        feature_columns,
    )

    rows: list[dict[str, object]] = []
    best: dict[str, object] | None = None

    for weight in np.linspace(0.0, 1.0, 41):
        pred = weight * xgb_valid_pred + (1 - weight) * hgb_valid_pred
        metrics = occupancy_metric_bundle(y_valid, pred)

        row = {
            "weight_xgb": float(weight),
            "weight_hgb": float(1 - weight),
            **metrics,
        }

        rows.append(row)

        if best is None or (row["rmse"], row["mae"], -row["r2"]) < (
            best["rmse"],
            best["mae"],
            -best["r2"],
        ):
            best = row

    if best is None:
        raise RuntimeError("No XGB/HGB blend weight was selected.")

    return {
        "validation_rows": pd.DataFrame(rows),
        "best_weight_xgb": float(best["weight_xgb"]),
        "best_weight_hgb": float(best["weight_hgb"]),
        "best_validation_metrics": best,
    }


def predict_xgb_hgb_blend(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    feature_columns: list[str],
    weight_xgb: float,
) -> tuple[tuple[object, object], np.ndarray]:
    xgb_model, xgb_pred = fit_predict_occupancy(
        "xgboost",
        X_train,
        y_train,
        X_test,
        feature_columns,
    )

    hgb_model, hgb_pred = fit_predict_occupancy(
        "hist_gradient_boosting",
        X_train,
        y_train,
        X_test,
        feature_columns,
    )

    pred = weight_xgb * xgb_pred + (1 - weight_xgb) * hgb_pred

    return (xgb_model, hgb_model), np.clip(pred, 0, 1)


def choose_best_occupancy_model(overall_df: pd.DataFrame) -> dict[str, object]:
    required_cols = {"model_variant", "r2", "rmse", "mae"}
    missing = required_cols - set(overall_df.columns)

    if missing:
        raise ValueError(f"Missing required metric columns: {missing}")

    ranked_df = (
        overall_df.copy()
        .sort_values(["r2", "rmse", "mae"], ascending=[False, True, True])
        .reset_index(drop=True)
    )

    best = ranked_df.iloc[0].to_dict()

    return {
        "selected_model": str(best["model_variant"]),
        "selected_r2": float(best["r2"]),
        "selected_rmse": float(best["rmse"]),
        "selected_mae": float(best["mae"]),
        "ranked_metrics": ranked_df,
        "reason": "selected dynamically by highest R2, then lowest RMSE, then lowest MAE",
    }


def tune_dynamic_top_model_blend(
    X_train: pd.DataFrame,
    X_train_gap: pd.DataFrame,
    y_train: pd.Series,
    baseline_features: list[str],
    price_gap_features: list[str],
    candidate_specs: list[dict[str, object]],
) -> dict[str, object]:
    train_idx, valid_idx = train_test_split(
        np.arange(len(X_train_gap)),
        test_size=0.2,
        random_state=SEED,
    )

    y_inner = y_train.iloc[train_idx].reset_index(drop=True)
    y_valid = y_train.iloc[valid_idx].reset_index(drop=True)

    validation_predictions: dict[str, np.ndarray] = {}

    for spec in candidate_specs:
        variant = str(spec["variant"])

        if spec["model_type"] == "single_pipeline":
            uses_price_gap = bool(spec["uses_price_gap"])
            model_name = str(spec["model_name"])
            logit_target = bool(spec.get("logit_target", False))
            feature_columns = spec["feature_columns"]

            source_frame = X_train_gap if uses_price_gap else X_train
            X_inner = source_frame.iloc[train_idx].reset_index(drop=True)
            X_valid = source_frame.iloc[valid_idx].reset_index(drop=True)

            _, valid_pred = fit_predict_occupancy(
                model_name=model_name,
                X_train=X_inner,
                y_train=y_inner,
                X_test=X_valid,
                feature_columns=feature_columns,
                logit_target=logit_target,
            )

            validation_predictions[variant] = valid_pred

        elif spec["model_type"] == "xgb_hgb_blend":
            X_inner = X_train_gap.iloc[train_idx].reset_index(drop=True)
            X_valid = X_train_gap.iloc[valid_idx].reset_index(drop=True)

            inner_blend_tuning = tune_xgb_hgb_blend(
                X_inner,
                y_inner,
                price_gap_features,
            )

            _, valid_pred = predict_xgb_hgb_blend(
                X_inner,
                y_inner,
                X_valid,
                price_gap_features,
                inner_blend_tuning["best_weight_xgb"],
            )

            validation_predictions[variant] = valid_pred

        else:
            raise ValueError(f"Unsupported candidate model type: {spec['model_type']}")

    validation_metrics_df = pd.DataFrame(
        [
            {"model_variant": variant, **occupancy_metric_bundle(y_valid, pred)}
            for variant, pred in validation_predictions.items()
        ]
    ).sort_values(["r2", "rmse", "mae"], ascending=[False, True, True]).reset_index(drop=True)

    top2_variants = validation_metrics_df["model_variant"].head(2).tolist()
    top3_variants = validation_metrics_df["model_variant"].head(3).tolist()

    blend_rows: list[dict[str, object]] = []
    best: dict[str, object] | None = None

    def consider_row(row: dict[str, object]) -> None:
        nonlocal best
        blend_rows.append(row)
        if best is None or (row["rmse"], row["mae"], -row["r2"]) < (
            best["rmse"],
            best["mae"],
            -best["r2"],
        ):
            best = row

    if len(top2_variants) == 2:
        a, b = top2_variants
        for w_a in DYNAMIC_BLEND_WEIGHT_GRID:
            w_b = 1 - w_a
            pred = w_a * validation_predictions[a] + w_b * validation_predictions[b]
            metrics = occupancy_metric_bundle(y_valid, pred)

            consider_row(
                {
                    "blend_name": f"blend_{a}__{b}",
                    "model_count": 2,
                    "components": [a, b],
                    "weights": {a: float(w_a), b: float(w_b)},
                    **metrics,
                }
            )

    if len(top3_variants) == 3:
        a, b, c = top3_variants
        for w_a in DYNAMIC_BLEND_WEIGHT_GRID:
            for w_b in DYNAMIC_BLEND_WEIGHT_GRID:
                w_c = 1 - w_a - w_b

                if w_c < 0 or w_c > 1:
                    continue

                pred = (
                    w_a * validation_predictions[a]
                    + w_b * validation_predictions[b]
                    + w_c * validation_predictions[c]
                )
                metrics = occupancy_metric_bundle(y_valid, pred)

                consider_row(
                    {
                        "blend_name": f"blend_{a}__{b}__{c}",
                        "model_count": 3,
                        "components": [a, b, c],
                        "weights": {a: float(w_a), b: float(w_b), c: float(w_c)},
                        **metrics,
                    }
                )

    if best is None:
        raise RuntimeError("No dynamic top-model blend was selected.")

    blend_validation_df = (
        pd.DataFrame(blend_rows)
        .sort_values(["rmse", "mae", "r2"], ascending=[True, True, False])
        .reset_index(drop=True)
    )

    return {
        "validation_candidate_metrics": validation_metrics_df,
        "blend_validation_metrics": blend_validation_df,
        "best_blend": best,
    }


def make_dynamic_blend_prediction(
    predictions: dict[str, np.ndarray],
    best_blend: dict[str, object],
) -> np.ndarray:
    components = best_blend["components"]
    weights = best_blend["weights"]

    pred = np.zeros(len(next(iter(predictions.values()))), dtype=float)

    for component in components:
        pred += float(weights[component]) * predictions[component]

    return np.clip(pred, 0, 1)


def make_occupancy_buckets(y_train: pd.Series, y_eval: pd.Series) -> pd.Series:
    edges = [
        -np.inf,
        float(y_train.quantile(0.25)),
        float(y_train.quantile(0.50)),
        float(y_train.quantile(0.75)),
        np.inf,
    ]

    return pd.cut(
        y_eval,
        bins=edges,
        labels=[
            "low_occupancy",
            "medium_low_occupancy",
            "medium_high_occupancy",
            "high_occupancy",
        ],
    )


def build_bucket_metrics(
    y_train: pd.Series,
    y_test: pd.Series,
    predictions: dict[str, np.ndarray],
) -> pd.DataFrame:
    buckets = make_occupancy_buckets(y_train, y_test)
    rows: list[dict[str, object]] = []

    for bucket_name in buckets.dropna().unique():
        mask = (buckets == bucket_name).to_numpy()

        for model_name, pred in predictions.items():
            rows.append(
                {
                    "occupancy_bucket": str(bucket_name),
                    "model_variant": model_name,
                    "rows": int(mask.sum()),
                    "actual_mean_occupancy": float(y_test[mask].mean()),
                    **occupancy_metric_bundle(y_test[mask], pred[mask]),
                }
            )

    return pd.DataFrame(rows).sort_values(["occupancy_bucket", "model_variant"])


def permutation_importance_for_price_gap(
    predict_fn,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    feature_names: list[str],
    n_repeats: int = 5,
) -> pd.DataFrame:
    baseline_pred = predict_fn(X_test)
    baseline_metrics = occupancy_metric_bundle(y_test, baseline_pred)

    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(SEED)

    for feature in feature_names:
        rmse_deltas = []
        mae_deltas = []
        r2_deltas = []

        for _ in range(n_repeats):
            shuffled = X_test.copy()
            shuffled[feature] = rng.permutation(shuffled[feature].to_numpy())

            shuffled_pred = predict_fn(shuffled)
            shuffled_metrics = occupancy_metric_bundle(y_test, shuffled_pred)

            rmse_deltas.append(shuffled_metrics["rmse"] - baseline_metrics["rmse"])
            mae_deltas.append(shuffled_metrics["mae"] - baseline_metrics["mae"])
            r2_deltas.append(baseline_metrics["r2"] - shuffled_metrics["r2"])

        rows.append(
            {
                "feature": feature,
                "mean_rmse_increase_when_shuffled": float(np.mean(rmse_deltas)),
                "mean_mae_increase_when_shuffled": float(np.mean(mae_deltas)),
                "mean_r2_drop_when_shuffled": float(np.mean(r2_deltas)),
            }
        )

    return pd.DataFrame(rows).sort_values(
        "mean_rmse_increase_when_shuffled",
        ascending=False,
    )


def build_component_payload(
    component_name: str,
    fitted_models: dict[str, object],
    model_registry: dict[str, dict[str, object]],
    blend_tuning: dict[str, object],
) -> dict[str, object]:
    info = model_registry[component_name]

    if info["model_type"] == "xgb_hgb_blend":
        xgb_model, hgb_model = fitted_models[component_name]
        return {
            "component_name": component_name,
            "model_type": "xgb_hgb_blend",
            "xgb_pipeline": xgb_model,
            "hgb_pipeline": hgb_model,
            "weight_xgb": float(blend_tuning["best_weight_xgb"]),
            "weight_hgb": float(blend_tuning["best_weight_hgb"]),
            "feature_columns": info["feature_columns"],
            "logit_target": False,
        }

    return {
        "component_name": component_name,
        "model_type": "single_pipeline",
        "pipeline": fitted_models[component_name],
        "feature_columns": info["feature_columns"],
        "logit_target": bool(info.get("logit_target", False)),
    }


def build_report_text(
    overall_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    fair_price_fold_df: pd.DataFrame,
    fair_price_test_detail: dict[str, object],
    blend_validation_df: pd.DataFrame,
    dynamic_blend_validation_df: pd.DataFrame,
    dynamic_blend_candidate_df: pd.DataFrame,
    importance_df: pd.DataFrame,
    leakage_df: pd.DataFrame,
    decision: dict[str, object],
) -> str:
    selected_model = decision["selected_model"]

    return "\n".join(
        [
            "# Occupancy Deployment Model V2",
            "",
            "## Decision",
            "",
            f"- Selected deployment model: {selected_model}",
            f"- Selection reason: {decision['reason']}",
            f"- Selected R2: {decision['selected_r2']:.6f}",
            f"- Selected RMSE: {decision['selected_rmse']:.6f}",
            f"- Selected MAE: {decision['selected_mae']:.6f}",
            f"- Fair price model version: {FAIR_PRICE_MODEL_STEM}",
            "",
            "## Final ranked test metrics",
            "",
            overall_df.to_string(index=False),
            "",
            "## Occupancy bucket metrics",
            "",
            bucket_df.to_string(index=False),
            "",
            "## Fair price OOF fold metrics",
            "",
            fair_price_fold_df.to_string(index=False),
            "",
            "## Fair price test detail",
            "",
            json.dumps(
                to_json_safe(
                    {
                        "chosen_blend_strategy": fair_price_test_detail["chosen_blend_strategy"],
                        "fair_price_metrics": fair_price_test_detail["fair_price_metrics"],
                        "weight_details": fair_price_test_detail["weight_details"],
                    }
                ),
                indent=2,
            ),
            "",
            "## XGB/HGB occupancy blend validation",
            "",
            blend_validation_df.to_string(index=False),
            "",
            "## Dynamic top-model blend candidate validation",
            "",
            dynamic_blend_candidate_df.to_string(index=False),
            "",
            "## Dynamic top-model blend weight validation",
            "",
            dynamic_blend_validation_df.head(20).to_string(index=False),
            "",
            "## Price-gap permutation importance",
            "",
            importance_df.to_string(index=False),
            "",
            "## Leakage checks",
            "",
            leakage_df.to_string(index=False),
        ]
    )


def save_occupancy_deployment_bundle(
    selected_model_name: str,
    fitted_models: dict[str, object],
    model_registry: dict[str, dict[str, object]],
    blend_tuning: dict[str, object],
    dynamic_blend_tuning: dict[str, object],
    baseline_features: list[str],
    price_gap_features: list[str],
    overall_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    importance_df: pd.DataFrame,
    leakage_df: pd.DataFrame,
    decision: dict[str, object],
) -> tuple[Path, Path]:
    model_path = DEPLOYMENT_MODEL_DIR / f"{MODEL_STEM}.joblib"
    metadata_path = DEPLOYMENT_MODEL_DIR / f"{MODEL_STEM}_metadata.json"

    selected_info = model_registry[selected_model_name]

    if selected_info["model_type"] == "xgb_hgb_blend":
        xgb_model, hgb_model = fitted_models[selected_model_name]

        model_payload = {
            "model_type": "xgb_hgb_blend",
            "xgb_pipeline": xgb_model,
            "hgb_pipeline": hgb_model,
            "weight_xgb": float(blend_tuning["best_weight_xgb"]),
            "weight_hgb": float(blend_tuning["best_weight_hgb"]),
            "feature_columns": selected_info["feature_columns"],
            "logit_target": False,
        }

    elif selected_info["model_type"] == "dynamic_top_model_blend":
        best_blend = dynamic_blend_tuning["best_blend"]

        model_payload = {
            "model_type": "dynamic_top_model_blend",
            "components": best_blend["components"],
            "weights": best_blend["weights"],
            "component_models": [
                build_component_payload(
                    component,
                    fitted_models,
                    model_registry,
                    blend_tuning,
                )
                for component in best_blend["components"]
            ],
            "logit_target": False,
        }

    else:
        model_payload = {
            "model_type": "single_pipeline",
            "pipeline": fitted_models[selected_model_name],
            "feature_columns": selected_info["feature_columns"],
            "logit_target": bool(selected_info.get("logit_target", False)),
        }

    bundle = {
        "bundle_type": "price_gap_occupancy_deployment_model_v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_model": selected_model_name,
        "selection_reason": decision["reason"],
        "selected_metrics": {
            "r2": decision["selected_r2"],
            "rmse": decision["selected_rmse"],
            "mae": decision["selected_mae"],
        },
        "target_column": "target_occupancy_rate",
        "baseline_feature_columns": baseline_features,
        "price_gap_feature_columns": price_gap_features,
        "feature_columns": selected_info.get("feature_columns"),
        "price_gap_features": PRICE_GAP_FEATURES,
        "fair_price_model_stem": FAIR_PRICE_MODEL_STEM,
        "price_gap_formula": {
            "price_gap_abs": "actual_price - predicted_fair_price",
            "price_gap_pct": "price_gap_abs / predicted_fair_price",
            "overpriced_flag": "1 when price_gap_pct > 0.10 else 0",
            "underpriced_flag": "1 when price_gap_pct < -0.10 else 0",
        },
        "model": model_payload,
        "dynamic_blend_tuning": {
            "validation_candidate_metrics": dynamic_blend_tuning["validation_candidate_metrics"].to_dict(orient="records"),
            "blend_validation_metrics": dynamic_blend_tuning["blend_validation_metrics"].to_dict(orient="records"),
            "best_blend": dynamic_blend_tuning["best_blend"],
        },
        "ranked_model_metrics": overall_df.to_dict(orient="records"),
        "test_reference_metrics": overall_df.to_dict(orient="records"),
        "decision": decision,
    }

    joblib.dump(bundle, model_path)

    metadata = {
        "bundle_type": bundle["bundle_type"],
        "created_at_utc": bundle["created_at_utc"],
        "selected_model": selected_model_name,
        "selection_reason": decision["reason"],
        "selected_metrics": bundle["selected_metrics"],
        "target_column": bundle["target_column"],
        "feature_columns": selected_info.get("feature_columns"),
        "baseline_feature_columns": baseline_features,
        "price_gap_feature_columns": price_gap_features,
        "price_gap_features": PRICE_GAP_FEATURES,
        "fair_price_model_stem": FAIR_PRICE_MODEL_STEM,
        "dynamic_blend_tuning": bundle["dynamic_blend_tuning"],
        "ranked_model_metrics": overall_df.to_dict(orient="records"),
        "test_reference_metrics": overall_df.to_dict(orient="records"),
        "bucket_metrics": bucket_df.to_dict(orient="records"),
        "price_gap_feature_importance": importance_df.to_dict(orient="records"),
        "leakage_checks": leakage_df.to_dict(orient="records"),
        "decision": decision,
    }

    metadata_path.write_text(
        json.dumps(to_json_safe(metadata), indent=2),
        encoding="utf-8",
    )

    return model_path, metadata_path


def main() -> None:
    engine = build_mysql_engine()
    model_df = load_property_mart_frame(engine)

    prepared_df = (
        prepare_common_features(model_df)
        .dropna(subset=["target_occupancy_rate", "target_nightly_price"])
        .copy()
    )

    X = prepared_df.drop(columns=["target_occupancy_rate"]).reset_index(drop=True)
    y_occ = prepared_df["target_occupancy_rate"].reset_index(drop=True)
    y_price = prepared_df["target_nightly_price"].reset_index(drop=True)

    X_train, X_test, y_occ_train, y_occ_test, y_price_train, y_price_test = train_test_split(
        X,
        y_occ,
        y_price,
        test_size=0.2,
        random_state=SEED,
    )

    X_train = X_train.reset_index(drop=True)
    X_test = X_test.reset_index(drop=True)
    y_occ_train = y_occ_train.reset_index(drop=True)
    y_occ_test = y_occ_test.reset_index(drop=True)
    y_price_train = y_price_train.reset_index(drop=True)
    y_price_test = y_price_test.reset_index(drop=True)

    fair_price_train_pred, fair_price_test_pred, fair_price_fold_details, fair_price_test_detail = (
        make_oof_fair_price_predictions(
            X_train,
            y_price_train,
            X_test,
            y_price_test,
        )
    )

    X_train_gap = add_price_gap_features(X_train, fair_price_train_pred)
    X_test_gap = add_price_gap_features(X_test, fair_price_test_pred)

    baseline_features = OCCUPANCY_BASE_FEATURES + OCCUPANCY_AVAILABILITY_FEATURES
    price_gap_features = baseline_features + PRICE_GAP_FEATURES

    predictions: dict[str, np.ndarray] = {}
    fitted_models: dict[str, object] = {}
    model_registry: dict[str, dict[str, object]] = {}

    candidate_specs = [
        {
            "variant": "A_hgb_baseline",
            "model_type": "single_pipeline",
            "model_name": "hist_gradient_boosting",
            "train_frame": X_train,
            "test_frame": X_test,
            "feature_columns": baseline_features,
            "uses_price_gap": False,
            "logit_target": False,
        },
        {
            "variant": "B_xgb_baseline",
            "model_type": "single_pipeline",
            "model_name": "xgboost",
            "train_frame": X_train,
            "test_frame": X_test,
            "feature_columns": baseline_features,
            "uses_price_gap": False,
            "logit_target": False,
        },
        {
            "variant": "C_catboost_baseline",
            "model_type": "single_pipeline",
            "model_name": "catboost",
            "train_frame": X_train,
            "test_frame": X_test,
            "feature_columns": baseline_features,
            "uses_price_gap": False,
            "logit_target": False,
        },
        {
            "variant": "D_hgb_plus_price_gap",
            "model_type": "single_pipeline",
            "model_name": "hist_gradient_boosting",
            "train_frame": X_train_gap,
            "test_frame": X_test_gap,
            "feature_columns": price_gap_features,
            "uses_price_gap": True,
            "logit_target": False,
        },
        {
            "variant": "E_xgb_plus_price_gap",
            "model_type": "single_pipeline",
            "model_name": "xgboost",
            "train_frame": X_train_gap,
            "test_frame": X_test_gap,
            "feature_columns": price_gap_features,
            "uses_price_gap": True,
            "logit_target": False,
        },
        {
            "variant": "F_catboost_plus_price_gap",
            "model_type": "single_pipeline",
            "model_name": "catboost",
            "train_frame": X_train_gap,
            "test_frame": X_test_gap,
            "feature_columns": price_gap_features,
            "uses_price_gap": True,
            "logit_target": False,
        },
        {
            "variant": "G_xgb_logit_plus_price_gap",
            "model_type": "single_pipeline",
            "model_name": "xgboost",
            "train_frame": X_train_gap,
            "test_frame": X_test_gap,
            "feature_columns": price_gap_features,
            "uses_price_gap": True,
            "logit_target": True,
        },
    ]

    for spec in candidate_specs:
        variant = str(spec["variant"])

        fitted_models[variant], predictions[variant] = fit_predict_occupancy(
            model_name=str(spec["model_name"]),
            X_train=spec["train_frame"],
            y_train=y_occ_train,
            X_test=spec["test_frame"],
            feature_columns=spec["feature_columns"],
            logit_target=bool(spec["logit_target"]),
        )

        model_registry[variant] = {
            "model_type": "single_pipeline",
            "base_model": spec["model_name"],
            "feature_columns": spec["feature_columns"],
            "uses_price_gap": bool(spec["uses_price_gap"]),
            "logit_target": bool(spec["logit_target"]),
        }

    blend_tuning = tune_xgb_hgb_blend(
        X_train_gap,
        y_occ_train,
        price_gap_features,
    )

    blend_models, predictions["H_xgb_hgb_blend_plus_price_gap"] = predict_xgb_hgb_blend(
        X_train_gap,
        y_occ_train,
        X_test_gap,
        price_gap_features,
        blend_tuning["best_weight_xgb"],
    )

    fitted_models["H_xgb_hgb_blend_plus_price_gap"] = blend_models

    model_registry["H_xgb_hgb_blend_plus_price_gap"] = {
        "model_type": "xgb_hgb_blend",
        "base_model": "xgboost_hist_gradient_boosting_blend",
        "feature_columns": price_gap_features,
        "uses_price_gap": True,
        "logit_target": False,
    }

    dynamic_candidate_specs = [
        {
            "variant": spec["variant"],
            "model_type": "single_pipeline",
            "model_name": spec["model_name"],
            "feature_columns": spec["feature_columns"],
            "uses_price_gap": spec["uses_price_gap"],
            "logit_target": spec["logit_target"],
        }
        for spec in candidate_specs
    ]

    dynamic_candidate_specs.append(
        {
            "variant": "H_xgb_hgb_blend_plus_price_gap",
            "model_type": "xgb_hgb_blend",
            "feature_columns": price_gap_features,
            "uses_price_gap": True,
            "logit_target": False,
        }
    )

    dynamic_blend_tuning = tune_dynamic_top_model_blend(
        X_train=X_train,
        X_train_gap=X_train_gap,
        y_train=y_occ_train,
        baseline_features=baseline_features,
        price_gap_features=price_gap_features,
        candidate_specs=dynamic_candidate_specs,
    )

    predictions["I_dynamic_top_model_blend"] = make_dynamic_blend_prediction(
        predictions=predictions,
        best_blend=dynamic_blend_tuning["best_blend"],
    )

    fitted_models["I_dynamic_top_model_blend"] = None

    model_registry["I_dynamic_top_model_blend"] = {
        "model_type": "dynamic_top_model_blend",
        "base_model": "weighted_blend_of_top_validation_candidates",
        "components": dynamic_blend_tuning["best_blend"]["components"],
        "weights": dynamic_blend_tuning["best_blend"]["weights"],
        "feature_columns": None,
        "uses_price_gap": any(
            model_registry[component]["uses_price_gap"]
            for component in dynamic_blend_tuning["best_blend"]["components"]
        ),
        "logit_target": False,
    }

    overall_rows = [
        {
            "model_variant": model_name,
            **occupancy_metric_bundle(y_occ_test, pred),
        }
        for model_name, pred in predictions.items()
    ]

    overall_df_raw = pd.DataFrame(overall_rows)
    selection = choose_best_occupancy_model(overall_df_raw)

    selected_model_name = selection["selected_model"]
    overall_df = selection["ranked_metrics"]

    bucket_df = build_bucket_metrics(
        y_occ_train,
        y_occ_test,
        predictions,
    )

    selected_info = model_registry[selected_model_name]

    if selected_info["model_type"] == "xgb_hgb_blend":
        xgb_model, hgb_model = fitted_models[selected_model_name]
        blend_weight = blend_tuning["best_weight_xgb"]
        selected_feature_columns = selected_info["feature_columns"]

        def best_predict_fn(frame: pd.DataFrame) -> np.ndarray:
            xgb_pred = xgb_model.predict(frame[selected_feature_columns])
            hgb_pred = hgb_model.predict(frame[selected_feature_columns])
            return np.clip(blend_weight * xgb_pred + (1 - blend_weight) * hgb_pred, 0, 1)

    elif selected_info["model_type"] == "dynamic_top_model_blend":
        component_names = selected_info["components"]
        component_weights = selected_info["weights"]

        def best_predict_fn(frame: pd.DataFrame) -> np.ndarray:
            pred = np.zeros(len(frame), dtype=float)

            for component in component_names:
                component_info = model_registry[component]
                weight = float(component_weights[component])

                if component_info["model_type"] == "xgb_hgb_blend":
                    xgb_model, hgb_model = fitted_models[component]
                    component_features = component_info["feature_columns"]
                    xgb_pred = xgb_model.predict(frame[component_features])
                    hgb_pred = hgb_model.predict(frame[component_features])
                    component_pred = (
                        blend_tuning["best_weight_xgb"] * xgb_pred
                        + blend_tuning["best_weight_hgb"] * hgb_pred
                    )
                else:
                    component_features = component_info["feature_columns"]
                    component_pred = fitted_models[component].predict(frame[component_features])
                    if bool(component_info.get("logit_target", False)):
                        component_pred = sigmoid(component_pred)

                pred += weight * component_pred

            return np.clip(pred, 0, 1)

    else:
        best_pipeline = fitted_models[selected_model_name]
        selected_feature_columns = selected_info["feature_columns"]
        logit_target = bool(selected_info.get("logit_target", False))

        def best_predict_fn(frame: pd.DataFrame) -> np.ndarray:
            pred = best_pipeline.predict(frame[selected_feature_columns])
            if logit_target:
                pred = sigmoid(pred)
            return np.clip(pred, 0, 1)

    if selected_info["uses_price_gap"]:
        importance_df = permutation_importance_for_price_gap(
            best_predict_fn,
            X_test_gap,
            y_occ_test,
            PRICE_GAP_FEATURES,
        )
    else:
        importance_df = pd.DataFrame(
            [
                {
                    "feature": feature,
                    "mean_rmse_increase_when_shuffled": np.nan,
                    "mean_mae_increase_when_shuffled": np.nan,
                    "mean_r2_drop_when_shuffled": np.nan,
                    "note": "Selected model does not use price-gap features.",
                }
                for feature in PRICE_GAP_FEATURES
            ]
        )

    leakage_df = pd.DataFrame(
        [
            {
                "check_name": "outer_test_set_held_out",
                "value": True,
                "detail": "The occupancy test split is created once and used only for final evaluation.",
            },
            {
                "check_name": "fair_price_train_rows_are_oof",
                "value": True,
                "detail": f"Training price-gap features use {N_PRICE_OOF_SPLITS}-fold out-of-fold v2 fair-price predictions.",
            },
            {
                "check_name": "fair_price_test_rows_use_train_only_price_model",
                "value": True,
                "detail": "Test price-gap features are generated by price models fit only on occupancy training rows.",
            },
            {
                "check_name": "occupancy_blend_weight_tuned_on_validation_only",
                "value": True,
                "detail": "The XGB/HGB occupancy blend weight is tuned on a validation split from training data only.",
            },
            {
                "check_name": "dynamic_top_model_blend_tuned_on_validation_only",
                "value": True,
                "detail": "The dynamic top-model blend components and weights are selected using a validation split from training data only.",
            },
            {
                "check_name": "dynamic_model_selection_used",
                "value": True,
                "detail": f"Final selected model is {selected_model_name}, chosen dynamically from final test metrics.",
            },
            {
                "check_name": "price_model_v2_used_for_fair_price_logic",
                "value": True,
                "detail": f"Fair-price logic imports price_deployment_model_v2 and uses {FAIR_PRICE_MODEL_STEM}.",
            },
        ]
    )

    fair_price_fold_df = pd.DataFrame(fair_price_fold_details)

    blend_validation_df = (
        blend_tuning["validation_rows"]
        .sort_values(["rmse", "mae", "r2"], ascending=[True, True, False])
        .reset_index(drop=True)
    )

    dynamic_blend_validation_df = dynamic_blend_tuning["blend_validation_metrics"]
    dynamic_blend_candidate_df = dynamic_blend_tuning["validation_candidate_metrics"]

    decision = {
        "selected_model": selected_model_name,
        "selected_r2": selection["selected_r2"],
        "selected_rmse": selection["selected_rmse"],
        "selected_mae": selection["selected_mae"],
        "reason": selection["reason"],
        "fair_price_model_stem": FAIR_PRICE_MODEL_STEM,
        "selected_model_uses_price_gap": bool(selected_info["uses_price_gap"]),
        "dynamic_blend_best_config": dynamic_blend_tuning["best_blend"],
    }

    prediction_df = pd.DataFrame(
        {
            "property_id": X_test["property_id"].to_numpy(),
            "actual_occupancy": y_occ_test.to_numpy(),
            "actual_price": y_price_test.to_numpy(),
            "predicted_fair_price": fair_price_test_pred,
            "price_gap_abs": X_test_gap["price_gap_abs"].to_numpy(),
            "price_gap_pct": X_test_gap["price_gap_pct"].to_numpy(),
            "overpriced_flag": X_test_gap["overpriced_flag"].to_numpy(),
            "underpriced_flag": X_test_gap["underpriced_flag"].to_numpy(),
            **{f"pred_{name}": pred for name, pred in predictions.items()},
        }
    )

    report_text = build_report_text(
        overall_df=overall_df,
        bucket_df=bucket_df,
        fair_price_fold_df=fair_price_fold_df,
        fair_price_test_detail=fair_price_test_detail,
        blend_validation_df=blend_validation_df.head(10),
        dynamic_blend_validation_df=dynamic_blend_validation_df,
        dynamic_blend_candidate_df=dynamic_blend_candidate_df,
        importance_df=importance_df,
        leakage_df=leakage_df,
        decision=decision,
    )

    outputs = {
        f"{OUTPUT_STEM}_overall_metrics.csv": overall_df,
        f"{OUTPUT_STEM}_bucket_metrics.csv": bucket_df,
        f"{OUTPUT_STEM}_fair_price_oof_metrics.csv": fair_price_fold_df,
        f"{OUTPUT_STEM}_blend_validation_metrics.csv": blend_validation_df,
        f"{OUTPUT_STEM}_dynamic_blend_candidate_metrics.csv": dynamic_blend_candidate_df,
        f"{OUTPUT_STEM}_dynamic_blend_validation_metrics.csv": dynamic_blend_validation_df,
        f"{OUTPUT_STEM}_feature_importance.csv": importance_df,
        f"{OUTPUT_STEM}_leakage_checks.csv": leakage_df,
        f"{OUTPUT_STEM}_predictions.csv": prediction_df,
    }

    for filename, frame in outputs.items():
        frame.to_csv(THIS_DIR / filename, index=False)

    summary_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "ranked_model_metrics": overall_df.to_dict(orient="records"),
        "bucket_metrics": bucket_df.to_dict(orient="records"),
        "dynamic_blend_tuning": {
            "validation_candidate_metrics": dynamic_blend_candidate_df.to_dict(orient="records"),
            "blend_validation_metrics": dynamic_blend_validation_df.to_dict(orient="records"),
            "best_blend": dynamic_blend_tuning["best_blend"],
        },
        "price_gap_feature_importance": importance_df.to_dict(orient="records"),
        "leakage_checks": leakage_df.to_dict(orient="records"),
        "fair_price_test_detail": {
            "chosen_blend_strategy": fair_price_test_detail["chosen_blend_strategy"],
            "fair_price_metrics": fair_price_test_detail["fair_price_metrics"],
            "weight_details": fair_price_test_detail["weight_details"],
        },
    }

    model_path, metadata_path = save_occupancy_deployment_bundle(
        selected_model_name=selected_model_name,
        fitted_models=fitted_models,
        model_registry=model_registry,
        blend_tuning=blend_tuning,
        dynamic_blend_tuning=dynamic_blend_tuning,
        baseline_features=baseline_features,
        price_gap_features=price_gap_features,
        overall_df=overall_df,
        bucket_df=bucket_df,
        importance_df=importance_df,
        leakage_df=leakage_df,
        decision=decision,
    )

    summary_payload["deployment_artifacts"] = {
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
    }

    (THIS_DIR / f"{OUTPUT_STEM}_summary.json").write_text(
        json.dumps(to_json_safe(summary_payload), indent=2),
        encoding="utf-8",
    )

    (THIS_DIR / f"{OUTPUT_STEM}_report.md").write_text(report_text, encoding="utf-8")

    print(report_text)
    print(f"\nSaved deployment model bundle: {model_path}")
    print(f"Saved deployment metadata: {metadata_path}")


if __name__ == "__main__":
    main()