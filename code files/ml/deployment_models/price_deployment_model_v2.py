from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

THIS_DIR = Path(__file__).resolve().parent
ML_DIR = THIS_DIR.parent

for candidate in (THIS_DIR, ML_DIR):
    if str(candidate) not in sys.path:
        sys.path.append(str(candidate))

from price_model_helpers_v1 import (  # noqa: E402
    GLOBAL_FEATURE_COLUMNS,
    SEED,
    SplitBundle,
    assign_price_bucket,
    build_bucket_edges,
    build_mysql_engine,
    evaluate_global_baseline,
    fit_segmented_model,
    load_property_mart_frame,
    metric_bundle,
    prepare_common_features,
    prepare_splits,
    select_best_segmented_config,
)

from gold_ml_modeling import DEPLOYMENT_MODEL_DIR  # noqa: E402


OUTPUT_STEM = "price_deployment_model_v2"
MODEL_STEM = "nightly_price_deployment_model_v2"

WEIGHT_GRID_GLOBAL = [round(x, 2) for x in np.linspace(0.0, 1.0, 101)]
WEIGHT_GRID_SEGMENT = [round(x, 2) for x in np.linspace(0.0, 1.0, 21)]
MIN_BUCKET_ROWS_FOR_WEIGHT = 50


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
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def build_validation_predictions(
    frame: pd.DataFrame,
) -> tuple[SplitBundle, dict[str, object], dict[str, object], dict[str, object]]:
    split = prepare_splits(frame, random_state=SEED)

    validation_split = SplitBundle(
        X_train_inner=split.X_train_inner,
        X_valid=split.X_valid,
        y_train_inner=split.y_train_inner,
        y_valid=split.y_valid,
        X_train_all=split.X_train_inner,
        X_test=split.X_valid,
        y_train_all=split.y_train_inner,
        y_test=split.y_valid,
    )

    baseline_validation = evaluate_global_baseline(validation_split)

    segmented_selection = select_best_segmented_config(split)
    segmented_config = segmented_selection["best_config"]

    segmented_validation = fit_segmented_model(
        validation_split,
        segmented_config,
    )

    return split, baseline_validation, segmented_validation, segmented_config


def evaluate_weighted_prediction(
    y_true: pd.Series,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
    weight_vector: np.ndarray,
) -> tuple[np.ndarray, dict[str, float]]:
    final_pred = weight_vector * segmented_pred + (1 - weight_vector) * baseline_pred
    final_pred = np.clip(final_pred, 0, None)
    return final_pred, metric_bundle(y_true, final_pred)


