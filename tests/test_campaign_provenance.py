import ast
import contextlib
import io
import re
import sys
import types

import pytest

import app.campaign.provenance as provenance
import app.campaign.service as service
import app.campaign.store as store
from app.campaign.analysis import analyze_campaign
from app.campaign.ledger import build_ledger
from app.campaign.protocol import build_script
from app.campaign.provenance import BASE_PACKAGES, environment_sentence, parse_provenance, provenance_code, spec_digest
from app.campaign.report import render_report
from app.campaign.runner import run_dataset
from app.campaign.spec import CampaignSpecError
from app.datasets import benchmark_keys
from app.seeds import SPLIT_SEEDS
from app.variants import expected_keys

MODELS = ["RandomForest", "HistGradientBoosting", "MLP", "LogisticRegression"]
CLAIMS = [{"id": "C1", "statement": "Trees beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"], "subject": ["RandomForest", "HistGradientBoosting"], "other": ["MLP"]}]
SPEC = {"title": "T", "models": MODELS, "params": {}, "claims": CLAIMS, "datasets": benchmark_keys(), "source": {}}
KEYS = benchmark_keys()
BASE = {"RandomForest": 0.90, "HistGradientBoosting": 0.92, "MLP": 0.85, "LogisticRegression": 0.80}
LINE = "provenance revision=0123456789abcdef0123456789abcdef01234567 python=3.12.4 numpy=1.26.4 pandas=2.2.2 scikit-learn=1.5.0 scipy=1.13.1 datasets=2.20.0"


class TestDigest:
    def test_it_is_a_sha256_in_hex(self):
        assert re.fullmatch(r"[0-9a-f]{64}", spec_digest(SPEC))

    def test_it_ignores_key_order(self):
        assert spec_digest(SPEC) == spec_digest(dict(reversed(list(SPEC.items()))))

    @pytest.mark.parametrize("change", [{"title": "U"}, {"models": MODELS[:3]}, {"datasets": KEYS[:8]}, {"params": {"MLP": {"alpha": 0.01}}}, {"claims": []}])
    def test_any_change_gives_another_digest(self, change):
        assert spec_digest({**SPEC, **change}) != spec_digest(SPEC)

    def test_non_ascii_text_is_hashed_as_written(self):
        assert spec_digest({"title": "Çalışma"}) != spec_digest({"title": "Calisma"})


class TestParse:
    def test_a_full_line_is_split_into_revision_python_and_libraries(self):
        assert parse_provenance(LINE) == {
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "python": "3.12.4",
            "libraries": {"numpy": "1.26.4", "pandas": "2.2.2", "scikit-learn": "1.5.0", "scipy": "1.13.1", "datasets": "2.20.0"},
        }

    def test_the_line_may_sit_between_other_output(self):
        output = "dataset=tb_credit samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50\n" + LINE + "\nmodel=A accuracy=0.9\n"
        assert parse_provenance(output)["python"] == "3.12.4"

    def test_a_missing_line_gives_an_empty_record(self):
        assert parse_provenance("dataset=x samples=1") == {}
        assert parse_provenance("") == {}

    def test_a_line_that_does_not_start_the_line_is_not_a_provenance_line(self):
        assert parse_provenance("model=A provenance revision=abc python=3 numpy=1") == {}

    def test_missing_fields_become_unknown(self):
        assert parse_provenance("provenance numpy=1.0") == {"revision": "unknown", "python": "unknown", "libraries": {"numpy": "1.0"}}

    def test_unknown_versions_are_kept_as_they_are(self):
        assert parse_provenance("provenance revision=unknown python=3.12.4 xgboost=unknown")["libraries"] == {"xgboost": "unknown"}


class TestCode:
    def test_it_is_plain_python_without_comments(self):
        code = provenance_code("tb_credit", [])
        ast.parse(code)
        assert "#" not in code

    def test_it_asks_the_hub_about_the_dataset_of_the_key(self):
        assert "'inria-soda/tabular-benchmark'" in provenance_code("tb_credit", [])
        assert "'scikit-learn/breast-cancer-wisconsin'" in provenance_code("breast_cancer", [])

    def test_base_and_model_packages_are_listed_once(self):
        code = provenance_code("tb_credit", ["xgboost", "numpy", "xgboost"])
        listed = ast.literal_eval(re.search(r"_packages = (\[.*?\])", code).group(1))
        assert listed == [*BASE_PACKAGES, "xgboost"]

    def run(self, monkeypatch, sha="abc123", fail=False):
        class Api:
            def dataset_info(self, hf_id):
                if fail:
                    raise ConnectionError("offline")
                return types.SimpleNamespace(sha=sha, id=hf_id)

        module = types.ModuleType("huggingface_hub")
        module.HfApi = Api
        monkeypatch.setitem(sys.modules, "huggingface_hub", module)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(provenance_code("tb_credit", []), "p", "exec"), {})
        return out.getvalue()

    def test_running_it_prints_the_revision_the_python_and_the_versions(self, monkeypatch):
        parsed = parse_provenance(self.run(monkeypatch))
        assert parsed["revision"] == "abc123"
        assert parsed["python"] == sys.version.split()[0]
        assert set(parsed["libraries"]) == set(BASE_PACKAGES)
        assert parsed["libraries"]["numpy"] != "unknown" and parsed["libraries"]["scikit-learn"] != "unknown"

    def test_an_unreachable_hub_gives_an_unknown_revision_instead_of_an_error(self, monkeypatch):
        assert parse_provenance(self.run(monkeypatch, fail=True))["revision"] == "unknown"

    def test_a_package_that_is_not_installed_is_unknown(self, monkeypatch):
        out = io.StringIO()
        module = types.ModuleType("huggingface_hub")
        module.HfApi = lambda: types.SimpleNamespace(dataset_info=lambda hf_id: types.SimpleNamespace(sha="s"))
        monkeypatch.setitem(sys.modules, "huggingface_hub", module)
        with contextlib.redirect_stdout(out):
            exec(compile(provenance_code("tb_credit", ["definitely-not-installed-package"]), "p", "exec"), {})
        assert parse_provenance(out.getvalue())["libraries"]["definitely-not-installed-package"] == "unknown"

    def test_a_missing_sha_is_unknown(self, monkeypatch):
        assert parse_provenance(self.run(monkeypatch, sha=None))["revision"] == "unknown"


