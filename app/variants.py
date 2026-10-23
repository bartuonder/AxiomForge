from typing import Any

BASELINE_SUFFIX = "__default"


def baseline_name(model: str) -> str:
    return f"{model}{BASELINE_SUFFIX}"


def is_baseline(name: str) -> bool:
    return name.endswith(BASELINE_SUFFIX)


def base_model(name: str) -> str:
    return name[: -len(BASELINE_SUFFIX)] if is_baseline(name) else name


def display_name(name: str) -> str:
    return f"{base_model(name)} (default)" if is_baseline(name) else name


def configured_models(spec: dict[str, Any] | None) -> list[str]:
    if not spec:
        return []
    params = spec.get("params") or {}
    return [model for model in spec.get("models", []) if params.get(model)]


def expected_keys(model_keys: list[str], spec: dict[str, Any] | None) -> list[str]:
    configured = set(configured_models(spec))
    keys: list[str] = []
    for key in model_keys:
        keys.append(key)
        if key in configured:
            keys.append(baseline_name(key))
    return keys
