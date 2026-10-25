import re
from typing import Any

SANDBOX_DESCRIPTORS = ("categorical_share", "mean_abs_correlation", "mean_abs_skew", "missing_share")
DESCRIPTORS = ("features", "minority_ratio", *SANDBOX_DESCRIPTORS)
DESCRIPTOR_LABELS = {
    "features": "the number of features",
    "minority_ratio": "the share of the minority class",
    "categorical_share": "the share of categorical features",
    "mean_abs_correlation": "the mean absolute correlation between features",
    "mean_abs_skew": "the mean absolute skewness of the features",
    "missing_share": "the share of missing values",
}
_LINE = re.compile(r"^descriptors (?P<body>.+)$", re.MULTILINE)
_PAIR = re.compile(r"(\w+)=(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")


def descriptors_code() -> str:
    return "\n".join(
        [
            "import numpy as _np",
            "_numeric = X.select_dtypes(include='number')",
            "_filled = _numeric.fillna(_numeric.median())",
            "_categorical_share = (X.shape[1] - _numeric.shape[1]) / max(1, X.shape[1])",
            "_correlation = 0.0",
            "if _filled.shape[1] > 1:",
            "    with _np.errstate(all='ignore'):",
            "        _matrix = _np.nan_to_num(_np.abs(_np.corrcoef(_filled.to_numpy(dtype=float), rowvar=False)))",
            "    _correlation = float(_matrix[_np.triu_indices_from(_matrix, k=1)].mean())",
            "_skew = float(_np.nan_to_num(_filled.skew().abs().to_numpy(dtype=float)).mean()) if _filled.shape[1] else 0.0",
            "_missing = float(X.isna().to_numpy().mean())",
            "print('descriptors categorical_share=%.4f mean_abs_correlation=%.4f mean_abs_skew=%.4f missing_share=%.4f' % (_categorical_share, _correlation, _skew, _missing))",
        ]
    )


def parse_descriptors(output: str) -> dict[str, float]:
    match = _LINE.search(output)
    if match is None:
        return {}
    pairs = {name: float(value) for name, value in _PAIR.findall(match.group("body"))}
    return {name: pairs[name] for name in SANDBOX_DESCRIPTORS if name in pairs}


def dataset_descriptors(profile: dict[str, Any], parsed: dict[str, float]) -> dict[str, float]:
    positive = float(profile["positive_ratio"])
    return {
        "features": float(profile["features"]),
        "minority_ratio": min(positive, 1.0 - positive),
        **parsed,
    }
