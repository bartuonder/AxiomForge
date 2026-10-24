import io
import json

import pytest

import app.campaign.__main__ as cli
import app.campaign.store as store
from app.datasets import DATASETS, benchmark_keys
from app.sandbox.e2b_runner import SandboxCodeError
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
KEYS = benchmark_keys()
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    return tmp_path / "campaigns"


def healthy(script, schema):
    dataset = next(key for key in KEYS if DATASETS[key]["config"] in script)
    shift = 0.002 * KEYS.index(dataset)
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    for _ in SPLIT_SEEDS:
        for key in expected_keys(MODELS, {"models": MODELS, "params": {}}):
            value = BASE[key] + shift
            lines.append(
                f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} "
                f"train_seconds=0.1000 tn=500 fp=100 fn=100 tp=500"
            )
    return "\n".join(lines)


def call(*argv, execute=healthy):
    out = io.StringIO()
    code = cli.main(list(argv), execute, out)
    return code, out.getvalue()


def test_the_demo_runs_and_prints_the_status_each_dataset_each_verdict_and_the_report_path(root):
    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "abc", "--workers", "2")
    assert code == 0
    assert text.splitlines()[0] == "campaign abc: completed"
    assert all(f"  {key}: finished" in text for key in KEYS)
    assert "  C1 replicated: Tree-based models outperform a neural network (MLP) on tabular classification data" in text
    assert "  C2 replicated: " in text
    assert f"report: {root / 'abc' / 'report.md'}" in text
    assert (root / "abc" / "report.md").exists()


def test_a_specification_file_can_be_used_instead_of_a_demo(tmp_path, root):
    from app.campaign.demos import demo_spec

    path = tmp_path / "spec.json"
    path.write_text(json.dumps({**demo_spec("grinsztajn-2022"), "datasets": KEYS, "title": "From a file"}), encoding="utf-8")
    code, text = call("run", "--spec", str(path), "--id", "abc")
    assert code == 0 and "campaign abc: completed" in text
    assert store.load_state("abc")["title"] == "From a file"


def test_an_unreadable_or_invalid_specification_is_a_usage_error(tmp_path):
    code, text = call("run", "--spec", str(tmp_path / "missing.json"))
    assert code == 2 and text.startswith("invalid campaign: cannot read ")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert call("run", "--spec", str(bad))[0] == 2
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    code, text = call("run", "--spec", str(empty))
    assert code == 2 and text.startswith("invalid campaign: ")


def test_an_unknown_demo_or_dataset_is_a_usage_error():
    code, text = call("run", "--demo", "nope")
    assert code == 2 and "available: grinsztajn-2022" in text
    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", "tb_credit,unknown_set")
    assert code == 2 and "unknown datasets: unknown_set" in text


def test_an_invalid_campaign_id_is_a_usage_error():
    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "../escape")
    assert code == 2 and "not valid" in text


def test_a_failed_campaign_exits_with_one_and_shows_the_error():
    def broken(script, schema):
        raise SandboxCodeError("E2B_API_KEY is missing")

    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "abc", "--workers", "1", execute=broken)
    assert code == 1 and text.splitlines()[0] == "campaign abc: failed"
    assert "  error: SandboxCodeError: E2B_API_KEY is missing" in text
    assert "report:" not in text


def test_failed_datasets_show_their_error_but_the_campaign_still_completes():
    def one_bad(script, schema):
        if DATASETS[KEYS[0]]["config"] in script:
            raise SandboxCodeError("OutOfMemory")
        return healthy(script, schema)

    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "abc", execute=one_bad)
    assert code == 0 and f"  {KEYS[0]}: failed (OutOfMemory)" in text


def test_an_unfinished_review_exits_with_one(monkeypatch):
    import app.campaign.service as service

    monkeypatch.setattr(service, "report_issues", lambda markdown, ledger: ["E9 is cited but not in the ledger"])
    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "abc")
    assert code == 1 and "campaign abc: needs_review" in text and "  issue: E9 is cited but not in the ledger" in text
    assert "report:" in text


def test_stored_campaigns_are_listed_with_status_and_title():
    assert call("list") == (0, "")
    call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "abc")
    code, text = call("list")
    assert code == 0 and text.startswith("abc completed Do tree-based models still outperform")


def test_a_stored_report_can_be_shown_and_a_missing_one_is_a_usage_error():
    call("run", "--demo", "grinsztajn-2022", "--datasets", ",".join(KEYS), "--id", "abc")
    code, text = call("show", "abc")
    assert code == 0 and text.startswith("# Do tree-based models still outperform") and "## Evidence ledger" in text
    code, text = call("show", "nope")
    assert code == 2 and text == "campaign nope has no report\n"
    code, text = call("show", "../x")
    assert code == 2 and "not valid" in text


def test_the_ready_campaigns_are_listed():
    assert call("demos") == (0, "grinsztajn-2022\n")


def test_a_command_is_required_and_a_run_needs_a_source():
    with pytest.raises(SystemExit):
        call()
    with pytest.raises(SystemExit):
        call("run")
    with pytest.raises(SystemExit):
        call("run", "--demo", "grinsztajn-2022", "--spec", "x.json")


def test_blank_dataset_keys_are_ignored():
    code, text = call("run", "--demo", "grinsztajn-2022", "--datasets", f" {KEYS[0]} , ,{",".join(KEYS[1:])}", "--id", "abc")
    assert code == 0 and list(store.load_state("abc")["datasets"]) == KEYS


def test_the_worker_count_is_passed_on_and_defaults_to_the_runner_default(monkeypatch):
    seen = []

    def fake(spec, campaign_id, execute, workers, tracker=None):
        seen.append(workers)
        return {"id": "abc", "status": "completed", "datasets": {}}

    monkeypatch.setattr(cli, "execute_campaign", fake)
    call("run", "--demo", "grinsztajn-2022")
    call("run", "--demo", "grinsztajn-2022", "--workers", "5")
    assert seen == [cli.DEFAULT_WORKERS, 5]


def test_mlflow_tracking_is_off_by_default_and_on_with_the_flag(monkeypatch):
    seen = []

    def fake(spec, campaign_id, execute, workers, tracker=None):
        seen.append(tracker)
        return {"id": "abc", "status": "completed", "datasets": {}, "mlflow_run_id": "run-9" if tracker else ""}

    monkeypatch.setattr(cli, "execute_campaign", fake)
    code, text = call("run", "--demo", "grinsztajn-2022")
    assert seen == [None] and "mlflow run" not in text
    code, text = call("run", "--demo", "grinsztajn-2022", "--mlflow")
    assert seen[1] is cli.log_campaign and "mlflow run: run-9" in text
