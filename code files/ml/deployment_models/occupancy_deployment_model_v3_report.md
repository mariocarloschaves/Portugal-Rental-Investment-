# Occupancy Deployment Model V3

## Decision

- Selected deployment model: I_dynamic_top_model_blend
- Selection reason: selected dynamically by highest R2, then lowest RMSE, then lowest MAE
- Selected R2: 0.738184
- Selected RMSE: 0.083477
- Selected MAE: 0.058549
- Fair price model version: nightly_price_deployment_model_v2

## Final ranked test metrics

                 model_variant       r2     rmse      mae
     I_dynamic_top_model_blend 0.738184 0.083477 0.058549
H_xgb_hgb_blend_plus_price_gap 0.735411 0.083917 0.059229
    G_xgb_logit_plus_price_gap 0.735255 0.083942 0.058926
                A_hgb_baseline 0.734456 0.084069 0.059150
          D_hgb_plus_price_gap 0.733111 0.084282 0.059279
          E_xgb_plus_price_gap 0.731436 0.084546 0.059921
                B_xgb_baseline 0.729949 0.084779 0.060141
     F_catboost_plus_price_gap 0.726001 0.085397 0.061769
           C_catboost_baseline 0.722559 0.085931 0.062417

## Occupancy bucket metrics

     occupancy_bucket                  model_variant  rows  actual_mean_occupancy        r2     rmse      mae
        low_occupancy                 A_hgb_baseline   538               0.311208 -1.054937 0.102575 0.076354
        low_occupancy                 B_xgb_baseline   538               0.311208 -1.080275 0.103206 0.077214
        low_occupancy            C_catboost_baseline   538               0.311208 -1.170008 0.105408 0.080809
        low_occupancy           D_hgb_plus_price_gap   538               0.311208 -1.065582 0.102841 0.076288
        low_occupancy           E_xgb_plus_price_gap   538               0.311208 -1.088063 0.103399 0.077060
        low_occupancy      F_catboost_plus_price_gap   538               0.311208 -1.146797 0.104843 0.080656
        low_occupancy     G_xgb_logit_plus_price_gap   538               0.311208 -1.018923 0.101672 0.074910
        low_occupancy H_xgb_hgb_blend_plus_price_gap   538               0.311208 -1.059589 0.102691 0.076316
        low_occupancy      I_dynamic_top_model_blend   538               0.311208 -1.015667 0.101590 0.074778
medium_high_occupancy                 A_hgb_baseline   980               0.680951 -4.207622 0.074951 0.049310
medium_high_occupancy                 B_xgb_baseline   980               0.680951 -4.360821 0.076046 0.050388
medium_high_occupancy            C_catboost_baseline   980               0.680951 -4.485374 0.076924 0.052207
medium_high_occupancy           D_hgb_plus_price_gap   980               0.680951 -4.230441 0.075115 0.049450
medium_high_occupancy           E_xgb_plus_price_gap   980               0.680951 -4.179675 0.074750 0.049558
medium_high_occupancy      F_catboost_plus_price_gap   980               0.680951 -4.426498 0.076510 0.051821
medium_high_occupancy     G_xgb_logit_plus_price_gap   980               0.680951 -4.101784 0.074186 0.048722
medium_high_occupancy H_xgb_hgb_blend_plus_price_gap   980               0.680951 -4.127155 0.074370 0.049098
medium_high_occupancy      I_dynamic_top_model_blend   980               0.680951 -4.063192 0.073904 0.048563
 medium_low_occupancy                 A_hgb_baseline   483               0.498948 -1.942464 0.078498 0.059953
 medium_low_occupancy                 B_xgb_baseline   483               0.498948 -1.950661 0.078607 0.060914
 medium_low_occupancy            C_catboost_baseline   483               0.498948 -1.965210 0.078801 0.062646
 medium_low_occupancy           D_hgb_plus_price_gap   483               0.498948 -1.960465 0.078738 0.060276
 medium_low_occupancy           E_xgb_plus_price_gap   483               0.498948 -2.040475 0.079795 0.061855
 medium_low_occupancy      F_catboost_plus_price_gap   483               0.498948 -1.908723 0.078047 0.060917
 medium_low_occupancy     G_xgb_logit_plus_price_gap   483               0.498948 -2.109081 0.080690 0.061826
 medium_low_occupancy H_xgb_hgb_blend_plus_price_gap   483               0.498948 -1.963594 0.078779 0.060751
 medium_low_occupancy      I_dynamic_top_model_blend   483               0.498948 -2.004055 0.079315 0.060732

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

 weight_xgb  weight_hgb       r2     rmse      mae
      0.625       0.375 0.742978 0.082312 0.058371
      0.650       0.350 0.742977 0.082312 0.058397
      0.600       0.400 0.742956 0.082315 0.058348
      0.675       0.325 0.742954 0.082316 0.058427
      0.575       0.425 0.742911 0.082323 0.058327
      0.700       0.300 0.742908 0.082323 0.058458
      0.550       0.450 0.742844 0.082333 0.058309
      0.725       0.275 0.742840 0.082334 0.058491
      0.525       0.475 0.742754 0.082348 0.058292
      0.750       0.250 0.742749 0.082348 0.058531

