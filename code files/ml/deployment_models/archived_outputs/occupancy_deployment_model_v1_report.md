# Occupancy Deployment Model V1

## Decision

- Use price-gap occupancy model: True
- Reason: E_xgb_hgb_blend_plus_price_gap improves R2 and does not worsen RMSE/MAE.

## Overall test metrics

                    model_variant       r2     rmse      mae
   E_xgb_hgb_blend_plus_price_gap 0.735411 0.083917 0.059229
       F_xgb_logit_plus_price_gap 0.735255 0.083942 0.058926
             D_hgb_plus_price_gap 0.733111 0.084282 0.059279
B_current_best_xgb_plus_price_gap 0.731436 0.084546 0.059921
         C_xgboost_plus_price_gap 0.731436 0.084546 0.059921
               A_current_best_xgb 0.729949 0.084779 0.060141

## Occupancy bucket metrics

     occupancy_bucket                     model_variant  rows  actual_mean_occupancy        r2     rmse      mae
        low_occupancy                A_current_best_xgb   538               0.311208 -1.080275 0.103206 0.077214
        low_occupancy B_current_best_xgb_plus_price_gap   538               0.311208 -1.088063 0.103399 0.077060
        low_occupancy          C_xgboost_plus_price_gap   538               0.311208 -1.088063 0.103399 0.077060
        low_occupancy              D_hgb_plus_price_gap   538               0.311208 -1.065582 0.102841 0.076288
        low_occupancy    E_xgb_hgb_blend_plus_price_gap   538               0.311208 -1.059589 0.102691 0.076316
        low_occupancy        F_xgb_logit_plus_price_gap   538               0.311208 -1.018923 0.101672 0.074910
medium_high_occupancy                A_current_best_xgb   980               0.680951 -4.360821 0.076046 0.050388
medium_high_occupancy B_current_best_xgb_plus_price_gap   980               0.680951 -4.179675 0.074750 0.049558
medium_high_occupancy          C_xgboost_plus_price_gap   980               0.680951 -4.179675 0.074750 0.049558
medium_high_occupancy              D_hgb_plus_price_gap   980               0.680951 -4.230441 0.075115 0.049450
medium_high_occupancy    E_xgb_hgb_blend_plus_price_gap   980               0.680951 -4.127155 0.074370 0.049098
medium_high_occupancy        F_xgb_logit_plus_price_gap   980               0.680951 -4.101784 0.074186 0.048722
 medium_low_occupancy                A_current_best_xgb   483               0.498948 -1.950661 0.078607 0.060914
 medium_low_occupancy B_current_best_xgb_plus_price_gap   483               0.498948 -2.040475 0.079795 0.061855
 medium_low_occupancy          C_xgboost_plus_price_gap   483               0.498948 -2.040475 0.079795 0.061855
 medium_low_occupancy              D_hgb_plus_price_gap   483               0.498948 -1.960465 0.078738 0.060276
 medium_low_occupancy    E_xgb_hgb_blend_plus_price_gap   483               0.498948 -1.963594 0.078779 0.060751
 medium_low_occupancy        F_xgb_logit_plus_price_gap   483               0.498948 -2.109081 0.080690 0.061826

