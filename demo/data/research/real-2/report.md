# Research session real-2

Status: completed

## Protocol

Hypothesis generator: rules.

The pool of 16 datasets was split once and for good into 6 exploration datasets and 10 confirmation datasets (seeded, deterministic). The hypothesis generator saw only the exploration datasets; the confirmation results stayed sealed until every hypothesis was registered and saved. Each registered hypothesis was tested exactly once on the confirmation datasets (two-sided Wilcoxon over datasets, one primary metric, ROC-AUC). All registered hypotheses of the session share one Holm correction (family-wise error) and a Benjamini-Hochberg q value; a hypothesis counts as confirmed only when its Holm adjusted p is below 0.05 and the confirmation effect has the registered direction. The confirmation set allows at most 25 hypotheses to be significant at all.

Exploration datasets: tb_magic, tb_heloc, tb_eye, tb_bioresponse, tb_diabetes, tb_jannis.
Confirmation datasets: tb_credit, tb_california, tb_electricity, tb_bank, tb_house16h, tb_pol, tb_higgs, tb_miniboone, tb_covertype, tb_creditcard.

## Result

16 registered, 15 confirmed, 0 reversed, 1 not confirmed, 0 not testable.

| id | stage | claim | exploration estimate (median diff, wins) | confirmation effect (median diff, wins) | p | adjusted p (Holm) | q (BH) | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H1 | default | HistGradientBoosting scores higher than LogisticRegression on roc_auc (default stage) | 0.0440, 5/6 | 0.0585, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H2 | default | RandomForest scores higher than LogisticRegression on roc_auc (default stage) | 0.0403, 5/6 | 0.0548, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H3 | default | ExtraTrees scores higher than LogisticRegression on roc_auc (default stage) | 0.0354, 5/6 | 0.0553, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H4 | default | GradientBoosting scores higher than LogisticRegression on roc_auc (default stage) | 0.0328, 6/6 | 0.0559, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H5 | default | HistGradientBoosting scores higher than MLP on roc_auc (default stage) | 0.0311, 5/6 | 0.0126, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H6 | default | ExtraTrees scores higher than MLP on roc_auc (default stage) | 0.0292, 5/6 | 0.0049, 7/10 | 0.08398 | 0.08398 | 0.08398 | not_confirmed |
| H7 | default | RandomForest scores higher than MLP on roc_auc (default stage) | 0.0291, 5/6 | 0.0073, 8/10 | 0.00977 | 0.03125 | 0.01116 | confirmed |
| H8 | default | GradientBoosting scores higher than MLP on roc_auc (default stage) | 0.0235, 5/6 | 0.0117, 8/10 | 0.01367 | 0.03125 | 0.01458 | confirmed |
| H9 | tuned | ExtraTrees scores higher than MLP on roc_auc (tuned stage) | 0.0545, 6/6 | 0.0105, 9/10 | 0.00391 | 0.03125 | 0.00521 | confirmed |
| H10 | tuned | RandomForest scores higher than MLP on roc_auc (tuned stage) | 0.0522, 6/6 | 0.0205, 9/10 | 0.00391 | 0.03125 | 0.00521 | confirmed |
| H11 | tuned | HistGradientBoosting scores higher than MLP on roc_auc (tuned stage) | 0.0515, 6/6 | 0.0164, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H12 | tuned | GradientBoosting scores higher than MLP on roc_auc (tuned stage) | 0.0503, 5/6 | 0.0146, 9/10 | 0.00586 | 0.03125 | 0.00721 | confirmed |
| H13 | tuned | RandomForest scores higher than LogisticRegression on roc_auc (tuned stage) | 0.0364, 6/6 | 0.0480, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H14 | tuned | HistGradientBoosting scores higher than LogisticRegression on roc_auc (tuned stage) | 0.0358, 6/6 | 0.0528, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H15 | tuned | ExtraTrees scores higher than LogisticRegression on roc_auc (tuned stage) | 0.0346, 6/6 | 0.0453, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |
| H16 | tuned | GradientBoosting scores higher than LogisticRegression on roc_auc (tuned stage) | 0.0322, 6/6 | 0.0503, 10/10 | 0.00195 | 0.03125 | 0.00313 | confirmed |

The exploration estimate is inflated by selection (the hypothesis was chosen because it looked strong there); only the confirmation effect is an unbiased estimate.

## Limits

- Hypotheses are limited to model comparisons and tuning effects on binary classification of tabular data.
- The datasets come from one benchmark; the exploration set is small, so the generator sees a noisy picture.
- The protocol would stay valid with any hypothesis generator that only reads the exploration datasets; this session used the generator named above.
- This is exploratory analysis with statistical safeguards, not a new scientific discovery.