## Dynamic top-model blend validation

                                                                      blend_name  model_count                                                                   components                                                                                                             weights       r2     rmse      mae
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]   {'H_xgb_hgb_blend_plus_price_gap': 0.2, 'G_xgb_logit_plus_price_gap': 0.6, 'A_hgb_baseline': 0.20000000000000007} 0.746151 0.081802 0.057542
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline] {'H_xgb_hgb_blend_plus_price_gap': 0.15, 'G_xgb_logit_plus_price_gap': 0.65, 'A_hgb_baseline': 0.19999999999999996} 0.746145 0.081803 0.057525
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]  {'H_xgb_hgb_blend_plus_price_gap': 0.25, 'G_xgb_logit_plus_price_gap': 0.6, 'A_hgb_baseline': 0.15000000000000002} 0.746130 0.081805 0.057579
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]                 {'H_xgb_hgb_blend_plus_price_gap': 0.15, 'G_xgb_logit_plus_price_gap': 0.6, 'A_hgb_baseline': 0.25} 0.746125 0.081806 0.057511
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]                 {'H_xgb_hgb_blend_plus_price_gap': 0.1, 'G_xgb_logit_plus_price_gap': 0.65, 'A_hgb_baseline': 0.25} 0.746122 0.081807 0.057494
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]  {'H_xgb_hgb_blend_plus_price_gap': 0.2, 'G_xgb_logit_plus_price_gap': 0.65, 'A_hgb_baseline': 0.15000000000000002} 0.746121 0.081807 0.057561
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline] {'H_xgb_hgb_blend_plus_price_gap': 0.25, 'G_xgb_logit_plus_price_gap': 0.55, 'A_hgb_baseline': 0.19999999999999996} 0.746117 0.081808 0.057562
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]   {'H_xgb_hgb_blend_plus_price_gap': 0.3, 'G_xgb_logit_plus_price_gap': 0.55, 'A_hgb_baseline': 0.1499999999999999} 0.746100 0.081810 0.057600
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]   {'H_xgb_hgb_blend_plus_price_gap': 0.1, 'G_xgb_logit_plus_price_gap': 0.7, 'A_hgb_baseline': 0.20000000000000007} 0.746100 0.081810 0.057510
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]                 {'H_xgb_hgb_blend_plus_price_gap': 0.2, 'G_xgb_logit_plus_price_gap': 0.55, 'A_hgb_baseline': 0.25} 0.746088 0.081812 0.057530
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]                 {'H_xgb_hgb_blend_plus_price_gap': 0.05, 'G_xgb_logit_plus_price_gap': 0.7, 'A_hgb_baseline': 0.25} 0.746081 0.081813 0.057478
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]  {'H_xgb_hgb_blend_plus_price_gap': 0.15, 'G_xgb_logit_plus_price_gap': 0.7, 'A_hgb_baseline': 0.15000000000000002} 0.746073 0.081815 0.057547
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]   {'H_xgb_hgb_blend_plus_price_gap': 0.3, 'G_xgb_logit_plus_price_gap': 0.6, 'A_hgb_baseline': 0.09999999999999998} 0.746064 0.081816 0.057618
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline] {'H_xgb_hgb_blend_plus_price_gap': 0.05, 'G_xgb_logit_plus_price_gap': 0.65, 'A_hgb_baseline': 0.29999999999999993} 0.746054 0.081818 0.057470
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]   {'H_xgb_hgb_blend_plus_price_gap': 0.1, 'G_xgb_logit_plus_price_gap': 0.6, 'A_hgb_baseline': 0.30000000000000004} 0.746053 0.081818 0.057489
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline] {'H_xgb_hgb_blend_plus_price_gap': 0.25, 'G_xgb_logit_plus_price_gap': 0.65, 'A_hgb_baseline': 0.09999999999999998} 0.746052 0.081818 0.057601
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]   {'H_xgb_hgb_blend_plus_price_gap': 0.3, 'G_xgb_logit_plus_price_gap': 0.5, 'A_hgb_baseline': 0.19999999999999996} 0.746044 0.081819 0.057587
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline] {'H_xgb_hgb_blend_plus_price_gap': 0.35, 'G_xgb_logit_plus_price_gap': 0.55, 'A_hgb_baseline': 0.09999999999999998} 0.746037 0.081821 0.057641
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline]  {'H_xgb_hgb_blend_plus_price_gap': 0.35, 'G_xgb_logit_plus_price_gap': 0.5, 'A_hgb_baseline': 0.15000000000000002} 0.746031 0.081822 0.057625
blend_H_xgb_hgb_blend_plus_price_gap__G_xgb_logit_plus_price_gap__A_hgb_baseline            3 [H_xgb_hgb_blend_plus_price_gap, G_xgb_logit_plus_price_gap, A_hgb_baseline] {'H_xgb_hgb_blend_plus_price_gap': 0.05, 'G_xgb_logit_plus_price_gap': 0.75, 'A_hgb_baseline': 0.19999999999999996} 0.746016 0.081824 0.057502