## Fair price OOF fold metrics

 fold  holdout_rows  fair_price_r2  fair_price_rmse  fair_price_mae                                                                                                                                                                                                                                                                                                chosen_blend_strategy
    1          2668       0.666866        41.688433       28.190388       {'strategy': 'segment_specific_weight', 'weight_scope': 'predicted_segment', 'weight_normal': 0.55, 'weight_luxury': 0.9, 'r2': 0.665905782190163, 'rmse': 41.62514417376786, 'mae': 27.87784210333806, 'mape': 0.19908734517722537, 'residual_mean': -1.5340272926451755, 'residual_std': 41.596867523316945}
    2          2668       0.684714        41.941143       28.267650    {'strategy': 'bucket_specific_weight', 'weight_scope': 'predicted_price_bucket_from_baseline', 'global_fallback_weight': 0.33, 'r2': 0.6564625446755847, 'rmse': 44.16001221885718, 'mae': 28.7588521880961, 'mape': 0.1971373910712778, 'residual_mean': -4.3384480342068255, 'residual_std': 43.94638264776866}
    3          2668       0.654947        42.210433       28.945690 {'strategy': 'bucket_specific_weight', 'weight_scope': 'predicted_price_bucket_from_baseline', 'global_fallback_weight': 0.74, 'r2': 0.6571075541204261, 'rmse': 45.15635648783359, 'mae': 30.562271628914367, 'mape': 0.20984659916133894, 'residual_mean': -3.358538855799658, 'residual_std': 45.031286324181266}

## Fair price test detail

{
  "chosen_blend_strategy": {
    "strategy": "bucket_specific_weight",
    "weight_scope": "predicted_price_bucket_from_baseline",
    "global_fallback_weight": 0.86,
    "r2": 0.6861477252369117,
    "rmse": 41.65840660134132,
    "mae": 28.73810852128084,
    "mape": 0.20007459296319607,
    "residual_mean": -3.8113066105001776,
    "residual_std": 41.48369297065337
  },
  "fair_price_metrics": {
    "r2": 0.7047989216300299,
    "rmse": 39.76767473414737,
    "mae": 26.958381197251715,
    "mape": 0.1954672668276793,
    "residual_mean": 0.9268223384338207,
    "residual_std": 39.75687304245548
  },
  "weight_details": [
    {
      "scope": "predicted_price_bucket_from_baseline",
      "value": "low_price",
      "weight": 0.53
    },
    {
      "scope": "predicted_price_bucket_from_baseline",
      "value": "medium_price",
      "weight": 0.9
    },
    {
      "scope": "predicted_price_bucket_from_baseline",
      "value": "high_price",
      "weight": 1.0
    },
    {
      "scope": "predicted_price_bucket_from_baseline",
      "value": "luxury_extreme_price",
      "weight": 0.86
    }
  ]
}

## XGB/HGB occupancy blend validation

 weight_xgb       r2     rmse      mae
      0.625 0.742978 0.082312 0.058371
      0.650 0.742977 0.082312 0.058397
      0.600 0.742956 0.082315 0.058348
      0.675 0.742954 0.082316 0.058427
      0.575 0.742911 0.082323 0.058327
      0.700 0.742908 0.082323 0.058458
      0.550 0.742844 0.082333 0.058309
      0.725 0.742840 0.082334 0.058491
      0.525 0.742754 0.082348 0.058292
      0.750 0.742749 0.082348 0.058531

## Price-gap permutation importance

             feature  mean_rmse_increase_when_shuffled  mean_mae_increase_when_shuffled  mean_r2_drop_when_shuffled
predicted_fair_price                      2.862498e-04                         0.000451                1.808814e-03
       price_gap_abs                      3.911350e-05                         0.000203                2.467856e-04
       price_gap_pct                      1.341685e-06                         0.000120                8.545860e-06
     overpriced_flag                     -1.085452e-07                         0.000002               -6.842721e-07
    underpriced_flag                     -7.143509e-06                        -0.000005               -4.504407e-05

## Leakage checks

                                          check_name  value                                                                                     detail
                             outer_test_set_held_out   True               The occupancy test split is created once and used only for final evaluation.
                       fair_price_train_rows_are_oof   True              Training price-gap features use 3-fold out-of-fold blended price predictions.
     fair_price_test_rows_use_train_only_price_model   True Test price-gap features are generated by price models fit only on occupancy training rows.
               blend_weight_tuned_on_validation_only   True The XGB/HGB occupancy blend weight is tuned on a validation split from training data only.
saved_full_price_model_not_used_for_feature_creation   True       The saved full-data price model is not used to create the experimental gap features.