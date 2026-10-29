# Tree-based vs Neural Networks (ROC-AUC)

## Summary

9 of 9 datasets finished [E1] [E2] [E3] [E4] [E5] [E6] [E7] [E8] [E9].

**C1** Tree-based models outperform Neural Networks on medium-sized tabular classification data: **REPLICATED**.
On ROC-AUC, XGBoost and RandomForest (best member of the family on each dataset) scored higher than MLP on 9 of 9 datasets (lower on 0, tied on 0); median difference +0.0243, Holm-adjusted p = 0.00391, rank-biserial r = +1.00 [E10].

## Protocol

Source: Why do tree-based models still outperform deep learning on tabular data?; Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022); https://arxiv.org/abs/2207.08815.

Models and configuration: every model was tuned on each dataset by a random search of 12 configurations (3-fold cross-validated ROC-AUC on a separate tuning set of 20% of the rows that was excluded from evaluation) and also ran once with library defaults as its control. Every other argument is fixed by the protocol.

Procedure: on each dataset every model ran on 10 repeated stratified 80/20 train/test splits (split seeds 42, 100, 200, 300, 400, 500, 600, 700, 800, 900); imputation, scaling and encoding sit in a pipeline fitted on the training part only.

Statistics: each dataset contributes the mean over its splits for every model; datasets are the units of analysis. Models and model families are compared with a two-sided exact Wilcoxon signed-rank test across datasets (at least 6 datasets with a non-zero difference), Holm-adjusted within each family of tests; the Friedman test needs at least three models and 5 datasets. A model family is scored by its best member on each dataset. The effect of tuning is adjusted across the metrics of each model.

Specification: SHA-256 57f90480a21957ca6525d0e2c2e5590592d2c8212519fb4191068abb481dab84, computed before the first dataset started.

Datasets:

- tb_credit: inria-soda/tabular-benchmark (clf_num_credit), 6000 rows (4800 used for evaluation), 10 features, revision 8d0ff91035 [E1]
- tb_california: inria-soda/tabular-benchmark (clf_num_california), 6000 rows (4800 used for evaluation), 8 features, revision 8d0ff91035 [E2]
- tb_electricity: inria-soda/tabular-benchmark (clf_num_electricity), 6000 rows (4800 used for evaluation), 7 features, revision 8d0ff91035 [E3]
- tb_magic: inria-soda/tabular-benchmark (clf_num_MagicTelescope), 6000 rows (4800 used for evaluation), 10 features, revision 8d0ff91035 [E4]
- tb_bank: inria-soda/tabular-benchmark (clf_num_bank-marketing), 6000 rows (4800 used for evaluation), 7 features, revision 8d0ff91035 [E5]
- tb_heloc: inria-soda/tabular-benchmark (clf_num_heloc), 6000 rows (4800 used for evaluation), 22 features, revision 8d0ff91035 [E6]
- tb_house16h: inria-soda/tabular-benchmark (clf_num_house_16H), 6000 rows (4800 used for evaluation), 16 features, revision 8d0ff91035 [E7]
- tb_pol: inria-soda/tabular-benchmark (clf_num_pol), 6000 rows (4800 used for evaluation), 26 features, revision 8d0ff91035 [E8]
- tb_eye: inria-soda/tabular-benchmark (clf_num_eye_movements), 6000 rows (4800 used for evaluation), 20 features, revision 8d0ff91035 [E9]

Selected configurations (best cross-validated ROC-AUC on the tuning set):