class TestScript:
    def test_the_campaign_script_prints_the_provenance_after_the_data_block(self):
        script = build_script("tb_credit", MODELS)
        assert script.index("dataset=tb_credit") < script.index("provenance revision=")

    def test_packages_of_the_models_are_part_of_the_record(self):
        script = build_script("tb_credit", ["RandomForest", "XGBoost"])
        assert "'xgboost'" in script.split("_packages = ")[1].split("\n")[0]

    def test_a_script_without_extra_packages_lists_only_the_base_ones(self):
        listed = ast.literal_eval(re.search(r"_packages = (\[.*?\])", build_script("tb_credit", MODELS)).group(1))
        assert listed == list(BASE_PACKAGES)


def fake_output(dataset, with_provenance=True, revision="deadbeefcafe1234"):
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    if with_provenance:
        lines.append(f"provenance revision={revision} python=3.12.4 numpy=1.26.4 pandas=2.2.2 scikit-learn=1.5.0 scipy=1.13.1 datasets=2.20.0")
    for _ in SPLIT_SEEDS:
        for key in expected_keys(MODELS, {"models": MODELS, "params": {}}):
            value = BASE[key]
            lines.append(f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} train_seconds=0.1 tn=1 fp=1 fn=1 tp=1")
    return "\n".join(lines)


