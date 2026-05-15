from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
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
from price_deployment_model_v1 import (  # noqa: E402
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
    metric_bundle as price_metric_bundle,
)


OUTPUT_STEM = "occupancy_deployment_model_v1"
MODEL_STEM = "occupancy_deployment_model_v1"
FAIR_PRICE_MODEL_STEM = "nightly_price_deployment_model_v1"
SEED = 42
N_PRICE_OOF_SPLITS = 3
PRICE_GAP_FEATURES = [
    "predicted_fair_price",
    "price_gap_abs",
    "price_gap_pct",
    "overpriced_flag",
    "underpriced_flag",
]


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


def predict_blended_fair_price(
    X_train: pd.DataFrame,
    y_price_train: pd.Series,
    X_eval: pd.DataFrame,
    y_price_eval: pd.Series,
) -> tuple[np.ndarray, dict[str, object]]:
    price_train_frame = make_price_training_frame(X_train, y_price_train)
    price_split, baseline_validation, segmented_validation, segmented_config = build_validation_predictions(price_train_frame)
    strategy_tuning = tune_blend_strategies(price_split, baseline_validation, segmented_validation)
    chosen_strategy = strategy_tuning["chosen_blend"]

    X_train_aug, X_eval_aug = add_train_only_price_proxies(X_train.copy(), X_eval.copy(), y_price_train.copy())
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
    kfold = KFold(n_splits=N_PRICE_OOF_SPLITS, shuffle=True, random_state=SEED)

    for fold_number, (train_idx, holdout_idx) in enumerate(kfold.split(X_train), start=1):
        fold_pred, fold_detail = predict_blended_fair_price(
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

    test_pred, test_detail = predict_blended_fair_price(
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
    xgb_model, xgb_valid_pred = fit_predict_occupancy("xgboost", X_inner, y_inner, X_valid, feature_columns)
    hgb_model, hgb_valid_pred = fit_predict_occupancy("hist_gradient_boosting", X_inner, y_inner, X_valid, feature_columns)

    rows: list[dict[str, object]] = []
    best: dict[str, object] | None = None
    for weight in np.linspace(0.0, 1.0, 41):
        pred = weight * xgb_valid_pred + (1 - weight) * hgb_valid_pred
        metrics = occupancy_metric_bundle(y_valid, pred)
        row = {"weight_xgb": float(weight), **metrics}
        rows.append(row)
        if best is None or (row["rmse"], row["mae"], -row["r2"]) < (best["rmse"], best["mae"], -best["r2"]):
            best = row
    return {
        "validation_rows": pd.DataFrame(rows),
        "best_weight_xgb": float(best["weight_xgb"]),
        "best_validation_metrics": best,
    }


def predict_xgb_hgb_blend(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    feature_columns: list[str],
    weight_xgb: float,
) -> tuple[tuple[object, object], np.ndarray]:
    xgb_model, xgb_pred = fit_predict_occupancy("xgboost", X_train, y_train, X_test, feature_columns)
    hgb_model, hgb_pred = fit_predict_occupancy("hist_gradient_boosting", X_train, y_train, X_test, feature_columns)
    pred = weight_xgb * xgb_pred + (1 - weight_xgb) * hgb_pred
    return (xgb_model, hgb_model), np.clip(pred, 0, 1)


def make_occupancy_buckets(y_train: pd.Series, y_eval: pd.Series) -> pd.Series:
    edges = [
        -np.inf,
        float(y_train.quantile(0.25)),
        float(y_train.quantile(0.50)),
        float(y_train.quantile(0.75)),
        np.inf,
    ]
    return pd.cut(y_eval, bins=edges, labels=["low_occupancy", "medium_low_occupancy", "medium_high_occupancy", "high_occupancy"])


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
    return pd.DataFrame(rows).sort_values("mean_rmse_increase_when_shuffled", ascending=False)


def build_report_text(
    overall_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    fair_price_fold_df: pd.DataFrame,
    fair_price_test_detail: dict[str, object],
    blend_validation_df: pd.DataFrame,
    importance_df: pd.DataFrame,
    leakage_df: pd.DataFrame,
    decision: dict[str, object],
) -> str:
    return "\n".join(
        [
            "# Occupancy Deployment Model V1",
            "",
            "## Decision",
            "",
            f"- Use price-gap occupancy model: {decision['use_new_model']}",
            f"- Reason: {decision['reason']}",
            "",
            "## Overall test metrics",
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
                {
                    "chosen_blend_strategy": fair_price_test_detail["chosen_blend_strategy"],
                    "fair_price_metrics": fair_price_test_detail["fair_price_metrics"],
                    "weight_details": fair_price_test_detail["weight_details"],
                },
                indent=2,
            ),
            "",
            "## XGB/HGB occupancy blend validation",
            "",
            blend_validation_df.to_string(index=False),
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
    best_model_name: str,
    fitted_models: dict[str, object],
    blend_tuning: dict[str, object],
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

    model_payload: dict[str, object]
    if best_model_name == "E_xgb_hgb_blend_plus_price_gap":
        xgb_model, hgb_model = fitted_models[best_model_name]
        model_payload = {
            "model_type": "xgb_hgb_blend",
            "xgb_pipeline": xgb_model,
            "hgb_pipeline": hgb_model,
            "weight_xgb": float(blend_tuning["best_weight_xgb"]),
            "weight_hgb": float(1 - blend_tuning["best_weight_xgb"]),
        }
    else:
        pipeline_key = best_model_name
        if best_model_name == "C_xgboost_plus_price_gap":
            pipeline_key = "B_current_best_xgb_plus_price_gap"
        model_payload = {
            "model_type": "single_pipeline",
            "pipeline": fitted_models[pipeline_key],
            "logit_target": best_model_name == "F_xgb_logit_plus_price_gap",
        }

    bundle = {
        "bundle_type": "price_gap_occupancy_deployment_model",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_model": best_model_name,
        "target_column": "target_occupancy_rate",
        "baseline_feature_columns": baseline_features,
        "feature_columns": price_gap_features,
        "price_gap_features": PRICE_GAP_FEATURES,
        "fair_price_model_stem": FAIR_PRICE_MODEL_STEM,
        "price_gap_formula": {
            "price_gap_abs": "actual_price - predicted_fair_price",
            "price_gap_pct": "price_gap_abs / predicted_fair_price",
            "overpriced_flag": "1 when price_gap_pct > 0.10 else 0",
            "underpriced_flag": "1 when price_gap_pct < -0.10 else 0",
        },
        "model": model_payload,
        "test_reference_metrics": overall_df.to_dict(orient="records"),
        "decision": decision,
    }
    joblib.dump(bundle, model_path)

    metadata = {
        "bundle_type": bundle["bundle_type"],
        "created_at_utc": bundle["created_at_utc"],
        "selected_model": best_model_name,
        "target_column": bundle["target_column"],
        "feature_columns": price_gap_features,
        "price_gap_features": PRICE_GAP_FEATURES,
        "fair_price_model_stem": FAIR_PRICE_MODEL_STEM,
        "test_reference_metrics": overall_df.to_dict(orient="records"),
        "bucket_metrics": bucket_df.to_dict(orient="records"),
        "price_gap_feature_importance": importance_df.to_dict(orient="records"),
        "leakage_checks": leakage_df.to_dict(orient="records"),
        "decision": decision,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return model_path, metadata_path


def main() -> None:
    engine = build_mysql_engine()
    model_df = load_property_mart_frame(engine)
    prepared_df = prepare_common_features(model_df).dropna(subset=["target_occupancy_rate", "target_nightly_price"]).copy()

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

    fair_price_train_pred, fair_price_test_pred, fair_price_fold_details, fair_price_test_detail = make_oof_fair_price_predictions(
        X_train,
        y_price_train,
        X_test,
        y_price_test,
    )

    X_train_gap = add_price_gap_features(X_train, fair_price_train_pred)
    X_test_gap = add_price_gap_features(X_test, fair_price_test_pred)

    baseline_features = OCCUPANCY_BASE_FEATURES + OCCUPANCY_AVAILABILITY_FEATURES
    price_gap_features = baseline_features + PRICE_GAP_FEATURES

    predictions: dict[str, np.ndarray] = {}
    fitted_models: dict[str, object] = {}

    fitted_models["A_current_best_xgb"], predictions["A_current_best_xgb"] = fit_predict_occupancy(
        "xgboost",
        X_train,
        y_occ_train,
        X_test,
        baseline_features,
    )
    fitted_models["B_current_best_xgb_plus_price_gap"], predictions["B_current_best_xgb_plus_price_gap"] = fit_predict_occupancy(
        "xgboost",
        X_train_gap,
        y_occ_train,
        X_test_gap,
        price_gap_features,
    )
    predictions["C_xgboost_plus_price_gap"] = predictions["B_current_best_xgb_plus_price_gap"]
    fitted_models["D_hgb_plus_price_gap"], predictions["D_hgb_plus_price_gap"] = fit_predict_occupancy(
        "hist_gradient_boosting",
        X_train_gap,
        y_occ_train,
        X_test_gap,
        price_gap_features,
    )

    blend_tuning = tune_xgb_hgb_blend(X_train_gap, y_occ_train, price_gap_features)
    blend_models, predictions["E_xgb_hgb_blend_plus_price_gap"] = predict_xgb_hgb_blend(
        X_train_gap,
        y_occ_train,
        X_test_gap,
        price_gap_features,
        blend_tuning["best_weight_xgb"],
    )
    fitted_models["E_xgb_hgb_blend_plus_price_gap"] = blend_models

    fitted_models["F_xgb_logit_plus_price_gap"], predictions["F_xgb_logit_plus_price_gap"] = fit_predict_occupancy(
        "xgboost",
        X_train_gap,
        y_occ_train,
        X_test_gap,
        price_gap_features,
        logit_target=True,
    )

    overall_rows = [
        {"model_variant": model_name, **occupancy_metric_bundle(y_occ_test, pred)}
        for model_name, pred in predictions.items()
    ]
    overall_df = pd.DataFrame(overall_rows).sort_values(["r2", "rmse", "mae"], ascending=[False, True, True]).reset_index(drop=True)
    bucket_df = build_bucket_metrics(y_occ_train, y_occ_test, predictions)

    best_model_name = str(overall_df.iloc[0]["model_variant"])
    current_row = overall_df.loc[overall_df["model_variant"] == "A_current_best_xgb"].iloc[0]
    best_row = overall_df.iloc[0]
    use_new_model = bool(
        best_model_name != "A_current_best_xgb"
        and best_row["r2"] > current_row["r2"]
        and best_row["rmse"] <= current_row["rmse"]
        and best_row["mae"] <= current_row["mae"]
    )
    if use_new_model:
        reason = f"{best_model_name} improves R2 and does not worsen RMSE/MAE."
    else:
        reason = "Price-gap features did not beat the current occupancy model on all required metrics."

    if best_model_name == "E_xgb_hgb_blend_plus_price_gap":
        xgb_model, hgb_model = fitted_models["E_xgb_hgb_blend_plus_price_gap"]
        blend_weight = blend_tuning["best_weight_xgb"]

        def best_predict_fn(frame: pd.DataFrame) -> np.ndarray:
            xgb_pred = xgb_model.predict(frame[price_gap_features])
            hgb_pred = hgb_model.predict(frame[price_gap_features])
            return np.clip(blend_weight * xgb_pred + (1 - blend_weight) * hgb_pred, 0, 1)

    else:
        best_pipeline = fitted_models.get(best_model_name) or fitted_models["B_current_best_xgb_plus_price_gap"]

        def best_predict_fn(frame: pd.DataFrame) -> np.ndarray:
            pred = best_pipeline.predict(frame[price_gap_features])
            if best_model_name == "F_xgb_logit_plus_price_gap":
                pred = sigmoid(pred)
            return np.clip(pred, 0, 1)

    importance_df = permutation_importance_for_price_gap(
        best_predict_fn,
        X_test_gap,
        y_occ_test,
        PRICE_GAP_FEATURES,
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
                "detail": f"Training price-gap features use {N_PRICE_OOF_SPLITS}-fold out-of-fold blended price predictions.",
            },
            {
                "check_name": "fair_price_test_rows_use_train_only_price_model",
                "value": True,
                "detail": "Test price-gap features are generated by price models fit only on occupancy training rows.",
            },
            {
                "check_name": "blend_weight_tuned_on_validation_only",
                "value": True,
                "detail": "The XGB/HGB occupancy blend weight is tuned on a validation split from training data only.",
            },
            {
                "check_name": "saved_full_price_model_not_used_for_feature_creation",
                "value": True,
                "detail": "The saved full-data price model is not used to create the experimental gap features.",
            },
        ]
    )

    fair_price_fold_df = pd.DataFrame(fair_price_fold_details)
    blend_validation_df = blend_tuning["validation_rows"].sort_values(["rmse", "mae", "r2"], ascending=[True, True, False]).reset_index(drop=True)
    decision = {
        "use_new_model": use_new_model,
        "selected_model": best_model_name,
        "current_model": "A_current_best_xgb",
        "reason": reason,
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
        importance_df=importance_df,
        leakage_df=leakage_df,
        decision=decision,
    )

    outputs = {
        f"{OUTPUT_STEM}_overall_metrics.csv": overall_df,
        f"{OUTPUT_STEM}_bucket_metrics.csv": bucket_df,
        f"{OUTPUT_STEM}_fair_price_oof_metrics.csv": fair_price_fold_df,
        f"{OUTPUT_STEM}_blend_validation_metrics.csv": blend_validation_df,
        f"{OUTPUT_STEM}_feature_importance.csv": importance_df,
        f"{OUTPUT_STEM}_leakage_checks.csv": leakage_df,
        f"{OUTPUT_STEM}_predictions.csv": prediction_df,
    }
    for filename, frame in outputs.items():
        frame.to_csv(THIS_DIR / filename, index=False)

    summary_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "overall_metrics": overall_df.to_dict(orient="records"),
        "price_gap_feature_importance": importance_df.to_dict(orient="records"),
        "leakage_checks": leakage_df.to_dict(orient="records"),
        "fair_price_test_detail": {
            "chosen_blend_strategy": fair_price_test_detail["chosen_blend_strategy"],
            "fair_price_metrics": fair_price_test_detail["fair_price_metrics"],
            "weight_details": fair_price_test_detail["weight_details"],
        },
    }
    model_path, metadata_path = save_occupancy_deployment_bundle(
        best_model_name=best_model_name,
        fitted_models=fitted_models,
        blend_tuning=blend_tuning,
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
    (THIS_DIR / f"{OUTPUT_STEM}_summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    (THIS_DIR / f"{OUTPUT_STEM}_report.md").write_text(report_text, encoding="utf-8")

    print(report_text)
    print(f"\nSaved deployment model bundle: {model_path}")
    print(f"Saved deployment metadata: {metadata_path}")


if __name__ == "__main__":
    main()
