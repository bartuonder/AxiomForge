# Do tree-based models still outperform neural networks on medium-sized tabular data?

## Summary

9 of 9 datasets finished [E1] [E2] [E3] [E4] [E5] [E6] [E7] [E8] [E9].

**C1** Tree-based models outperform a neural network (MLP) on tabular classification data: **REPLICATED**.
On ROC-AUC, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than MLP on 9 of 9 datasets (lower on 0, tied on 0); median difference +0.0134, Holm-adjusted p = 0.0117, rank-biserial r = +1.00 [E10].
On PR-AUC, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than MLP on 8 of 9 datasets (lower on 1, tied on 0); median difference +0.0172, Holm-adjusted p = 0.0117, rank-biserial r = +0.96 [E11].
On F1, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than MLP on 9 of 9 datasets (lower on 0, tied on 0); median difference +0.0246, Holm-adjusted p = 0.0117, rank-biserial r = +1.00 [E12].

**C2** Tree-based models outperform linear models on tabular classification data: **REPLICATED**.
On ROC-AUC, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than LogisticRegression on 9 of 9 datasets (lower on 0, tied on 0); median difference +0.0575, Holm-adjusted p = 0.0117, rank-biserial r = +1.00 [E13].
On PR-AUC, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than LogisticRegression on 9 of 9 datasets (lower on 0, tied on 0); median difference +0.0490, Holm-adjusted p = 0.0117, rank-biserial r = +1.00 [E14].
On F1, RandomForest and HistGradientBoosting (best member of the family on each dataset) scored higher than LogisticRegression on 9 of 9 datasets (lower on 0, tied on 0); median difference +0.0724, Holm-adjusted p = 0.0117, rank-biserial r = +1.00 [E15].

## Protocol

Source: Why do tree-based models still outperform deep learning on tabular data?; Grinsztajn, Oyallon and Varoquaux, NeurIPS 2022 (Datasets and Benchmarks); https://arxiv.org/abs/2207.08815.

Models and configuration: RandomForest, HistGradientBoosting, MLP and LogisticRegression ran with library default parameters. Every other argument is fixed by the protocol, and a configured model also runs once with library defaults as its control.

Procedure: on each dataset every model ran on 10 repeated stratified 80/20 train/test splits (split seeds 42, 100, 200, 300, 400, 500, 600, 700, 800, 900); imputation, scaling and encoding sit in a pipeline fitted on the training part only.

Statistics: each dataset contributes the mean over its splits for every model; datasets are the units of analysis. Models and model families are compared with a two-sided exact Wilcoxon signed-rank test across datasets (at least 6 datasets with a non-zero difference), Holm-adjusted within each family of tests; the Friedman test needs at least three models and 5 datasets. A model family is scored by its best member on each dataset.

Datasets:

- tb_credit: inria-soda/tabular-benchmark (clf_num_credit), 6000 rows, 10 features [E1]
- tb_california: inria-soda/tabular-benchmark (clf_num_california), 6000 rows, 8 features [E2]
- tb_electricity: inria-soda/tabular-benchmark (clf_num_electricity), 6000 rows, 7 features [E3]
- tb_magic: inria-soda/tabular-benchmark (clf_num_MagicTelescope), 6000 rows, 10 features [E4]
- tb_bank: inria-soda/tabular-benchmark (clf_num_bank-marketing), 6000 rows, 7 features [E5]
- tb_heloc: inria-soda/tabular-benchmark (clf_num_heloc), 6000 rows, 22 features [E6]
- tb_house16h: inria-soda/tabular-benchmark (clf_num_house_16H), 6000 rows, 16 features [E7]
- tb_pol: inria-soda/tabular-benchmark (clf_num_pol), 6000 rows, 26 features [E8]
- tb_eye: inria-soda/tabular-benchmark (clf_num_eye_movements), 6000 rows, 20 features [E9]

Deviations from the source:

- No hyperparameter search: every model ran with library default parameters, whereas the paper tuned each model with random search.
- Each dataset was reduced to a fixed 6000-row balanced sample and evaluated with 80/20 stratified splits repeated over ten seeds.
- The neural network is scikit-learn's MLPClassifier, not the ResNet or FT-Transformer of the paper.
- Only the nine numeric-feature classification datasets of the benchmark available on Hugging Face were used.
- Tree-based models are RandomForest and HistGradientBoosting; the paper also included XGBoost and gradient boosted trees from other libraries.

## Results

Mean ROC-AUC per dataset (best in bold):

| Dataset | RandomForest | HistGradientBoosting | MLP | LogisticRegression |
|---|---|---|---|---|
| tb_credit [E1] | 0.8416 | **0.8417** | 0.8346 | 0.8049 |
| tb_california [E2] | 0.9514 | **0.9596** | 0.9429 | 0.9156 |
| tb_electricity [E3] | 0.9012 | **0.9084** | 0.8593 | 0.8157 |
| tb_magic [E4] | **0.9231** | 0.9230 | 0.9207 | 0.8402 |
| tb_bank [E5] | 0.8635 | **0.8723** | 0.8588 | 0.8232 |
| tb_heloc [E6] | **0.7928** | 0.7923 | 0.7653 | 0.7843 |
| tb_house16h [E7] | 0.9451 | **0.9492** | 0.9374 | 0.8917 |
| tb_pol [E8] | 0.9983 | **0.9986** | 0.9985 | 0.9390 |
| tb_eye [E9] | 0.6820 | **0.6919** | 0.6035 | 0.5780 |

