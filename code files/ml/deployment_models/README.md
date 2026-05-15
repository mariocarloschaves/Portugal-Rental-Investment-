# Deployment Models

This folder contains the active deployment-model training/evaluation scripts and their latest reports.

## Active Models

- Nightly price notebook: `price_deployment_model_v1.ipynb`
- Occupancy notebook: `occupancy_deployment_model_v1.ipynb`
- Nightly price backend script: `price_deployment_model_v1.py`
- Occupancy backend script: `occupancy_deployment_model_v1.py`
- Shared price helpers: `price_model_helpers_v1.py`

## Active Artifacts

- Price artifact: `code files/data/gold/modeling/deployment_models/nightly_price_deployment_model_v1.joblib`
- Price metadata: `code files/data/gold/modeling/deployment_models/nightly_price_deployment_model_v1_metadata.json`
- Occupancy artifact: `code files/data/gold/modeling/deployment_models/occupancy_deployment_model_v1.joblib`
- Occupancy metadata: `code files/data/gold/modeling/deployment_models/occupancy_deployment_model_v1_metadata.json`

## Current Scores

- Price deployment model: R2 `0.702068`, RMSE `39.466098`, MAE `26.875403`, MAPE `0.190449`
- Occupancy deployment model: R2 `0.721178`, RMSE `0.083908`, MAE `0.059050`

## Notes

- The price model is the leakage-free blended price model, with the baseline model preserved as fallback inside the bundle.
- The occupancy model uses price-positioning features from leakage-safe fair-price predictions.
- Generated CSV outputs are intentionally not kept here. The necessary deployment evidence lives in the notebooks, reports, registry, metadata, and model artifacts.
- Older tests, notebooks, and previous model artifacts are archived in `code files/ml/previous_models` and `code files/data/gold/modeling/previous_models`.
