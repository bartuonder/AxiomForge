import ast
import io

import pytest

import app.campaign.__main__ as cli
import app.campaign.runner as runner
from app.campaign.__main__ import main as cli_main
from app.campaign.protocol import ProtocolError, build_script
from app.campaign.provenance import provenance_code
from app.campaign.runner import run_dataset
from app.campaign.spec import CampaignSpecError, validate_campaign
from app.datasets import DATASETS, loader_code, pinned_loader_code
from app.seeds import SPLIT_SEEDS

SHA = "8d0ff9103525b7e3579b180230fddb3186258301"
OTHER = "a" * 40
RAW = {
    "title": "T",
    "models": ["RandomForest", "MLP"],
    "datasets": ["tb_credit", "tb_electricity"],
    "claims": [{"statement": "Trees win", "metric": "roc_auc", "subject": ["RandomForest"], "other": ["MLP"]}],
}


class TestSpec:
    def test_pinned_revisions_are_kept(self):
        spec = validate_campaign({**RAW, "revisions": {"tb_credit": SHA}})
        assert spec["revisions"] == {"tb_credit": SHA}

    def test_uppercase_hex_is_normalised(self):
        assert validate_campaign({**RAW, "revisions": {"tb_credit": SHA.upper()}})["revisions"] == {"tb_credit": SHA}

    def test_no_revisions_leave_the_spec_unchanged(self):
        assert "revisions" not in validate_campaign(RAW)
        assert "revisions" not in validate_campaign({**RAW, "revisions": {}})
        assert "revisions" not in validate_campaign({**RAW, "revisions": None})

    @pytest.mark.parametrize("value", ["main", SHA[:39], SHA + "0", "g" * 40, "", 5, None])
    def test_a_bad_revision_is_refused(self, value):
        with pytest.raises(CampaignSpecError, match="revision"):
            validate_campaign({**RAW, "revisions": {"tb_credit": value}})

    def test_a_revision_for_a_dataset_outside_the_campaign_is_refused(self):
        with pytest.raises(CampaignSpecError, match="tb_pol"):
            validate_campaign({**RAW, "revisions": {"tb_pol": SHA}})

    @pytest.mark.parametrize("raw", [["tb_credit"], "x", 3])
    def test_revisions_must_be_an_object(self, raw):
        with pytest.raises(CampaignSpecError, match="revisions must be an object"):
            validate_campaign({**RAW, "revisions": raw})

    def test_revisions_change_the_digest(self):
        from app.campaign.provenance import spec_digest

        assert spec_digest(validate_campaign(RAW)) != spec_digest(validate_campaign({**RAW, "revisions": {"tb_credit": SHA}}))


class TestLoader:
    @pytest.mark.parametrize("key", ["tb_credit", "credit_default", "adult_income"])
    def test_the_pinned_code_adds_the_revision_to_the_load_call(self, key):
        code = pinned_loader_code(key, SHA)
        assert f'split="train", revision="{SHA}")' in code
        ast.parse(code)

    def test_everything_but_the_load_call_is_unchanged(self):
        plain = loader_code("tb_credit").splitlines()
        pinned = pinned_loader_code("tb_credit", SHA).splitlines()
        assert len(plain) == len(pinned)
        changed = [(a, b) for a, b in zip(plain, pinned) if a != b]
        assert len(changed) == 1 and changed[0][1] == changed[0][0].replace('split="train")', f'split="train", revision="{SHA}")')

    def test_the_plain_loader_is_untouched(self):
        assert "revision" not in loader_code("tb_credit")

    @pytest.mark.parametrize("value", ["main", SHA[:10], "x" * 40])
    def test_a_bad_revision_is_refused(self, value):
        with pytest.raises(ValueError, match="revision"):
            pinned_loader_code("tb_credit", value)

    def test_every_dataset_can_be_pinned(self):
        for key in DATASETS:
            assert f'revision="{SHA}"' in pinned_loader_code(key, SHA)


class TestProvenance:
    def test_without_a_revision_the_head_is_asked(self):
        code = provenance_code("tb_credit", [])
        assert "dataset_info('inria-soda/tabular-benchmark').sha" in code and ", revision=" not in code

    def test_with_a_revision_that_commit_is_asked(self):
        code = provenance_code("tb_credit", [], SHA)
        assert f"dataset_info('inria-soda/tabular-benchmark', revision='{SHA}').sha" in code
        ast.parse(code)