Mean PR-AUC per dataset (best in bold):

| Dataset | RandomForest | HistGradientBoosting | MLP | LogisticRegression |
|---|---|---|---|---|
| tb_credit [E1] | 0.8344 | **0.8397** | 0.8394 | 0.8215 |
| tb_california [E2] | 0.9537 | **0.9624** | 0.9456 | 0.9186 |
| tb_electricity [E3] | 0.8971 | **0.9091** | 0.8649 | 0.8312 |
| tb_magic [E4] | 0.9330 | **0.9353** | 0.9331 | 0.8592 |
| tb_bank [E5] | 0.8406 | **0.8592** | 0.8375 | 0.8130 |
| tb_heloc [E6] | 0.7963 | **0.7970** | 0.7635 | 0.7765 |
| tb_house16h [E7] | 0.9424 | **0.9503** | 0.9332 | 0.8657 |
| tb_pol [E8] | 0.9983 | 0.9986 | **0.9986** | 0.9496 |
| tb_eye [E9] | 0.6611 | **0.6775** | 0.5965 | 0.5645 |

Mean F1 per dataset (best in bold):

| Dataset | RandomForest | HistGradientBoosting | MLP | LogisticRegression |
|---|---|---|---|---|
| tb_credit [E1] | **0.7692** | 0.7618 | 0.7446 | 0.7019 |
| tb_california [E2] | 0.8763 | **0.8921** | 0.8665 | 0.8363 |
| tb_electricity [E3] | 0.8206 | **0.8259** | 0.7791 | 0.7231 |
| tb_magic [E4] | 0.8449 | **0.8476** | 0.8365 | 0.7573 |
| tb_bank [E5] | 0.7944 | **0.8001** | 0.7898 | 0.7276 |
| tb_heloc [E6] | **0.7232** | 0.7220 | 0.6924 | 0.7090 |
| tb_house16h [E7] | 0.8804 | **0.8833** | 0.8727 | 0.8314 |
| tb_pol [E8] | 0.9797 | **0.9844** | 0.9830 | 0.8634 |
| tb_eye [E9] | 0.6160 | **0.6311** | 0.5719 | 0.5544 |

ROC-AUC mean ranks across 9 datasets (1 = best): HistGradientBoosting 1.22, RandomForest 1.89, MLP 3.00, LogisticRegression 3.89; Friedman chi-square = 22.60, p = 4.89e-05 [E16].

PR-AUC mean ranks across 9 datasets (1 = best): HistGradientBoosting 1.11, RandomForest 2.33, MLP 2.67, LogisticRegression 3.89; Friedman chi-square = 21.13, p = 9.88e-05 [E17].

F1 mean ranks across 9 datasets (1 = best): HistGradientBoosting 1.22, RandomForest 1.89, MLP 3.00, LogisticRegression 3.89; Friedman chi-square = 22.60, p = 4.89e-05 [E18].

Pairwise comparisons that were significant after Holm adjustment:

RandomForest scored higher than MLP on ROC-AUC on 8 of 9 datasets (median difference 0.0077, adjusted p = 0.0234) [E20].
RandomForest scored higher than LogisticRegression on ROC-AUC on 9 of 9 datasets (median difference 0.0534, adjusted p = 0.0234) [E21].
HistGradientBoosting scored higher than MLP on ROC-AUC on 9 of 9 datasets (median difference 0.0134, adjusted p = 0.0234) [E22].
HistGradientBoosting scored higher than LogisticRegression on ROC-AUC on 9 of 9 datasets (median difference 0.0575, adjusted p = 0.0234) [E23].
MLP scored higher than LogisticRegression on ROC-AUC on 8 of 9 datasets (median difference 0.0356, adjusted p = 0.0234) [E24].
HistGradientBoosting scored higher than RandomForest on PR-AUC on 9 of 9 datasets (median difference 0.0079, adjusted p = 0.0234) [E25].
RandomForest scored higher than LogisticRegression on PR-AUC on 9 of 9 datasets (median difference 0.0487, adjusted p = 0.0234) [E27].
HistGradientBoosting scored higher than MLP on PR-AUC on 8 of 9 datasets (median difference 0.0172, adjusted p = 0.0234) [E28].
HistGradientBoosting scored higher than LogisticRegression on PR-AUC on 9 of 9 datasets (median difference 0.0490, adjusted p = 0.0234) [E29].
MLP scored higher than LogisticRegression on PR-AUC on 8 of 9 datasets (median difference 0.0320, adjusted p = 0.0234) [E30].
RandomForest scored higher than MLP on F1 on 8 of 9 datasets (median difference 0.0098, adjusted p = 0.0234) [E32].
RandomForest scored higher than LogisticRegression on F1 on 9 of 9 datasets (median difference 0.0668, adjusted p = 0.0234) [E33].
HistGradientBoosting scored higher than MLP on F1 on 9 of 9 datasets (median difference 0.0172, adjusted p = 0.0234) [E34].
HistGradientBoosting scored higher than LogisticRegression on F1 on 9 of 9 datasets (median difference 0.0724, adjusted p = 0.0234) [E35].
MLP scored higher than LogisticRegression on F1 on 8 of 9 datasets (median difference 0.0427, adjusted p = 0.0234) [E36].

