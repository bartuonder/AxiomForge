import hashlib
import json
import re
from typing import Any

from app.datasets import DATASETS

BASE_PACKAGES = ("numpy", "pandas", "scikit-learn", "scipy", "datasets")
UNKNOWN = "unknown"
_LINE = re.compile(r"^provenance (?P<body>.+)$", re.MULTILINE)
_PAIR = re.compile(r"([\w.-]+)=(\S+)")


def spec_digest(spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def provenance_code(dataset: str, extra_packages: list[str]) -> str:
    packages = list(dict.fromkeys([*BASE_PACKAGES, *extra_packages]))
    hf_id = DATASETS[dataset]["hf_id"]
    return "\n".join(
        [
            "import sys",
            "import importlib.metadata as _metadata",
            "def _version(name):",
            "    try:",
            "        return _metadata.version(name)",
            "    except Exception:",
            f"        return {UNKNOWN!r}",
            "try:",
            "    from huggingface_hub import HfApi",
            f"    _revision = HfApi().dataset_info({hf_id!r}).sha or {UNKNOWN!r}",
            "except Exception:",
            f"    _revision = {UNKNOWN!r}",
            f"_packages = {packages!r}",
            f'print("provenance revision=" + _revision + " python=" + sys.version.split()[0] + " " + " ".join(name + "=" + _version(name) for name in _packages))',
        ]
    )


def parse_provenance(output: str) -> dict[str, Any]:
    match = _LINE.search(output)
    if match is None:
        return {}
    pairs = dict(_PAIR.findall(match.group("body")))
    revision = pairs.pop("revision", UNKNOWN)
    python = pairs.pop("python", UNKNOWN)
    return {"revision": revision, "python": python, "libraries": pairs}


def environment_sentence(provenance_by_dataset: dict[str, dict[str, Any]]) -> str:
    known = {dataset: item for dataset, item in provenance_by_dataset.items() if item}
    if not known:
        return ""
    environments = {
        json.dumps({"python": item.get("python", UNKNOWN), "libraries": item.get("libraries", {})}, sort_keys=True): dataset
        for dataset, item in known.items()
    }
    first = next(iter(known.values()))
    versions = ", ".join(f"{name} {version}" for name, version in sorted((first.get("libraries") or {}).items()))
    head = f"Environment: Python {first.get('python', UNKNOWN)}; {versions}"
    if len(environments) == 1 and len(known) == len(provenance_by_dataset):
        return head + " (identical on every dataset)."
    if len(environments) == 1:
        return head + f" (identical on the {len(known)} datasets that reported it)."
    return head + " on " + next(iter(known)) + "; the environments differed between datasets: " + ", ".join(sorted(known)) + "."