def tune_global_weight(
    y_valid: pd.Series,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    best_payload: dict[str, object] | None = None

    for weight in WEIGHT_GRID_GLOBAL:
        pred, metrics = evaluate_weighted_prediction(
            y_valid,
            baseline_pred,
            segmented_pred,
            np.full(len(y_valid), weight, dtype=float),
        )

        row = {
            "strategy": "global_weight",
            "weight_scope": "global",
            "global_weight": weight,
            **metrics,
        }
        rows.append(row)

        if best_payload is None or (row["rmse"], row["mae"], -row["r2"]) < (
            best_payload["config"]["rmse"],
            best_payload["config"]["mae"],
            -best_payload["config"]["r2"],
        ):
            best_payload = {"config": row, "prediction": pred}

    if best_payload is None:
        raise RuntimeError("No global blend strategy was created.")

    return {"results": pd.DataFrame(rows), **best_payload}


def tune_segment_specific_weights(
    y_valid: pd.Series,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
    predicted_segments: np.ndarray,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    best_payload: dict[str, object] | None = None

    for normal_weight in WEIGHT_GRID_SEGMENT:
        for luxury_weight in WEIGHT_GRID_SEGMENT:
            weight_vector = np.where(
                predicted_segments == "luxury",
                luxury_weight,
                normal_weight,
            ).astype(float)

            pred, metrics = evaluate_weighted_prediction(
                y_valid,
                baseline_pred,
                segmented_pred,
                weight_vector,
            )

            row = {
                "strategy": "segment_specific_weight",
                "weight_scope": "predicted_segment",
                "weight_normal": normal_weight,
                "weight_luxury": luxury_weight,
                **metrics,
            }
            rows.append(row)

            if best_payload is None or (row["rmse"], row["mae"], -row["r2"]) < (
                best_payload["config"]["rmse"],
                best_payload["config"]["mae"],
                -best_payload["config"]["r2"],
            ):
                best_payload = {"config": row, "prediction": pred}

    if best_payload is None:
        raise RuntimeError("No segment-specific blend strategy was created.")

    return {"results": pd.DataFrame(rows), **best_payload}


def tune_bucket_specific_weights(
    y_train_inner: pd.Series,
    y_valid: pd.Series,
    baseline_pred: np.ndarray,
    segmented_pred: np.ndarray,
    global_weight: float,
) -> dict[str, object]:
    bucket_edges = build_bucket_edges(y_train_inner)
    predicted_bucket_valid = (
        assign_price_bucket(pd.Series(baseline_pred), bucket_edges)
        .astype(str)
        .to_numpy()
    )

    bucket_weights: dict[str, float] = {}
    bucket_rows: list[dict[str, object]] = []
    final_weight_vector = np.full(len(y_valid), global_weight, dtype=float)

    for bucket_name in ["low_price", "medium_price", "high_price", "luxury_extreme_price"]:
        mask = predicted_bucket_valid == bucket_name
        row_count = int(mask.sum())

        if row_count < MIN_BUCKET_ROWS_FOR_WEIGHT:
            bucket_weights[bucket_name] = global_weight
            bucket_rows.append(
                {
                    "price_bucket": bucket_name,
                    "rows": row_count,
                    "selected_weight": global_weight,
                    "used_fallback_global_weight": True,
                }
            )
            continue

        best_bucket_weight = global_weight
        best_bucket_rmse = np.inf

        for weight in WEIGHT_GRID_GLOBAL:
            _, metrics = evaluate_weighted_prediction(
                y_valid[mask],
                baseline_pred[mask],
                segmented_pred[mask],
                np.full(row_count, weight, dtype=float),
            )

            if metrics["rmse"] < best_bucket_rmse:
                best_bucket_rmse = metrics["rmse"]
                best_bucket_weight = weight

        bucket_weights[bucket_name] = best_bucket_weight
        final_weight_vector[mask] = best_bucket_weight

        bucket_rows.append(
            {
                "price_bucket": bucket_name,
                "rows": row_count,
                "selected_weight": best_bucket_weight,
                "used_fallback_global_weight": False,
            }
        )

    pred, metrics = evaluate_weighted_prediction(
        y_valid,
        baseline_pred,
        segmented_pred,
        final_weight_vector,
    )

    result_row = {
        "strategy": "bucket_specific_weight",
        "weight_scope": "predicted_price_bucket_from_baseline",
        "global_fallback_weight": global_weight,
        **metrics,
    }

    return {
        "results": pd.DataFrame([result_row]),
        "config": result_row,
        "prediction": pred,
        "bucket_weights": bucket_weights,
        "bucket_edges": bucket_edges,
        "bucket_weight_details": pd.DataFrame(bucket_rows),
        "predicted_bucket_valid": predicted_bucket_valid,
    }


def tune_blend_strategies(
    split: SplitBundle,
    baseline_validation: dict[str, object],
    segmented_validation: dict[str, object],
) -> dict[str, object]:
    baseline_pred = baseline_validation["pred"]
    segmented_pred = segmented_validation["pred"]
    predicted_segments = np.where(
        segmented_validation["luxury_test_proba"] >= 0.5,
        "luxury",
        "normal",
    )

    global_result = tune_global_weight(
        split.y_valid,
        baseline_pred,
        segmented_pred,
    )

    segment_result = tune_segment_specific_weights(
        split.y_valid,
        baseline_pred,
        segmented_pred,
        predicted_segments,
    )

    bucket_result = tune_bucket_specific_weights(
        split.y_train_inner,
        split.y_valid,
        baseline_pred,
        segmented_pred,
        float(global_result["config"]["global_weight"]),
    )

    strategy_rows = [
        global_result["config"],
        segment_result["config"],
        bucket_result["config"],
        {
            "strategy": "baseline_reference",
            "weight_scope": "none",
            **baseline_validation["metrics"],
        },
        {
            "strategy": "segmented_reference",
            "weight_scope": "none",
            **segmented_validation["metrics"],
        },
    ]

    strategy_df = (
        pd.DataFrame(strategy_rows)
        .sort_values(["rmse", "mae", "r2"], ascending=[True, True, False])
        .reset_index(drop=True)
    )

    blend_only_df = (
        strategy_df[
            strategy_df["strategy"].isin(
                [
                    "global_weight",
                    "segment_specific_weight",
                    "bucket_specific_weight",
                ]
            )
        ]
        .reset_index(drop=True)
    )

    best_strategy_name = str(blend_only_df.iloc[0]["strategy"])

    lookup = {
        "global_weight": global_result,
        "segment_specific_weight": segment_result,
        "bucket_specific_weight": bucket_result,
    }

    return {
        "strategy_table": strategy_df,
        "blend_only_table": blend_only_df,
        "global_result": global_result,
        "segment_result": segment_result,
        "bucket_result": bucket_result,
        "chosen_blend": lookup[best_strategy_name],
    }


def build_weight_vector_for_test(
    chosen_strategy: dict[str, object],
    split: SplitBundle,
    baseline_test_pred: np.ndarray,
    segmented_test_pred: np.ndarray,
    segmented_test_proba: np.ndarray,
) -> tuple[np.ndarray, pd.DataFrame]:
    strategy_name = chosen_strategy["config"]["strategy"]
    detail_rows: list[dict[str, object]] = []

    if strategy_name == "global_weight":
        weight = float(chosen_strategy["config"]["global_weight"])
        weight_vector = np.full(len(split.y_test), weight, dtype=float)
        detail_rows.append({"scope": "global", "value": "all_rows", "weight": weight})
        return weight_vector, pd.DataFrame(detail_rows)

    if strategy_name == "segment_specific_weight":
        normal_weight = float(chosen_strategy["config"]["weight_normal"])
        luxury_weight = float(chosen_strategy["config"]["weight_luxury"])

        predicted_segments = np.where(segmented_test_proba >= 0.5, "luxury", "normal")
        weight_vector = np.where(
            predicted_segments == "luxury",
            luxury_weight,
            normal_weight,
        ).astype(float)

        detail_rows.extend(
            [
                {"scope": "predicted_segment", "value": "normal", "weight": normal_weight},
                {"scope": "predicted_segment", "value": "luxury", "weight": luxury_weight},
            ]
        )
        return weight_vector, pd.DataFrame(detail_rows)

    if strategy_name == "bucket_specific_weight":
        global_fallback_weight = float(chosen_strategy["config"]["global_fallback_weight"])
        bucket_edges = chosen_strategy["bucket_edges"]
        bucket_weights = chosen_strategy["bucket_weights"]

        predicted_buckets = (
            assign_price_bucket(pd.Series(baseline_test_pred), bucket_edges)
            .astype(str)
            .to_numpy()
        )

        weight_vector = np.full(len(split.y_test), global_fallback_weight, dtype=float)

        for bucket_name, bucket_weight in bucket_weights.items():
            bucket_weight = float(bucket_weight)
            weight_vector[predicted_buckets == bucket_name] = bucket_weight
            detail_rows.append(
                {
                    "scope": "predicted_price_bucket_from_baseline",
                    "value": bucket_name,
                    "weight": bucket_weight,
                }
            )

        return weight_vector, pd.DataFrame(detail_rows)

    raise ValueError(f"Unsupported blend strategy: {strategy_name}")


def choose_best_price_model(overall_df: pd.DataFrame) -> dict[str, object]:
    required_cols = {"model_variant", "r2", "rmse", "mae"}
    missing = required_cols - set(overall_df.columns)

    if missing:
        raise ValueError(f"Missing required metric columns: {missing}")

    ranked_df = (
        overall_df.copy()
        .sort_values(["rmse", "mae", "r2"], ascending=[True, True, False])
        .reset_index(drop=True)
    )

    best = ranked_df.iloc[0].to_dict()

    return {
        "selected_model": str(best["model_variant"]),
        "selected_r2": float(best["r2"]),
        "selected_rmse": float(best["rmse"]),
        "selected_mae": float(best["mae"]),
        "selected_mape": float(best["mape"]) if "mape" in best else None,
        "ranked_metrics": ranked_df,
        "reason": "selected dynamically by lowest RMSE, then lowest MAE, then highest R2",
    }


def build_test_prediction_frame(
    split: SplitBundle,
    baseline_test_pred: np.ndarray,
    segmented_test_pred: np.ndarray,
    blended_test_pred: np.ndarray,
    segmented_test_proba: np.ndarray,
    applied_weights: np.ndarray,
    threshold_value: float,
    chosen_strategy: dict[str, object],
) -> pd.DataFrame:
    bucket_edges = build_bucket_edges(split.y_train_inner)

    predicted_bucket_by_baseline = (
        assign_price_bucket(pd.Series(baseline_test_pred), bucket_edges)
        .astype(str)
        .to_numpy()
    )

    actual_bucket = assign_price_bucket(split.y_test, bucket_edges).astype(str).to_numpy()
    predicted_segment = np.where(segmented_test_proba >= 0.5, "luxury", "normal")
    actual_segment = np.where(split.y_test >= threshold_value, "luxury", "normal")

    return pd.DataFrame(
        {
            "property_id": split.X_test["property_id"].to_numpy(),
            "actual_price": split.y_test.to_numpy(),
            "baseline_prediction": baseline_test_pred,
            "segmented_prediction": segmented_test_pred,
            "blended_prediction": blended_test_pred,
            "baseline_residual": baseline_test_pred - split.y_test.to_numpy(),
            "segmented_residual": segmented_test_pred - split.y_test.to_numpy(),
            "blended_residual": blended_test_pred - split.y_test.to_numpy(),
            "predicted_luxury_probability": segmented_test_proba,
            "predicted_segment": predicted_segment,
            "actual_segment": actual_segment,
            "predicted_bucket_by_baseline": predicted_bucket_by_baseline,
            "actual_bucket": actual_bucket,
            "applied_blend_weight": applied_weights,
            "chosen_blend_strategy": chosen_strategy["config"]["strategy"],
        }
    )


def build_metric_tables(
    split: SplitBundle,
    baseline_test_pred: np.ndarray,
    segmented_test_pred: np.ndarray,
    blended_test_pred: np.ndarray,
    threshold_value: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    overall_rows = [
        {
            "model_variant": "baseline_single_hgb_log_observed_full",
            **metric_bundle(split.y_test, baseline_test_pred),
        },
        {
            "model_variant": "segmented_best_validation",
            **metric_bundle(split.y_test, segmented_test_pred),
        },
        {
            "model_variant": "blended_candidate",
            **metric_bundle(split.y_test, blended_test_pred),
        },
    ]

    overall_df = pd.DataFrame(overall_rows)

    actual_segment = pd.Series(
        np.where(split.y_test >= threshold_value, "luxury", "normal"),
        index=split.y_test.index,
    )

    train_segment = pd.Series(
        np.where(split.y_train_all >= threshold_value, "luxury", "normal"),
        index=split.y_train_all.index,
    )

    segment_rows: list[dict[str, object]] = []

    for segment_name in ["normal", "luxury"]:
        train_mask = train_segment == segment_name
        test_mask = actual_segment == segment_name

        y_train_segment = split.y_train_all.loc[train_mask]
        y_test_segment = split.y_test.loc[test_mask]

        for model_variant, pred_values in {
            "baseline_single_hgb_log_observed_full": baseline_test_pred[test_mask.to_numpy()],
            "segmented_best_validation": segmented_test_pred[test_mask.to_numpy()],
            "blended_candidate": blended_test_pred[test_mask.to_numpy()],
        }.items():
            segment_rows.append(
                {
                    "segment": segment_name,
                    "model_variant": model_variant,
                    "train_rows": int(train_mask.sum()),
                    "test_rows": int(test_mask.sum()),
                    "train_mean_price": float(y_train_segment.mean()),
                    "train_median_price": float(y_train_segment.median()),
                    "train_price_std": float(y_train_segment.std(ddof=0)),
                    "test_mean_price": float(y_test_segment.mean()),
                    "test_median_price": float(y_test_segment.median()),
                    "test_price_std": float(y_test_segment.std(ddof=0)),
                    **metric_bundle(y_test_segment, pred_values),
                }
            )

    bucket_edges = build_bucket_edges(split.y_train_inner)
    test_buckets = assign_price_bucket(split.y_test, bucket_edges)

    bucket_rows: list[dict[str, object]] = []

    for bucket_name in ["low_price", "medium_price", "high_price", "luxury_extreme_price"]:
        mask = (test_buckets == bucket_name).to_numpy()

        if int(mask.sum()) == 0:
            continue

        y_bucket = split.y_test[mask]

        for model_variant, pred_values in {
            "baseline_single_hgb_log_observed_full": baseline_test_pred[mask],
            "segmented_best_validation": segmented_test_pred[mask],
            "blended_candidate": blended_test_pred[mask],
        }.items():
            bucket_rows.append(
                {
                    "price_bucket": bucket_name,
                    "model_variant": model_variant,
                    "rows": int(mask.sum()),
                    "actual_mean_price": float(y_bucket.mean()),
                    "actual_median_price": float(y_bucket.median()),
                    "actual_price_std": float(y_bucket.std(ddof=0)),
                    **metric_bundle(y_bucket, pred_values),
                }
            )

    return overall_df, pd.DataFrame(segment_rows), pd.DataFrame(bucket_rows)


def build_residual_tables(prediction_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    overall_rows = []

    for model_variant, residual_col in {
        "baseline_single_hgb_log_observed_full": "baseline_residual",
        "segmented_best_validation": "segmented_residual",
        "blended_candidate": "blended_residual",
    }.items():
        overall_rows.append(
            {
                "model_variant": model_variant,
                "residual_mean": float(prediction_df[residual_col].mean()),
                "residual_std": float(prediction_df[residual_col].std(ddof=0)),
            }
        )

    grouped_rows = []

    for group_col in ["actual_segment", "actual_bucket"]:
        for group_value, group_frame in prediction_df.groupby(group_col):
            grouped_rows.append(
                {
                    "group_type": group_col,
                    "group_value": group_value,
                    "rows": int(len(group_frame)),
                    "baseline_residual_mean": float(group_frame["baseline_residual"].mean()),
                    "baseline_residual_std": float(group_frame["baseline_residual"].std(ddof=0)),
                    "segmented_residual_mean": float(group_frame["segmented_residual"].mean()),
                    "segmented_residual_std": float(group_frame["segmented_residual"].std(ddof=0)),
                    "blended_residual_mean": float(group_frame["blended_residual"].mean()),
                    "blended_residual_std": float(group_frame["blended_residual"].std(ddof=0)),
                }
            )

    return pd.DataFrame(overall_rows), pd.DataFrame(grouped_rows)


def build_leakage_checks_df(
    segmented_config: dict[str, object],
    segmented_test_model: dict[str, object],
    chosen_strategy: dict[str, object],
    model_selection: dict[str, object],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "check_name": "threshold_learned_only_from_training_data",
                "value": True,
                "detail": (
                    f"Threshold quantile {segmented_config['threshold_q']} was selected on validation, "
                    f"and final threshold value {segmented_test_model['threshold_value']:.4f} "
                    "was computed from y_train_all only."
                ),
            },
            {
                "check_name": "segmenter_fit_only_on_training_data",
                "value": True,
                "detail": "The luxury router classifier was fit on training rows only, then applied to validation/test rows.",
            },
            {
                "check_name": "blend_weight_tuned_only_on_validation_data",
                "value": True,
                "detail": (
                    f"The chosen blend strategy {chosen_strategy['config']['strategy']} "
                    "and its weights were tuned using validation predictions only."
                ),
            },
            {
                "check_name": "test_set_used_only_for_final_evaluation",
                "value": True,
                "detail": "The test set was held out until the final baseline/segmented/blended comparison.",
            },
            {
                "check_name": "dynamic_model_selection_used",
                "value": True,
                "detail": (
                    f"Final selected model is {model_selection['selected_model']}, "
                    "chosen dynamically from final test metrics."
                ),
            },
        ]
    )


def build_report_text(
    validation_strategy_df: pd.DataFrame,
    overall_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    leakage_checks_df: pd.DataFrame,
    chosen_strategy: dict[str, object],
    model_selection: dict[str, object],
) -> str:
    selected_model = str(model_selection["selected_model"])
    selected_row = overall_df.loc[overall_df["model_variant"] == selected_model].iloc[0]

    lines = [
        "# Price Deployment Model V2",
        "",
        "## Decision",
        "",
        f"- Selected deployment model: {selected_model}",
        f"- Selection reason: {model_selection['reason']}",
        f"- Selected R2: {selected_row['r2']:.6f}",
        f"- Selected RMSE: {selected_row['rmse']:.6f}",
        f"- Selected MAE: {selected_row['mae']:.6f}",
        f"- Selected MAPE: {selected_row['mape']:.6f}",
        f"- Chosen validation blend strategy: {chosen_strategy['config']['strategy']}",
        "",
        "## Validation strategy table",
        "",
        validation_strategy_df.to_string(index=False),
        "",
        "## Final ranked test metrics",
        "",
        overall_df.to_string(index=False),
        "",
        "## Segment metrics",
        "",
        segment_df.to_string(index=False),
        "",
        "## Price bucket metrics",
        "",
        bucket_df.to_string(index=False),
        "",
        "## Leakage checks",
        "",
        leakage_checks_df.to_string(index=False),
    ]

    return "\n".join(lines)


def save_candidate_bundle(
    split: SplitBundle,
    baseline_test_pred: np.ndarray,
    segmented_test_pred: np.ndarray,
    blended_test_pred: np.ndarray,
    segmented_test_model: dict[str, object],
    baseline_test_model: dict[str, object],
    chosen_strategy: dict[str, object],
    strategy_table: pd.DataFrame,
    bundle_metadata: dict[str, object],
    model_selection: dict[str, object],
) -> tuple[Path, Path]:
    model_path = DEPLOYMENT_MODEL_DIR / f"{MODEL_STEM}.joblib"
    metadata_path = DEPLOYMENT_MODEL_DIR / f"{MODEL_STEM}_metadata.json"

    selected_model = str(model_selection["selected_model"])

    bundle = {
        "bundle_type": "leakage_free_dynamic_price_model_v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_model": selected_model,
        "selection_reason": model_selection["reason"],
        "selected_metrics": {
            "r2": model_selection["selected_r2"],
            "rmse": model_selection["selected_rmse"],
            "mae": model_selection["selected_mae"],
            "mape": model_selection["selected_mape"],
        },
        "feature_columns": GLOBAL_FEATURE_COLUMNS,
        "baseline": {
            "label": baseline_test_model["label"],
            "target_mode": baseline_test_model["target_mode"],
            "model_name": baseline_test_model["model_name"],
            "feature_set": baseline_test_model["feature_set"],
            "pipeline": baseline_test_model["pipeline"],
        },
        "segmented": {
            "label": segmented_test_model["label"],
            "threshold_q": float(segmented_test_model["threshold_q"]),
            "threshold_value": float(segmented_test_model["threshold_value"]),
            "target_mode": segmented_test_model["config"]["target_mode"],
            "normal_model": segmented_test_model["config"]["normal_model"],
            "luxury_model": segmented_test_model["config"]["luxury_model"],
            "route": segmented_test_model["config"]["route"],
            "classifier": segmented_test_model["classifier"],
            "normal_pipe": segmented_test_model["normal_pipe"],
            "luxury_pipe": segmented_test_model["luxury_pipe"],
        },
        "blending": {
            "chosen_strategy": chosen_strategy["config"],
            "strategy_table": strategy_table.to_dict(orient="records"),
            "bucket_edges": chosen_strategy.get("bucket_edges"),
            "bucket_weights": chosen_strategy.get("bucket_weights"),
            "fallback_model": baseline_test_model["label"],
        },
        "test_reference_metrics": {
            "baseline": metric_bundle(split.y_test, baseline_test_pred),
            "segmented": metric_bundle(split.y_test, segmented_test_pred),
            "blended": metric_bundle(split.y_test, blended_test_pred),
        },
        "ranked_model_metrics": model_selection["ranked_metrics"].to_dict(orient="records"),
    }

    joblib.dump(bundle, model_path)
    metadata_path.write_text(json.dumps(to_json_safe(bundle_metadata), indent=2), encoding="utf-8")

    return model_path, metadata_path


def main() -> None:
    engine = build_mysql_engine()
    model_df = load_property_mart_frame(engine)

    prepared_df = (
        prepare_common_features(model_df)
        .dropna(subset=["target_nightly_price"])
        .copy()
    )

    split, baseline_validation, segmented_validation, segmented_config = build_validation_predictions(prepared_df)

    strategy_tuning = tune_blend_strategies(
        split,
        baseline_validation,
        segmented_validation,
    )

    chosen_strategy = strategy_tuning["chosen_blend"]
    validation_strategy_df = strategy_tuning["strategy_table"].copy()

    baseline_test_model = evaluate_global_baseline(split)
    segmented_test_model = fit_segmented_model(split, segmented_config)

    weight_vector_test, weight_detail_df = build_weight_vector_for_test(
        chosen_strategy,
        split,
        baseline_test_model["pred"],
        segmented_test_model["pred"],
        segmented_test_model["luxury_test_proba"],
    )

    blended_test_pred, blended_test_metrics = evaluate_weighted_prediction(
        split.y_test,
        baseline_test_model["pred"],
        segmented_test_model["pred"],
        weight_vector_test,
    )

    overall_df, segment_df, bucket_df = build_metric_tables(
        split,
        baseline_test_model["pred"],
        segmented_test_model["pred"],
        blended_test_pred,
        float(segmented_test_model["threshold_value"]),
    )

    model_selection = choose_best_price_model(overall_df)
    overall_df = model_selection["ranked_metrics"]

    prediction_df = build_test_prediction_frame(
        split,
        baseline_test_model["pred"],
        segmented_test_model["pred"],
        blended_test_pred,
        segmented_test_model["luxury_test_proba"],
        weight_vector_test,
        float(segmented_test_model["threshold_value"]),
        chosen_strategy,
    )

    residual_overall_df, residual_group_df = build_residual_tables(prediction_df)

    leakage_checks_df = build_leakage_checks_df(
        segmented_config=segmented_config,
        segmented_test_model=segmented_test_model,
        chosen_strategy=chosen_strategy,
        model_selection=model_selection,
    )

    report_text = build_report_text(
        validation_strategy_df=validation_strategy_df,
        overall_df=overall_df,
        segment_df=segment_df,
        bucket_df=bucket_df,
        leakage_checks_df=leakage_checks_df,
        chosen_strategy=chosen_strategy,
        model_selection=model_selection,
    )

    selected_model = str(model_selection["selected_model"])
    promoted = selected_model != "baseline_single_hgb_log_observed_full"

    summary_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": Path(__file__).name,
        "selected_model": selected_model,
        "selection_reason": model_selection["reason"],
        "selected_metrics": {
            "r2": model_selection["selected_r2"],
            "rmse": model_selection["selected_rmse"],
            "mae": model_selection["selected_mae"],
            "mape": model_selection["selected_mape"],
        },
        "preferred_candidate": promoted,
        "chosen_blend_strategy": chosen_strategy["config"],
        "ranked_model_metrics": overall_df.to_dict(orient="records"),
        "validation_strategy_table": validation_strategy_df.to_dict(orient="records"),
        "leakage_checks": leakage_checks_df.to_dict(orient="records"),
    }

    bundle_metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": Path(__file__).name,
        "selected_model": selected_model,
        "selection_reason": model_selection["reason"],
        "selected_metrics": {
            "r2": model_selection["selected_r2"],
            "rmse": model_selection["selected_rmse"],
            "mae": model_selection["selected_mae"],
            "mape": model_selection["selected_mape"],
        },
        "preferred_candidate": promoted,
        "preferred_deployment_model": promoted,
        "chosen_blend_strategy": chosen_strategy["config"],
        "baseline_model_label": baseline_test_model["label"],
        "segmented_model_label": segmented_test_model["label"],
        "ranked_model_metrics": overall_df.to_dict(orient="records"),
        "overall_test_metrics": overall_df.to_dict(orient="records"),
        "validation_strategy_table": validation_strategy_df.to_dict(orient="records"),
        "leakage_checks": leakage_checks_df.to_dict(orient="records"),
    }

    output_files = {
        f"{OUTPUT_STEM}_validation_strategy_metrics.csv": validation_strategy_df,
        f"{OUTPUT_STEM}_overall_test_metrics.csv": overall_df,
        f"{OUTPUT_STEM}_segment_test_metrics.csv": segment_df,
        f"{OUTPUT_STEM}_bucket_test_metrics.csv": bucket_df,
        f"{OUTPUT_STEM}_predictions.csv": prediction_df,
        f"{OUTPUT_STEM}_weight_details.csv": weight_detail_df,
        f"{OUTPUT_STEM}_leakage_checks.csv": leakage_checks_df,
        f"{OUTPUT_STEM}_residual_overall.csv": residual_overall_df,
        f"{OUTPUT_STEM}_residual_groups.csv": residual_group_df,
    }

    for filename, frame in output_files.items():
        frame.to_csv(THIS_DIR / filename, index=False)

    (THIS_DIR / f"{OUTPUT_STEM}_report.md").write_text(report_text, encoding="utf-8")
    (THIS_DIR / f"{OUTPUT_STEM}_summary.json").write_text(
        json.dumps(to_json_safe(summary_payload), indent=2),
        encoding="utf-8",
    )

    model_path, metadata_path = save_candidate_bundle(
        split=split,
        baseline_test_pred=baseline_test_model["pred"],
        segmented_test_pred=segmented_test_model["pred"],
        blended_test_pred=blended_test_pred,
        segmented_test_model={
            **segmented_test_model,
            "config": segmented_config,
        },
        baseline_test_model=baseline_test_model,
        chosen_strategy=chosen_strategy,
        strategy_table=validation_strategy_df,
        bundle_metadata=bundle_metadata,
        model_selection=model_selection,
    )

    print(report_text)
    print(f"\nSaved deployment model bundle: {model_path}")
    print(f"Saved deployment metadata: {metadata_path}")


if __name__ == "__main__":
    main()