## Limitations

- Every conclusion concerns the datasets listed above; with a handful of datasets the tests have little power and a non-significant result is not evidence of equivalence.
- Within a dataset the repeated splits overlap, so they are summarised by their mean and never used as independent samples across datasets.
- Only scikit-learn style estimators with the arguments fixed by the protocol were run; the listed parameters are single configurations, not the result of a search.
- Datasets larger than the sampling limit were sampled with a fixed seed, which changes their size but not the class balance of the benchmark.

## Evidence ledger

| Id | Kind | Key | Detail |
|---|---|---|---|
| E1 | dataset | tb_credit | inria-soda/tabular-benchmark (clf_num_credit), script sha256 7a11beaf0e05 |
| E2 | dataset | tb_california | inria-soda/tabular-benchmark (clf_num_california), script sha256 5855211783eb |
| E3 | dataset | tb_electricity | inria-soda/tabular-benchmark (clf_num_electricity), script sha256 6e7b338d0312 |
| E4 | dataset | tb_magic | inria-soda/tabular-benchmark (clf_num_MagicTelescope), script sha256 bac94e63d991 |
| E5 | dataset | tb_bank | inria-soda/tabular-benchmark (clf_num_bank-marketing), script sha256 02d85190eb80 |
| E6 | dataset | tb_heloc | inria-soda/tabular-benchmark (clf_num_heloc), script sha256 bd3763330ce0 |
| E7 | dataset | tb_house16h | inria-soda/tabular-benchmark (clf_num_house_16H), script sha256 449cb85d7a45 |
| E8 | dataset | tb_pol | inria-soda/tabular-benchmark (clf_num_pol), script sha256 e499629d34da |
| E9 | dataset | tb_eye | inria-soda/tabular-benchmark (clf_num_eye_movements), script sha256 c127359b3806 |
| E10 | claim | C1:roc_auc | replicated, 9/9 wins |
| E11 | claim | C1:pr_auc | replicated, 8/9 wins |
| E12 | claim | C1:f1 | replicated, 9/9 wins |
| E13 | claim | C2:roc_auc | replicated, 9/9 wins |
| E14 | claim | C2:pr_auc | replicated, 9/9 wins |
| E15 | claim | C2:f1 | replicated, 9/9 wins |
| E16 | friedman | roc_auc | mean ranks over 9 datasets |
| E17 | friedman | pr_auc | mean ranks over 9 datasets |
| E18 | friedman | f1 | mean ranks over 9 datasets |
| E19 | pairwise | roc_auc:RandomForest:HistGradientBoosting | 2 wins, 7 losses, 0 ties |
| E20 | pairwise | roc_auc:RandomForest:MLP | 8 wins, 1 losses, 0 ties |
| E21 | pairwise | roc_auc:RandomForest:LogisticRegression | 9 wins, 0 losses, 0 ties |
| E22 | pairwise | roc_auc:HistGradientBoosting:MLP | 9 wins, 0 losses, 0 ties |
| E23 | pairwise | roc_auc:HistGradientBoosting:LogisticRegression | 9 wins, 0 losses, 0 ties |
| E24 | pairwise | roc_auc:MLP:LogisticRegression | 8 wins, 1 losses, 0 ties |
| E25 | pairwise | pr_auc:RandomForest:HistGradientBoosting | 0 wins, 9 losses, 0 ties |
| E26 | pairwise | pr_auc:RandomForest:MLP | 6 wins, 3 losses, 0 ties |
| E27 | pairwise | pr_auc:RandomForest:LogisticRegression | 9 wins, 0 losses, 0 ties |
| E28 | pairwise | pr_auc:HistGradientBoosting:MLP | 8 wins, 1 losses, 0 ties |
| E29 | pairwise | pr_auc:HistGradientBoosting:LogisticRegression | 9 wins, 0 losses, 0 ties |
| E30 | pairwise | pr_auc:MLP:LogisticRegression | 8 wins, 1 losses, 0 ties |
| E31 | pairwise | f1:RandomForest:HistGradientBoosting | 2 wins, 7 losses, 0 ties |
| E32 | pairwise | f1:RandomForest:MLP | 8 wins, 1 losses, 0 ties |
| E33 | pairwise | f1:RandomForest:LogisticRegression | 9 wins, 0 losses, 0 ties |
| E34 | pairwise | f1:HistGradientBoosting:MLP | 9 wins, 0 losses, 0 ties |
| E35 | pairwise | f1:HistGradientBoosting:LogisticRegression | 9 wins, 0 losses, 0 ties |
| E36 | pairwise | f1:MLP:LogisticRegression | 8 wins, 1 losses, 0 ties |
