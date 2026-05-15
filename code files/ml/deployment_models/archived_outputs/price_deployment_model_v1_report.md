# Price Deployment Model V1

## Decision

- Use blended price deployment model over current baseline: NO
- Chosen validation blend strategy: bucket_specific_weight

## Validation strategy table

               strategy                         weight_scope  global_weight       r2      rmse       mae     mape  residual_mean  residual_std  weight_normal  weight_luxury  global_fallback_weight
 bucket_specific_weight predicted_price_bucket_from_baseline            NaN 0.677298 40.616453 28.119749 0.202027      -0.584994     40.612240            NaN            NaN                    0.74
segment_specific_weight                    predicted_segment            NaN 0.677216 40.621646 28.130083 0.201781      -0.553041     40.617882           0.75           0.25                     NaN
          global_weight                               global           0.74 0.676927 40.639810 28.104448 0.201642      -0.532921     40.636316            NaN            NaN                     NaN
    segmented_reference                                 none            NaN 0.674932 40.765075 28.282331 0.204853       0.679620     40.759409            NaN            NaN                     NaN
     baseline_reference                                 none            NaN 0.661465 41.600903 28.491603 0.198511      -3.983998     41.409695            NaN            NaN                     NaN

## Final test metrics

                        model_variant       r2      rmse       mae     mape  residual_mean  residual_std
baseline_single_hgb_log_observed_full 0.695374 40.397538 27.167904 0.190709      -2.607025     40.313329
            segmented_best_validation 0.694774 40.437288 27.471794 0.200948       1.783650     40.397931
                    blended_candidate 0.700360 40.065582 27.245058 0.197541       0.594159     40.061177

## Promotion rule check

- Baseline R2=0.695374, blended R2=0.700360
- Baseline RMSE=40.397538, blended RMSE=40.065582
- Baseline MAE=27.167904, blended MAE=27.245058

## Segment metrics

segment                         model_variant  train_rows  test_rows  train_mean_price  train_median_price  train_price_std  test_mean_price  test_median_price  test_price_std         r2       rmse        mae     mape  residual_mean  residual_std
 normal baseline_single_hgb_log_observed_full        7802       1951        137.910920               122.0        61.854222       136.615582              120.0       62.031414   0.669729  35.648985  25.083449 0.188579       0.070231     35.648916
 normal             segmented_best_validation        7802       1951        137.910920               122.0        61.854222       136.615582              120.0       62.031414   0.667638  35.761628  25.528220 0.199504       4.439840     35.484952
 normal                     blended_candidate        7802       1951        137.910920               122.0        61.854222       136.615582              120.0       62.031414   0.673822  35.427369  25.276269 0.195938       3.241365     35.278776
 luxury baseline_single_hgb_log_observed_full         202         50        390.158416               392.5        31.743007       391.080000              387.5       33.441794 -13.058621 125.389429 108.503339 0.273839    -107.073574     65.251503
 luxury             segmented_best_validation         202         50        390.158416               392.5        31.743007       391.080000              387.5       33.441794 -12.892948 124.648417 103.310030 0.257306    -101.860885     71.844193
 luxury                     blended_candidate         202         50        390.158416               392.5        31.743007       391.080000              387.5       33.441794 -12.652388 123.564545 104.067212 0.260090    -102.699827     68.709114

## Price bucket metrics

        price_bucket                         model_variant  rows  actual_mean_price  actual_median_price  actual_price_std        r2       rmse       mae     mape  residual_mean  residual_std
           low_price baseline_single_hgb_log_observed_full  1048          92.246183                 94.0         19.067089 -0.594694  24.078152 17.340265 0.197399      10.660358     21.589677
           low_price             segmented_best_validation  1048          92.246183                 94.0         19.067089 -1.083893  27.524668 19.811421 0.224641      14.026976     23.682299
           low_price                     blended_candidate  1048          92.246183                 94.0         19.067089 -0.924585  26.451660 19.168519 0.217988      13.343905     22.839231
        medium_price baseline_single_hgb_log_observed_full   585         154.135043                152.0         19.401927 -2.164493  34.514132 26.649132 0.173073      -1.846572     34.464699
        medium_price             segmented_best_validation   585         154.135043                152.0         19.401927 -2.190922  34.657955 25.765677 0.168741       3.923607     34.435144
        medium_price                     blended_candidate   585         154.135043                152.0         19.401927 -2.078041  34.039413 25.528615 0.166535       2.044198     33.977977
          high_price baseline_single_hgb_log_observed_full   263         236.901141                234.0         30.044038 -2.179794  53.574459 41.885299 0.177385     -23.387215     48.200216
          high_price             segmented_best_validation   263         236.901141                234.0         30.044038 -1.773427  50.034169 39.312191 0.165865     -18.666278     46.421850
          high_price                     blended_candidate   263         236.901141                234.0         30.044038 -1.858725  50.797756 40.082239 0.169409     -20.259557     46.582855
luxury_extreme_price baseline_single_hgb_log_observed_full   105         351.838095                340.0         44.800537 -4.723681 107.181775 91.283824 0.255575     -87.215528     62.300759
luxury_extreme_price             segmented_best_validation   105         351.838095                340.0         44.800537 -4.299910 103.137702 83.777739 0.231785     -81.116830     63.698081
luxury_extreme_price                     blended_candidate   105         351.838095                340.0         44.800537 -4.325671 103.388057 85.265572 0.236677     -82.505653     62.304956

## Leakage checks

                                check_name  value                                                                                                                         detail
 threshold_learned_only_from_training_data   True Threshold quantile 0.975 was selected on validation and the final threshold value 345.0000 was computed from y_train_all only.
       segmenter_fit_only_on_training_data   True                              The luxury router classifier was fit on training rows only, then applied to validation/test rows.
blend_weight_tuned_only_on_validation_data   True                 The chosen blend strategy bucket_specific_weight and its weights were tuned using validation predictions only.
   test_set_used_only_for_final_evaluation   True                                               The test set was held out until the final baseline/segmented/blended comparison.
      baseline_model_preserved_as_fallback   True                         The current HGB log-price baseline is stored inside the blended bundle and remains the fallback model.