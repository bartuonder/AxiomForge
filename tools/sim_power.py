import argparse
import json

from sklearn.datasets import make_classification
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from app.graph.stats import corrected_resampled_t
from app.seeds import SPLIT_SEEDS

ROWS = 1000
SCENARIOS = {
    "null (same algorithm, other seed)": (
        lambda seed: ExtraTreesClassifier(n_estimators=20, random_state=seed),
        lambda seed: ExtraTreesClassifier(n_estimators=20, random_state=seed + 7),
    ),
    "moderate difference (depth 6 against full depth)": (
        lambda seed: ExtraTreesClassifier(n_estimators=20, random_state=seed),
        lambda seed: ExtraTreesClassifier(n_estimators=20, max_depth=6, random_state=seed),
    ),
    "large difference (depth 2 against full depth)": (
        lambda seed: ExtraTreesClassifier(n_estimators=20, random_state=seed),
        lambda seed: ExtraTreesClassifier(n_estimators=20, max_depth=2, random_state=seed),
    ),
}


def split_scores(features, labels, seeds, make_first, make_second):
    first, second = [], []
    for seed in seeds:
        X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=seed, stratify=labels)
        first.append(accuracy_score(y_test, make_first(seed).fit(X_train, y_train).predict(X_test)))
        second.append(accuracy_score(y_test, make_second(seed).fit(X_train, y_train).predict(X_test)))
    return first, second


def rejection_rate(make_first, make_second, splits: int, replications: int) -> float:
    rejected = 0
    for replication in range(replications):
        features, labels = make_classification(n_samples=ROWS, n_features=10, n_informative=4, class_sep=0.6, random_state=1000 + replication)
        first, second = split_scores(features, labels, SPLIT_SEEDS[:splits], make_first, make_second)
        _, _, p_value = corrected_resampled_t(first, second, int(ROWS * 0.8), int(ROWS * 0.2))
        rejected += p_value < 0.05
    return rejected / replications


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate the type I error and the power of the corrected resampled t test.")
    parser.add_argument("--replications", type=int, default=150)
    parser.add_argument("--splits", type=int, nargs="+", default=[5, 10])
    arguments = parser.parse_args(argv)
    for splits in arguments.splits:
        for label, (make_first, make_second) in SCENARIOS.items():
            rate = rejection_rate(make_first, make_second, splits, arguments.replications)
            print(json.dumps({"scenario": label, "splits": splits, "replications": arguments.replications, "rejection_rate": round(rate, 3)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