class TestScript:
    MODELS = ["RandomForest", "MLP"]

    def test_the_script_loads_the_pinned_commit(self):
        script = build_script("tb_credit", self.MODELS, None, SPLIT_SEEDS, None, {"tb_credit": SHA})
        assert f'split="train", revision="{SHA}")' in script and f"revision='{SHA}'" in script

    def test_other_datasets_stay_unpinned(self):
        script = build_script("tb_credit", self.MODELS, None, SPLIT_SEEDS, None, {"tb_electricity": SHA})
        assert "revision=" not in script.split("provenance")[0]

    def test_without_revisions_the_script_is_unchanged(self):
        assert build_script("tb_credit", self.MODELS) == build_script("tb_credit", self.MODELS, None, SPLIT_SEEDS, None, None)
        assert "revision=" not in build_script("tb_credit", self.MODELS).split("print(\"provenance")[0].split("frame = load_dataset")[1]

    def test_a_bad_revision_is_a_protocol_error(self):
        with pytest.raises(ProtocolError, match="revision"):
            build_script("tb_credit", self.MODELS, None, SPLIT_SEEDS, None, {"tb_credit": "main"})

    def test_the_script_is_valid_python(self):
        ast.parse(build_script("tb_credit", self.MODELS, None, SPLIT_SEEDS, None, {"tb_credit": SHA}))


class TestRunner:
    def test_the_runner_pins_the_dataset_of_the_spec(self):
        seen = []

        def execute(script, schema):
            seen.append(script)
            raise RuntimeError("stop")

        spec = {**validate_campaign({**RAW, "revisions": {"tb_credit": SHA}})}
        run_dataset("tb_credit", spec, execute=execute, attempts=1)
        run_dataset("tb_electricity", spec, execute=execute, attempts=1)
        assert f'revision="{SHA}"' in seen[0] and "revision=" not in seen[1].split("print(\"provenance")[0].split("frame = load_dataset")[1]


LEDGER = [
    {"kind": "dataset", "key": "tb_credit", "provenance": {"revision": SHA}},
    {"kind": "dataset", "key": "tb_electricity", "provenance": {"revision": "unknown"}},
    {"kind": "dataset", "key": "tb_pol", "provenance": {"revision": OTHER}},
    {"kind": "claim", "key": "tb_credit", "provenance": {"revision": OTHER}},
]


class TestPinFrom:
    def run(self, monkeypatch, ledger=LEDGER, extra=None):
        seen = []
        monkeypatch.setattr(cli.store, "load_ledger", lambda campaign_id: ledger)
        monkeypatch.setattr(cli, "execute_campaign", lambda spec, campaign_id, execute, workers, tracker=None: seen.append(spec) or {"id": "abc", "status": "completed", "datasets": {}})
        out = io.StringIO()
        code = cli_main(["run", "--demo", "grinsztajn-2022", "--datasets", "tb_credit,tb_electricity", "--pin-from", "old-run", *(extra or [])], None, out)
        return code, seen, out.getvalue()

    def test_the_known_revisions_of_the_old_campaign_are_pinned(self, monkeypatch):
        code, seen, _ = self.run(monkeypatch)
        assert code == 0 and seen[0]["revisions"] == {"tb_credit": SHA}

    def test_unknown_revisions_and_datasets_outside_the_run_are_skipped(self, monkeypatch):
        _, seen, _ = self.run(monkeypatch)
        assert "tb_electricity" not in seen[0]["revisions"] and "tb_pol" not in seen[0]["revisions"]

    def test_a_missing_campaign_is_a_usage_error(self, monkeypatch):
        code, seen, text = self.run(monkeypatch, ledger=None)
        assert code == 2 and seen == [] and "old-run" in text

    def test_a_ledger_without_any_known_revision_is_a_usage_error(self, monkeypatch):
        code, seen, text = self.run(monkeypatch, ledger=[{"kind": "dataset", "key": "tb_credit", "provenance": {"revision": "unknown"}}])
        assert code == 2 and seen == [] and "no revision" in text

    def test_without_the_flag_nothing_is_pinned(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "execute_campaign", lambda spec, campaign_id, execute, workers, tracker=None: seen.append(spec) or {"id": "abc", "status": "completed", "datasets": {}})
        cli_main(["run", "--demo", "grinsztajn-2022"], None, io.StringIO())
        assert "revisions" not in seen[0]


class TestReport:
    def test_a_pinned_campaign_says_so_in_the_protocol(self):
        from app.campaign.analysis import analyze_campaign
        from app.campaign.report import render_report

        spec = validate_campaign({**RAW, "revisions": {"tb_credit": SHA}})
        summary = {name: {f"{metric}_mean": 0.8 for metric in ("roc_auc", "pr_auc", "f1")} for name in spec["models"]}
        data = {
            "order": spec["datasets"],
            "datasets": {
                key: {"summary": summary, "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5}, "provenance": {"revision": SHA if key == "tb_credit" else OTHER}, "seconds": 1.0, "attempts": 1, "script": key}
                for key in spec["datasets"]
            },
            "failed": {},
        }
        markdown, _ = render_report(spec, data, analyze_campaign(spec, data))
        protocol = markdown.split("## Protocol")[1].split("## Results")[0]
        assert "Dataset revisions pinned in the specification: tb_credit." in protocol
        spec_plain = validate_campaign(RAW)
        markdown_plain, _ = render_report(spec_plain, data, analyze_campaign(spec_plain, data))
        assert "pinned in the specification" not in markdown_plain