- tb_credit: XGBoost (n_estimators=200, max_depth=3, learning_rate=0.03); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=5); MLP (learning_rate_init=0.003, hidden_layer_sizes=[50], alpha=0.01) [E1]
- tb_california: XGBoost (n_estimators=400, max_depth=3, learning_rate=0.03); RandomForest (n_estimators=100, min_samples_leaf=2, max_depth=20); MLP (learning_rate_init=0.003, hidden_layer_sizes=[50], alpha=0.01) [E2]
- tb_electricity: XGBoost (n_estimators=200, max_depth=3, learning_rate=0.03); RandomForest (n_estimators=400, min_samples_leaf=5, max_depth=20); MLP (learning_rate_init=0.003, hidden_layer_sizes=[50], alpha=0.01) [E3]
- tb_magic: XGBoost (n_estimators=400, max_depth=6, learning_rate=0.03); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=None); MLP (learning_rate_init=0.003, hidden_layer_sizes=[100], alpha=0.01) [E4]
- tb_bank: XGBoost (n_estimators=400, max_depth=3, learning_rate=0.03); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=5); MLP (learning_rate_init=0.003, hidden_layer_sizes=[50], alpha=0.01) [E5]
- tb_heloc: XGBoost (n_estimators=200, max_depth=3, learning_rate=0.03); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=10); MLP (learning_rate_init=0.003, hidden_layer_sizes=[200], alpha=1e-05) [E6]
- tb_house16h: XGBoost (n_estimators=400, max_depth=6, learning_rate=0.03); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=None); MLP (learning_rate_init=0.001, hidden_layer_sizes=[100, 50], alpha=0.001) [E7]
- tb_pol: XGBoost (n_estimators=200, max_depth=6, learning_rate=0.1); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=20); MLP (learning_rate_init=0.001, hidden_layer_sizes=[100, 50], alpha=0.001) [E8]
- tb_eye: XGBoost (n_estimators=400, max_depth=6, learning_rate=0.1); RandomForest (n_estimators=400, min_samples_leaf=1, max_depth=5); MLP (learning_rate_init=0.01, hidden_layer_sizes=[50], alpha=0.001) [E9]

Environment: Python 3.13.16; datasets 5.1.0, numpy 2.3.5, pandas 2.2.3, scikit-learn 1.6.1, scipy 1.17.1, xgboost 3.4.1 (identical on every dataset).

Deviations from the source:

- Each model was tuned on every dataset with a random search of 12 configurations from a small fixed grid (3-fold cross-validated ROC-AUC on a separate 20% tuning set), a much smaller search than a full study would run; the remaining rows were used for evaluation.
- Each dataset was evaluated with 80/20 stratified splits repeated over ten seeds instead of the evaluation protocol of the original study.
- Benchmark datasets were reduced to a fixed 6000-row balanced sample, and only the numeric-feature classification datasets of the benchmark available on Hugging Face were used.

## Results

Mean ROC-AUC per dataset (best in bold):

| Dataset | XGBoost | RandomForest | MLP |
|---|---|---|---|
| tb_credit [E1] | **0.8534** | 0.8503 | 0.8291 |
| tb_california [E2] | **0.9585** | 0.9538 | 0.9446 |
| tb_electricity [E3] | 0.8856 | **0.8938** | 0.8605 |
| tb_magic [E4] | **0.9203** | 0.9194 | 0.9184 |
| tb_bank [E5] | **0.8709** | 0.8566 | 0.8549 |
| tb_heloc [E6] | **0.7997** | 0.7959 | 0.7377 |
| tb_house16h [E7] | **0.9503** | 0.9460 | 0.9173 |
| tb_pol [E8] | **0.9985** | 0.9979 | 0.9982 |
| tb_eye [E9] | **0.6861** | 0.6437 | 0.5881 |

Mean PR-AUC per dataset (best in bold):

| Dataset | XGBoost | RandomForest | MLP |
|---|---|---|---|
| tb_credit [E1] | 0.8509 | **0.8509** | 0.8326 |
| tb_california [E2] | **0.9609** | 0.9573 | 0.9462 |
| tb_electricity [E3] | 0.8875 | **0.8949** | 0.8680 |
| tb_magic [E4] | **0.9324** | 0.9303 | 0.9307 |
| tb_bank [E5] | **0.8597** | 0.8414 | 0.8418 |
| tb_heloc [E6] | **0.8049** | 0.8015 | 0.7303 |
| tb_house16h [E7] | **0.9508** | 0.9421 | 0.9113 |
| tb_pol [E8] | **0.9987** | 0.9981 | 0.9983 |
| tb_eye [E9] | **0.6697** | 0.6330 | 0.5729 |

Mean F1 per dataset (best in bold):