class TestRunner:
    def test_the_parsed_provenance_travels_with_the_dataset_result(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit"))
        assert result["provenance"]["revision"] == "deadbeefcafe1234" and result["provenance"]["libraries"]["scikit-learn"] == "1.5.0"

    def test_output_without_the_line_still_finishes_with_an_empty_record(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit", with_provenance=False))
        assert result["status"] == "finished" and result["provenance"] == {}


def outcome(revision="deadbeefcafe1234", with_provenance=True, keys=KEYS):
    data = {"order": list(keys), "datasets": {}, "failed": {}}
    for index, key in enumerate(keys):
        result = run_dataset(key, SPEC, lambda script, schema, key=key: fake_output(key, with_provenance, revision if index % 2 == 0 else revision))
        data["datasets"][key] = result
    return data


def report(data, spec=SPEC):
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    return markdown, ledger


class TestLedgerAndReport:
    def test_every_dataset_entry_carries_its_provenance(self):
        markdown, ledger = report(outcome())
        entries = [entry for entry in ledger if entry["kind"] == "dataset"]
        assert len(entries) == 9 and all(entry["provenance"]["revision"] == "deadbeefcafe1234" for entry in entries)

    def test_the_specification_digest_is_in_the_protocol(self):
        markdown, _ = report(outcome())
        protocol = markdown.split("## Protocol")[1].split("## Results")[0]
        assert f"Specification: SHA-256 {spec_digest(SPEC)}, computed before the first dataset started." in protocol

    def test_the_dataset_lines_show_a_short_revision(self):
        markdown, _ = report(outcome())
        assert "- tb_credit: inria-soda/tabular-benchmark (clf_num_credit), 6000 rows, 10 features, revision deadbeefca [E1]" in markdown

    def test_an_unknown_revision_is_left_out(self):
        markdown, _ = report(outcome(revision="unknown"))
        assert ", revision" not in markdown

    def test_the_environment_is_stated_once_when_it_is_identical(self):
        markdown, _ = report(outcome())
        assert "Environment: Python 3.12.4; datasets 2.20.0, numpy 1.26.4, pandas 2.2.2, scikit-learn 1.5.0, scipy 1.13.1 (identical on every dataset)." in markdown

    def test_without_any_provenance_there_is_no_environment_line_and_no_revision(self):
        markdown, ledger = report(outcome(with_provenance=False))
        assert "Environment:" not in markdown and ", revision" not in markdown
        assert all(entry["provenance"] == {} for entry in ledger if entry["kind"] == "dataset")

    def test_the_digest_follows_the_specification(self):
        first, _ = report(outcome())
        other = {**SPEC, "title": "Another title"}
        second, _ = report(outcome(), other)
        assert spec_digest(SPEC) in first and spec_digest(other) in second and spec_digest(SPEC) not in second


class TestEnvironmentSentence:
    A = {"revision": "r", "python": "3.12.4", "libraries": {"numpy": "1.26.4", "pandas": "2.2.2"}}
    B = {"revision": "r", "python": "3.12.4", "libraries": {"numpy": "2.0.0", "pandas": "2.2.2"}}

    def test_nothing_known_gives_nothing(self):
        assert environment_sentence({}) == "" and environment_sentence({"a": {}, "b": {}}) == ""

    def test_identical_environments(self):
        assert environment_sentence({"a": self.A, "b": dict(self.A)}) == "Environment: Python 3.12.4; numpy 1.26.4, pandas 2.2.2 (identical on every dataset)."

    def test_some_datasets_without_a_record_are_counted(self):
        assert environment_sentence({"a": self.A, "b": {}}).endswith("(identical on the 1 datasets that reported it).")

    def test_different_environments_are_reported(self):
        sentence = environment_sentence({"a": self.A, "b": self.B})
        assert "the environments differed between datasets: a, b." in sentence and "identical" not in sentence

    def test_the_library_order_is_alphabetical(self):
        sentence = environment_sentence({"a": {"python": "3", "libraries": {"zlib": "1", "alpha": "2"}}})
        assert sentence.index("alpha 2") < sentence.index("zlib 1")


class TestPreRegistration:
    @pytest.fixture(autouse=True)
    def root(self, tmp_path, monkeypatch):
        monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")

    def healthy(self, script, schema):
        dataset = next(key for key in KEYS if key in script or True)
        return fake_output(KEYS[0])

    def test_the_state_records_the_digest_when_the_campaign_is_queued(self):
        campaign_id, spec = service.queue_campaign(SPEC)
        assert store.load_state(campaign_id)["spec_sha256"] == spec_digest(spec)

    def test_queue_once_records_it_too(self):
        spec, _ = service.queue_once("g-1", SPEC)
        assert store.load_state("g-1")["spec_sha256"] == spec_digest(spec)

    def test_a_changed_specification_is_refused_after_queueing(self):
        campaign_id, spec = service.queue_campaign(SPEC)
        with pytest.raises(CampaignSpecError, match="changed after it was queued"):
            service.execute_campaign({**spec, "title": "Edited after approval"}, campaign_id, self.healthy, workers=1)
        assert store.load_state(campaign_id)["status"] == "queued"

    def test_the_same_specification_runs(self):
        campaign_id, spec = service.queue_campaign(SPEC)
        state = service.execute_campaign(spec, campaign_id, self.healthy, workers=1, attempts=1)
        assert state["spec_sha256"] == spec_digest(spec) and state["status"] in {"completed", "needs_review", "failed"}

    def test_a_campaign_without_a_queued_state_runs_and_records_its_digest(self):
        state = service.execute_campaign(SPEC, "fresh", self.healthy, workers=1, attempts=1)
        assert state["spec_sha256"] == spec_digest(service.validate_campaign(SPEC))

    def test_an_old_state_without_a_digest_does_not_block_a_run(self):
        store.save_state("old", {"id": "old", "title": "T", "status": "queued", "datasets": {}})
        state = service.execute_campaign(SPEC, "old", self.healthy, workers=1, attempts=1)
        assert state["spec_sha256"]


class TestSecondPass:
    def test_the_base_packages_are_exactly_these(self):
        assert BASE_PACKAGES == ("numpy", "pandas", "scikit-learn", "scipy", "datasets")

    def test_the_digest_is_the_sha256_of_the_canonical_json(self):
        import hashlib

        assert spec_digest({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()
        assert spec_digest({"title": "\u00c7al\u0131\u015fma"}) == hashlib.sha256('{"title":"\u00c7al\u0131\u015fma"}'.encode("utf-8")).hexdigest()
        assert spec_digest({"b": [1, 2], "a": {"y": 1, "x": 2}}) == hashlib.sha256(b'{"a":{"x":2,"y":1},"b":[1,2]}').hexdigest()

    def test_the_printed_line_has_the_short_python_version_followed_by_the_packages(self, monkeypatch):
        output = TestCode().run(monkeypatch)
        assert f" python={sys.version.split()[0]} numpy=" in output and "(" not in output.split("python=")[1].split(" numpy=")[0]

    def test_a_differing_environment_on_one_dataset_is_reported_in_the_report(self):
        data = outcome()
        data["datasets"]["tb_pol"]["provenance"]["libraries"]["numpy"] = "2.0.0"
        markdown, _ = report(data)
        line = next(item for item in markdown.splitlines() if item.startswith("Environment:"))
        assert "the environments differed between datasets" in line and "tb_pol" in line and "identical" not in line