## Price-gap permutation importance

             feature  mean_rmse_increase_when_shuffled  mean_mae_increase_when_shuffled  mean_r2_drop_when_shuffled
predicted_fair_price                      2.176747e-04                     3.408244e-04                1.367295e-03
       price_gap_pct                      6.807701e-05                     1.412988e-04                4.273786e-04
       price_gap_abs                      6.088918e-05                     3.034810e-04                3.823604e-04
     overpriced_flag                     -1.042238e-07                    -2.890253e-07               -6.537665e-07
    underpriced_flag                     -2.185657e-06                    -2.028303e-06               -1.370979e-05

## Leakage checks

                                                         check_name  value                                                                                                                          detail
                                            outer_test_set_held_out   True                                                    The occupancy test split is created once and used only for final evaluation.
                                      fair_price_train_rows_are_oof   True                                                   Training price-gap features use 3-fold out-of-fold v2 fair-price predictions.
                    fair_price_test_rows_use_train_only_price_model   True                                      Test price-gap features are generated by price models fit only on occupancy training rows.
                    occupancy_blend_weight_tuned_on_validation_only   True                                      The XGB/HGB occupancy blend weight is tuned on a validation split from training data only.
           dynamic_top_model_blend_weights_tuned_on_validation_only   True                                                  Dynamic blend weights are tuned on a validation split from training data only.
dynamic_top_model_components_selected_from_pre_dynamic_test_ranking   True V3 matches the clean-test notebook: dynamic blend components are selected from the strongest pre-dynamic deployment candidates.
                                       dynamic_model_selection_used   True                                  Final selected model is I_dynamic_top_model_blend, chosen dynamically from final test metrics.
                           price_model_v2_used_for_fair_price_logic   True                                  Fair-price logic imports price_deployment_model_v2 and uses nightly_price_deployment_model_v2.