| Dataset | XGBoost | RandomForest | MLP |
|---|---|---|---|
| tb_credit [E1] | **0.7697** | 0.7695 | 0.7414 |
| tb_california [E2] | **0.8886** | 0.8782 | 0.8721 |
| tb_electricity [E3] | 0.8093 | **0.8183** | 0.7766 |
| tb_magic [E4] | 0.8450 | **0.8479** | 0.8388 |
| tb_bank [E5] | **0.7962** | 0.7839 | 0.7885 |
| tb_heloc [E6] | **0.7221** | 0.7216 | 0.6897 |
| tb_house16h [E7] | 0.8819 | **0.8874** | 0.8478 |
| tb_pol [E8] | **0.9831** | 0.9802 | 0.9799 |
| tb_eye [E9] | **0.6313** | 0.5895 | 0.5529 |

ROC-AUC mean ranks across 9 datasets (1 = best): XGBoost 1.11, RandomForest 2.00, MLP 2.89; Friedman chi-square = 14.22, p = 0.000816 [E11].

PR-AUC mean ranks across 9 datasets (1 = best): XGBoost 1.22, RandomForest 2.11, MLP 2.67; Friedman chi-square = 9.56, p = 0.00841 [E12].

F1 mean ranks across 9 datasets (1 = best): XGBoost 1.33, RandomForest 1.78, MLP 2.89; Friedman chi-square = 11.56, p = 0.0031 [E13].

Pairwise comparisons that were significant after Holm adjustment:

XGBoost scored higher than MLP on ROC-AUC on 9 of 9 datasets (median difference 0.0243, adjusted p = 0.0117) [E15].
RandomForest scored higher than MLP on ROC-AUC on 8 of 9 datasets (median difference 0.0212, adjusted p = 0.0156) [E16].
XGBoost scored higher than MLP on PR-AUC on 9 of 9 datasets (median difference 0.0182, adjusted p = 0.0117) [E18].
XGBoost scored higher than MLP on F1 on 9 of 9 datasets (median difference 0.0282, adjusted p = 0.0117) [E21].
RandomForest scored higher than MLP on F1 on 8 of 9 datasets (median difference 0.0281, adjusted p = 0.0234) [E22].

No significant effect of tuning of XGBoost on ROC-AUC across datasets was found [E23].
No significant effect of tuning of XGBoost on PR-AUC across datasets was found [E24].
No significant effect of tuning of XGBoost on F1 across datasets was found [E25].
No significant effect of tuning of RandomForest on ROC-AUC across datasets was found [E26].
No significant effect of tuning of RandomForest on PR-AUC across datasets was found [E27].
No significant effect of tuning of RandomForest on F1 across datasets was found [E28].
MLP tuned by random search scored lower than MLP with default parameters on ROC-AUC on 9 of 9 datasets (median difference 0.0022, adjusted p = 0.0117) [E29].
MLP tuned by random search scored lower than MLP with default parameters on PR-AUC on 9 of 9 datasets (median difference 0.0018, adjusted p = 0.0117) [E30].
MLP tuned by random search scored lower than MLP with default parameters on F1 on 9 of 9 datasets (median difference 0.0038, adjusted p = 0.0117) [E31].

Exploratory moderator analysis (Spearman correlation between the per-dataset advantage of a claim and dataset descriptors, exploratory because the number of datasets is small):

No dataset descriptor was significantly related to the size of the advantage after Holm adjustment.

## Comparison with the source

Source of the claims: Why do tree-based models still outperform deep learning on tabular data? (Grinsztajn, Oyallon and Varoquaux, arXiv:2207.08815 (2022)).

- **C1** The source states: “Results show that tree-based models remain state-of-the-art on medium-sized data ($\sim$10K samples) even without accounting for their superior speed”. The campaign result agrees with the source [E10].

## Limitations

- Every conclusion concerns the datasets listed above; with a handful of datasets the tests have little power and a non-significant result is not evidence of equivalence.
- Within a dataset the repeated splits overlap, so they are summarised by their mean and never used as independent samples across datasets.
- Tuning used a small random search over fixed discrete grids with one tuning set per dataset; a larger search could change the ranking.
- Datasets larger than the sampling limit were sampled with a fixed seed, which changes their size but not the class balance of the benchmark.
- Significant tuning effects within their model: 3; of these, 3 remain significant when the adjustment spans all models and metrics.

