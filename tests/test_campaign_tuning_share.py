import io

import pytest

import app.campaign.__main__ as cli
import app.campaign.planning as planning
from app.campaign.__main__ import main as cli_main
from app.campaign.analysis import analyze_campaign
from app.campaign.protocol import ESTIMATORS, build_script
from app.campaign.report import render_report
from app.campaign.tuning import (
    DEFAULT_FOLDS,
    DEFAULT_ITERATIONS,
    MAX_SHARE,
    MIN_SHARE,
    TUNING_SHARE,
    TuningError,
    tuning_code,
    validate_tuning,
)
from app.seeds import SPLIT_SEEDS

MODELS = ["MLP", "HistGradientBoosting"]


class TestValidation:
    def test_the_share_is_optional_and_absent_by_default(self):
        assert validate_tuning({"iterations": 8}, MODELS) == {"iterations": 8, "folds": DEFAULT_FOLDS}

    def test_a_given_share_is_kept_as_a_float(self):
        assert validate_tuning({"share": 0.5}, MODELS) == {"iterations": DEFAULT_ITERATIONS, "folds": DEFAULT_FOLDS, "share": 0.5}
        assert validate_tuning({"share": 1 / 4}, MODELS)["share"] == 0.25
        assert isinstance(validate_tuning({"share": 0.5}, MODELS)["share"], float)

    def test_the_bounds_are_inclusive(self):
        assert validate_tuning({"share": MIN_SHARE}, MODELS)["share"] == MIN_SHARE
        assert validate_tuning({"share": MAX_SHARE}, MODELS)["share"] == MAX_SHARE

    def test_the_documented_bounds(self):
        assert (MIN_SHARE, MAX_SHARE, TUNING_SHARE) == (0.1, 0.6, 0.2)

    @pytest.mark.parametrize("value", [0.09, 0.61, 0, 1, -0.2, float("nan"), float("inf"), True, "0.5", None, [0.5]])
    def test_a_bad_share_is_refused(self, value):
        with pytest.raises(TuningError, match="tuning share must be a number from 0.1 to 0.6"):
            validate_tuning({"share": value}, MODELS)

    def test_other_unknown_fields_are_still_refused(self):
        with pytest.raises(TuningError, match="unknown fields: sharee"):
            validate_tuning({"sharee": 0.5}, MODELS)


class TestCode:
    def test_the_default_share_is_the_constant(self):
        assert "train_size=0.2," in tuning_code(MODELS, 12, 3, ESTIMATORS)

    def test_a_share_reaches_the_split(self):
        code = tuning_code(MODELS, 12, 3, ESTIMATORS, 0.5)
        assert "train_size=0.5," in code and "train_size=0.2," not in code

    def test_the_script_uses_the_share_of_the_setting(self):
        script = build_script("tb_credit", MODELS, None, SPLIT_SEEDS, {"iterations": 4, "folds": 3, "share": 0.4})
        assert "train_size=0.4," in script

    def test_the_script_keeps_the_default_without_a_share(self):
        assert "train_size=0.2," in build_script("tb_credit", MODELS, None, SPLIT_SEEDS, {"iterations": 4, "folds": 3})


def spec_for(tuning):
    return {"title": "T", "models": MODELS, "params": {}, "tuning": tuning, "claims": [{"id": "C1", "statement": "s", "metric": "roc_auc", "metrics": ["roc_auc"], "subject": ["HistGradientBoosting"], "other": ["MLP"]}], "datasets": ["tb_credit", "tb_electricity"], "source": {}}


def protocol_of(tuning):
    spec = spec_for(tuning)
    data = {
        "order": ["tb_credit", "tb_electricity"],
        "datasets": {
            key: {
                "summary": {name: {f"{metric}_mean": 0.8 for metric in ("roc_auc", "pr_auc", "f1")} for name in ("MLP", "MLP__default", "HistGradientBoosting", "HistGradientBoosting__default")},
                "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
                "tuning": {},
                "seconds": 1.0,
                "attempts": 1,
                "script": key,
            }
            for key in ("tb_credit", "tb_electricity")
        },
        "failed": {},
    }
    markdown, _ = render_report(spec, data, analyze_campaign(spec, data))
    return markdown.split("## Protocol")[1].split("## Results")[0]


class TestWording:
    def test_the_report_names_the_share(self):
        assert "separate tuning set of 50% of the rows" in protocol_of({"iterations": 12, "folds": 3, "share": 0.5})

    def test_the_report_keeps_the_default_share(self):
        assert "separate tuning set of 20% of the rows" in protocol_of({"iterations": 12, "folds": 3})

    def test_a_share_that_is_not_exact_in_floating_point_is_rounded(self):
        assert "tuning set of 29% of the rows" in protocol_of({"iterations": 12, "folds": 3, "share": 0.29})

    def test_the_planning_note_names_the_share(self):
        assert "on a separate 35% tuning set" in planning.tuning_note({"iterations": 8, "folds": 3, "share": 0.35})

    def test_the_planning_note_rounds_a_share_that_is_not_exact_in_floating_point(self):
        assert "on a separate 29% tuning set" in planning.tuning_note({"iterations": 8, "folds": 3, "share": 0.29})

    def test_the_planning_note_keeps_the_default_share(self):
        assert "on a separate 20% tuning set" in planning.tuning_note({"iterations": 8, "folds": 3})


class TestCli:
    def run(self, monkeypatch, *flags):
        seen = []
        monkeypatch.setattr(cli, "execute_campaign", lambda spec, campaign_id, execute, workers, tracker=None: seen.append(spec) or {"id": "abc", "status": "completed", "datasets": {}})
        out = io.StringIO()
        code = cli_main(["run", "--demo", "grinsztajn-2022", *flags], None, out)
        return code, seen, out.getvalue()

    def test_the_flag_sets_the_share(self, monkeypatch):
        code, seen, _ = self.run(monkeypatch, "--tuning", "12", "--tuning-share", "0.5")
        assert code == 0 and seen[0]["tuning"] == {"iterations": 12, "share": 0.5}

    def test_the_deviation_note_names_the_share(self, monkeypatch):
        _, seen, _ = self.run(monkeypatch, "--tuning", "12", "--tuning-share", "0.5")
        assert any("separate 50% tuning set" in note for note in seen[0]["source"]["deviations"])

    def test_without_the_flag_the_share_is_left_out(self, monkeypatch):
        _, seen, _ = self.run(monkeypatch, "--tuning", "12")
        assert seen[0]["tuning"] == {"iterations": 12}

    def test_the_share_needs_a_tuning(self, monkeypatch):
        code, seen, text = self.run(monkeypatch, "--tuning-share", "0.5")
        assert code == 2 and seen == [] and "--tuning-share needs --tuning" in text

    def test_a_zero_share_is_not_silently_ignored(self, monkeypatch):
        monkeypatch.undo()
        out = io.StringIO()
        assert cli_main(["run", "--demo", "grinsztajn-2022", "--tuning", "12", "--tuning-share", "0"], None, out) == 2
        assert "tuning share must be a number" in out.getvalue()

    def test_a_bad_share_is_a_usage_error(self, monkeypatch):
        monkeypatch.undo()
        out = io.StringIO()
        assert cli_main(["run", "--demo", "grinsztajn-2022", "--tuning", "12", "--tuning-share", "0.9"], None, out) == 2
        assert "tuning share must be a number from 0.1 to 0.6" in out.getvalue()
