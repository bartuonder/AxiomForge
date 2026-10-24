import copy
from typing import Any

from app.campaign.spec import CampaignSpecError

TREES = ["RandomForest", "HistGradientBoosting"]

GRINSZTAJN_2022: dict[str, Any] = {
    "title": "Do tree-based models still outperform neural networks on medium-sized tabular data?",
    "models": ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"],
    "claims": [
        {
            "id": "C1",
            "statement": "Tree-based models outperform a neural network (MLP) on tabular classification data",
            "metrics": ["roc_auc", "pr_auc", "f1"],
            "subject": list(TREES),
            "other": ["MLP"],
        },
        {
            "id": "C2",
            "statement": "Tree-based models outperform linear models on tabular classification data",
            "metrics": ["roc_auc", "pr_auc", "f1"],
            "subject": list(TREES),
            "other": ["LogisticRegression"],
        },
    ],
    "source": {
        "title": "Why do tree-based models still outperform deep learning on tabular data?",
        "citation": "Grinsztajn, Oyallon and Varoquaux, NeurIPS 2022 (Datasets and Benchmarks)",
        "url": "https://arxiv.org/abs/2207.08815",
        "deviations": [
            "No hyperparameter search: every model ran with library default parameters, whereas the paper tuned each model with random search.",
            "Each dataset was reduced to a fixed 6000-row balanced sample and evaluated with 80/20 stratified splits repeated over ten seeds.",
            "The neural network is scikit-learn's MLPClassifier, not the ResNet or FT-Transformer of the paper.",
            "Only the nine numeric-feature classification datasets of the benchmark available on Hugging Face were used.",
            "Tree-based models are RandomForest and HistGradientBoosting; the paper also included XGBoost and gradient boosted trees from other libraries.",
        ],
    },
}

DEMOS: dict[str, dict[str, Any]] = {"grinsztajn-2022": GRINSZTAJN_2022}


def demo_names() -> list[str]:
    return sorted(DEMOS)


def demo_spec(name: str) -> dict[str, Any]:
    if name not in DEMOS:
        raise CampaignSpecError(f"unknown demo {name!r}; available: " + ", ".join(demo_names()))
    return copy.deepcopy(DEMOS[name])
