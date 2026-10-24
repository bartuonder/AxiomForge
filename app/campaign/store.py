import json
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2] / "reports" / "campaigns"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_LOCK = threading.Lock()
REPLACE_ATTEMPTS = 20
REPLACE_PAUSE_SECONDS = 0.02


class CampaignStoreError(ValueError):
    pass


def new_campaign_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def campaign_dir(campaign_id: str) -> Path:
    if not _ID.fullmatch(campaign_id):
        raise CampaignStoreError(f"campaign id {campaign_id!r} is not valid")
    return ROOT / campaign_id


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        with _LOCK:
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(REPLACE_PAUSE_SECONDS)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def save_state(campaign_id: str, state: dict[str, Any]) -> None:
    _write(campaign_dir(campaign_id) / "state.json", json.dumps({**state, "updated": now()}, ensure_ascii=False, indent=1))


def load_state(campaign_id: str) -> dict[str, Any] | None:
    path = campaign_dir(campaign_id) / "state.json"
    for attempt in range(REPLACE_ATTEMPTS):
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_PAUSE_SECONDS)
    return None


def save_artifacts(
    campaign_id: str,
    markdown: str,
    ledger: list[dict[str, Any]],
    analysis: dict[str, Any],
    scripts: dict[str, str],
) -> None:
    folder = campaign_dir(campaign_id)
    _write(folder / "report.md", markdown)
    _write(folder / "ledger.json", json.dumps(ledger, ensure_ascii=False, indent=1))
    _write(folder / "analysis.json", json.dumps(analysis, ensure_ascii=False, indent=1))
    for dataset, script in scripts.items():
        if not _ID.fullmatch(dataset):
            raise CampaignStoreError(f"dataset key {dataset!r} is not valid")
        _write(folder / "scripts" / f"{dataset}.py", script)


def load_report(campaign_id: str) -> str | None:
    path = campaign_dir(campaign_id) / "report.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def load_ledger(campaign_id: str) -> list[dict[str, Any]] | None:
    path = campaign_dir(campaign_id) / "ledger.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_campaigns() -> list[str]:
    if not ROOT.exists():
        return []
    return sorted((item.name for item in ROOT.iterdir() if (item / "state.json").exists()))