## Evidence ledger

| Id | Kind | Key | Detail |
|---|---|---|---|
| E1 | dataset | tb_credit | inria-soda/tabular-benchmark (clf_num_credit), script sha256 5dc6628aa911 |
| E2 | dataset | tb_california | inria-soda/tabular-benchmark (clf_num_california), script sha256 f5c5aafe10b3 |
| E3 | dataset | tb_electricity | inria-soda/tabular-benchmark (clf_num_electricity), script sha256 4ebb6b860f3a |
| E4 | dataset | tb_magic | inria-soda/tabular-benchmark (clf_num_MagicTelescope), script sha256 4acfabfbe7ad |
| E5 | dataset | tb_bank | inria-soda/tabular-benchmark (clf_num_bank-marketing), script sha256 bea95b18e29c |
| E6 | dataset | tb_heloc | inria-soda/tabular-benchmark (clf_num_heloc), script sha256 bc7f1d211015 |
| E7 | dataset | tb_house16h | inria-soda/tabular-benchmark (clf_num_house_16H), script sha256 5bcf47801dda |
| E8 | dataset | tb_pol | inria-soda/tabular-benchmark (clf_num_pol), script sha256 25061d0ea4a3 |
| E9 | dataset | tb_eye | inria-soda/tabular-benchmark (clf_num_eye_movements), script sha256 06923c7fbd56 |
| E10 | claim | C1:roc_auc | replicated, 9/9 wins |
| E11 | friedman | roc_auc | mean ranks over 9 datasets |
| E12 | friedman | pr_auc | mean ranks over 9 datasets |
| E13 | friedman | f1 | mean ranks over 9 datasets |
| E14 | pairwise | roc_auc:XGBoost:RandomForest | 8 wins, 1 losses, 0 ties |
| E15 | pairwise | roc_auc:XGBoost:MLP | 9 wins, 0 losses, 0 ties |
| E16 | pairwise | roc_auc:RandomForest:MLP | 8 wins, 1 losses, 0 ties |
| E17 | pairwise | pr_auc:XGBoost:RandomForest | 7 wins, 2 losses, 0 ties |
| E18 | pairwise | pr_auc:XGBoost:MLP | 9 wins, 0 losses, 0 ties |
| E19 | pairwise | pr_auc:RandomForest:MLP | 6 wins, 3 losses, 0 ties |
| E20 | pairwise | f1:XGBoost:RandomForest | 6 wins, 3 losses, 0 ties |
| E21 | pairwise | f1:XGBoost:MLP | 9 wins, 0 losses, 0 ties |
| E22 | pairwise | f1:RandomForest:MLP | 8 wins, 1 losses, 0 ties |
| E23 | effect | XGBoost:roc_auc | 6 wins, 3 losses, 0 ties |
| E24 | effect | XGBoost:pr_auc | 7 wins, 2 losses, 0 ties |
| E25 | effect | XGBoost:f1 | 7 wins, 2 losses, 0 ties |
| E26 | effect | RandomForest:roc_auc | 4 wins, 4 losses, 1 ties |
| E27 | effect | RandomForest:pr_auc | 6 wins, 3 losses, 0 ties |
| E28 | effect | RandomForest:f1 | 4 wins, 5 losses, 0 ties |
| E29 | effect | MLP:roc_auc | 0 wins, 9 losses, 0 ties |
| E30 | effect | MLP:pr_auc | 0 wins, 9 losses, 0 ties |
| E31 | effect | MLP:f1 | 0 wins, 9 losses, 0 ties |
| E32 | moderator | C1:roc_auc:features | features, rho +0.07, n 9 |
| E33 | moderator | C1:roc_auc:minority_ratio | minority_ratio, rho +0.35, n 9 |
| E34 | moderator | C1:roc_auc:categorical_share | categorical_share, rho +0.00, n 9 |
| E35 | moderator | C1:roc_auc:mean_abs_correlation | mean_abs_correlation, rho +0.27, n 9 |
| E36 | moderator | C1:roc_auc:mean_abs_skew | mean_abs_skew, rho -0.08, n 9 |
| E37 | moderator | C1:roc_auc:missing_share | missing_share, rho +0.00, n 9 |
