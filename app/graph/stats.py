import numpy as np
from scipy import stats

MIN_SPLITS = 3
FLAT_STD = 1e-12


def pitman_morgan_p(first: list[float], second: list[float]) -> float:
    x = np.asarray(first, dtype=float)
    y = np.asarray(second, dtype=float)
    if x.size != y.size:
        raise ValueError("paired samples must have the same length")
    if x.size < MIN_SPLITS:
        raise ValueError(f"at least {MIN_SPLITS} paired splits are required")
    total = x + y
    difference = x - y
    if np.std(total) < FLAT_STD or np.std(difference) < FLAT_STD:
        return 1.0
    _, p_value = stats.pearsonr(total, difference)
    return float(p_value)


def holm_adjust(p_values: list[float]) -> list[float]:
    count = len(p_values)
    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (count - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted
