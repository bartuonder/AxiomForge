import contextlib
import io
import sys
import types
from types import SimpleNamespace

import mlflow
import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification

import app.agents.campaign_planner as planner
import app.campaign.planning as planning
import app.campaign.runner as runner
import app.campaign.tracking as tracking
import app.sandbox.e2b_runner as sandbox
from app.campaign.__main__ import main as cli_main
from app.campaign.analysis import analyze_campaign
from app.campaign.ledger import build_ledger, find
from app.campaign.meta_evidence import discussion_facts, effect_sentences
from app.campaign.planning import assemble_spec, estimate_cost
from app.campaign.protocol import ProtocolError, build_script
from app.campaign.report import render_report, report_issues
from app.campaign.runner import run_dataset
from app.campaign.spec import CampaignSpecError, validate_campaign
from app.campaign.tuning import DEFAULT_FOLDS, DEFAULT_ITERATIONS, SEARCH_SPACES, effective_params, parse_tuning
from app.datasets import DATASETS, benchmark_keys
from app.seeds import SPLIT_SEEDS
from app.tracking.mlflow_logger import parse_dataset_profile, parse_model_results
from app.variants import expected_keys

MODELS = ["RandomForest", "GradientBoosting", "MLP"]
CLAIMS = [{"id": "C1", "statement": "Trees beat the MLP", "metric": "roc_auc", "metrics": ["roc_auc", "pr_auc", "f1"], "subject": ["RandomForest", "GradientBoosting"], "other": ["MLP"]}]
TUNING = {"iterations": 12, "folds": 3}
SPEC = {"title": "T", "models": MODELS, "params": {}, "tuning": TUNING, "claims": CLAIMS, "datasets": benchmark_keys(), "source": {}}
PLAIN = {**SPEC, "tuning": {}}
KEYS = benchmark_keys()
BASE = {"RandomForest": 0.90, "GradientBoosting": 0.91, "MLP": 0.85}


def raw(**changes):
    return {"title": "T", "models": MODELS, "claims": [{"statement": "Trees win", "metric": "roc_auc", "subject": ["RandomForest"], "other": ["MLP"]}], **changes}


class TestSpec:
    def test_no_tuning_gives_an_empty_setting(self):
        assert validate_campaign(raw())["tuning"] == {}

    def test_a_partial_setting_is_completed_with_the_defaults(self):
        assert validate_campaign(raw(tuning={"iterations": 8}))["tuning"] == {"iterations": 8, "folds": DEFAULT_FOLDS}

    def test_tuning_and_listed_parameters_are_exclusive(self):
        with pytest.raises(CampaignSpecError, match="tuning and listed parameters cannot be combined"):
            validate_campaign(raw(tuning={"iterations": 8}, params={"MLP": {"alpha": 0.01}}))

    def test_empty_tuning_may_sit_next_to_parameters(self):
        assert validate_campaign(raw(tuning={}, params={"MLP": {"alpha": 0.01}}))["params"] == {"MLP": {"alpha": 0.01}}

    @pytest.mark.parametrize("tuning", [{"iterations": 2}, {"folds": 9}, {"iterations": "x"}, {"budget": 1}, "yes"])
    def test_a_bad_setting_is_a_spec_error(self, tuning):
        with pytest.raises(CampaignSpecError):
            validate_campaign(raw(tuning=tuning))

    def test_effective_parameters_mark_every_model_as_tuned(self):
        assert effective_params(SPEC) == {model: {"tuned": True} for model in MODELS}

    def test_without_tuning_the_listed_parameters_are_the_effective_ones(self):
        assert effective_params({**PLAIN, "params": {"MLP": {"alpha": 0.01}}}) == {"MLP": {"alpha": 0.01}}
        assert effective_params({"models": MODELS}) == {}


def fake_hub(monkeypatch, key, rows=7000):
    entry = DATASETS[key]
    features, labels = make_classification(n_samples=rows, n_features=10, n_informative=6, class_sep=0.6, random_state=3)
    frame = pd.DataFrame(features, columns=[f"f{index}" for index in range(10)])
    positive = entry["positive"]
    negative = "other" if isinstance(positive, str) else (0 if positive != 0 else 1)
    frame[entry["target"]] = np.where(labels == 1, positive, negative)
    for name in entry["drop"]:
        frame[name] = 0
    monkeypatch.setitem(sys.modules, "datasets", types.SimpleNamespace(load_dataset=lambda *args, **kwargs: types.SimpleNamespace(to_pandas=lambda: frame)))


def run_locally(script):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(compile(script, "campaign", "exec"), {})
    return buffer.getvalue()


class TestProtocol:
    SMALL = ["LogisticRegression", "DecisionTree", "GaussianNB"]

    def test_the_tuning_block_comes_before_the_models_and_each_model_has_its_control(self):
        script = build_script("tb_credit", MODELS, None, SPLIT_SEEDS, TUNING)
        assert script.index("ParameterSampler") < script.index("models = {")
        for model in MODELS:
            assert f'"{model}": with_preprocessing(' in script and f'"{model}__default": with_preprocessing(' in script
            assert f"**tuned['{model}']" in script

    def test_the_script_is_plain_python_without_comments(self):
        import ast

        script = build_script("tb_credit", MODELS, None, SPLIT_SEEDS, TUNING)
        ast.parse(script)
        assert "#" not in script

    def test_without_tuning_the_script_has_no_search(self):
        script = build_script("tb_credit", MODELS, None, SPLIT_SEEDS)
        assert "ParameterSampler" not in script and "tuned[" not in script and "train_size=0.2" not in script
        assert build_script("tb_credit", MODELS, None, SPLIT_SEEDS, {}) == script

    def test_the_control_is_the_library_default_constructor(self):
        script = build_script("tb_credit", ["KNN", "GaussianNB"], None, SPLIT_SEEDS, TUNING)
        assert '"KNN__default": with_preprocessing(KNeighborsClassifier())' in script

    def test_tuning_and_parameters_cannot_be_combined(self):
        with pytest.raises(ProtocolError, match="cannot be combined"):
            build_script("tb_credit", MODELS, {"MLP": {"alpha": 0.01}}, SPLIT_SEEDS, TUNING)

    def test_a_bad_tuning_setting_is_a_protocol_error(self):
        with pytest.raises(ProtocolError, match="whole number from"):
            build_script("tb_credit", MODELS, None, SPLIT_SEEDS, {"iterations": 1})

    def test_each_model_is_built_once_from_its_tuned_parameters(self):
        script = build_script("tb_credit", MODELS, None, SPLIT_SEEDS, TUNING)
        for model in MODELS:
            assert script.count(f'    "{model}": with_preprocessing(') == 1
            assert script.count(f'    "{model}__default": with_preprocessing(') == 1

    def test_the_iterations_and_folds_of_the_setting_reach_the_script(self):
        script = build_script("tb_credit", ["KNN", "GaussianNB"], None, SPLIT_SEEDS, {"iterations": 7, "folds": 4})
        assert "cv=4" in script and "'KNN': 7" in script

    def test_a_tuned_script_runs_and_prints_what_the_parsers_expect(self, monkeypatch):
        fake_hub(monkeypatch, "tb_credit")
        seeds = (1, 2)
        output = run_locally(build_script("tb_credit", self.SMALL, None, seeds, {"iterations": 4, "folds": 3}))
        assert parse_dataset_profile(output)["samples"] == 6000.0
        rows = parse_model_results(output)
        counts = {}
        for row in rows:
            counts[row["model"]] = counts.get(row["model"], 0) + 1
        assert counts == {name: 2 for name in [*self.SMALL, *[f"{model}__default" for model in self.SMALL]]}
        assert [row["model"] for row in rows[:6]] == ["LogisticRegression", "LogisticRegression__default", "DecisionTree", "DecisionTree__default", "GaussianNB", "GaussianNB__default"]
        assert all(row["tn"] + row["fp"] + row["fn"] + row["tp"] == 960 for row in rows)
        tuning = parse_tuning(output)
        assert tuning["rows_tune"] == 1200 and tuning["rows_eval"] == 4800 and set(tuning["models"]) == set(self.SMALL)
        for model, found in tuning["models"].items():
            assert found["cv_roc_auc"] > 0.5 and set(found["params"]) <= set(SEARCH_SPACES[model])

    def test_the_tuned_run_keeps_the_controls_in_the_expected_keys(self):
        keys = expected_keys(MODELS, {"models": MODELS, "params": effective_params(SPEC)})
        assert keys == ["RandomForest", "RandomForest__default", "GradientBoosting", "GradientBoosting__default", "MLP", "MLP__default"]


def fake_output(dataset, tuned=True, drop_controls=False):
    lines = [f"dataset={dataset} samples=6000 features=10 negative_ratio=0.50 positive_ratio=0.50"]
    if tuned:
        lines.append("tuning rows_tune=1200 rows_eval=4800")
        lines.append('tuned model=RandomForest cv_roc_auc=0.8800 params={"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 2}')
        lines.append('tuned model=GradientBoosting cv_roc_auc=0.8900 params={"n_estimators": 100, "learning_rate": 0.1, "max_depth": 3}')
        lines.append('tuned model=MLP cv_roc_auc=0.8400 params={"hidden_layer_sizes": [100], "alpha": 0.001, "learning_rate_init": 0.003}')
    keys = expected_keys(MODELS, {"models": MODELS, "params": effective_params(SPEC if tuned else PLAIN)})
    for _ in SPLIT_SEEDS:
        for key in keys:
            if drop_controls and key.endswith("__default"):
                continue
            value = BASE[key.split("__")[0]] - (0.01 if key.endswith("__default") else 0.0)
            lines.append(f"model={key} accuracy={value:.4f} f1={value - 0.05:.4f} roc_auc={value:.4f} pr_auc={value - 0.02:.4f} train_seconds=0.1 tn=1 fp=1 fn=1 tp=1")
    return "\n".join(lines)


class TestRunner:
    def test_a_tuned_spec_runs_with_the_longer_sandbox_by_default(self, monkeypatch):
        used = []
        monkeypatch.setattr(runner, "run_tuned_classification", lambda script, schema: used.append("tuned") or fake_output("tb_credit"))
        monkeypatch.setattr(runner, "run_classification", lambda script, schema: used.append("plain") or fake_output("tb_credit", tuned=False))
        run_dataset("tb_credit", SPEC)
        run_dataset("tb_credit", PLAIN)
        assert used == ["tuned", "plain"]

    def test_an_explicit_executor_wins_over_the_default(self, monkeypatch):
        monkeypatch.setattr(runner, "run_tuned_classification", lambda script, schema: pytest.fail("used the default"))
        assert run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit"))["status"] == "finished"

    def test_the_result_carries_the_found_configurations(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit"))
        assert result["tuning"]["rows_eval"] == 4800
        assert result["tuning"]["models"]["RandomForest"]["params"] == {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 2}

    def test_an_untuned_run_has_an_empty_tuning_record(self):
        assert run_dataset("tb_credit", PLAIN, lambda script, schema: fake_output("tb_credit", tuned=False))["tuning"] == {}

    def test_every_model_gets_a_tuned_versus_default_effect(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit"))
        assert {row["model"] for row in result["parameter_effects"]} == set(MODELS)
        assert all(row["params"] == {"tuned": True} and row["mean_difference"] > 0 for row in result["parameter_effects"])

    def test_missing_controls_fail_the_dataset(self):
        result = run_dataset("tb_credit", SPEC, lambda script, schema: fake_output("tb_credit", drop_controls=True), attempts=1)
        assert result["status"] == "failed" and "incomplete output" in result["error"]

    def test_the_script_sent_to_the_sandbox_contains_the_search(self):
        sent = []
        run_dataset("tb_credit", SPEC, lambda script, schema: sent.append(script) or fake_output("tb_credit"))
        assert "ParameterSampler" in sent[0]


def outcome(keys=KEYS, spec=SPEC, equal_default=False, worse=False):
    data = {"order": list(keys), "datasets": {}, "failed": {}}
    for index, key in enumerate(keys):
        summary = {}
        for model in MODELS:
            tuned = BASE[model] + 0.001 * index
            summary[model] = {f"{metric}_mean": tuned for metric in ("roc_auc", "pr_auc", "f1")}
            summary[f"{model}__default"] = {f"{metric}_mean": tuned if equal_default else (tuned + 0.01 + 0.0005 * index if worse else tuned - 0.01 - 0.0005 * index) for metric in ("roc_auc", "pr_auc", "f1")}
        data["datasets"][key] = {
            "summary": summary,
            "profile": {"dataset": key, "samples": 6000.0, "features": 10.0, "negative_ratio": 0.5, "positive_ratio": 0.5},
            "descriptors": {},
            "provenance": {},
            "tuning": parse_tuning(fake_output(key)) if spec.get("tuning") else {},
            "seconds": 1.0,
            "attempts": 1,
            "script": f"script {key}",
        }
    return data


def build(spec=SPEC, **kwargs):
    data = outcome(spec=spec, **kwargs)
    analysis = analyze_campaign(spec, data)
    markdown, ledger = render_report(spec, data, analysis)
    return data, analysis, ledger, markdown


class TestAnalysisLedgerReport:
    def test_every_tuned_model_is_compared_with_its_default(self):
        _, analysis, _, _ = build()
        assert {row["model"] for row in analysis["parameter_effects"]} == set(MODELS) and len(analysis["parameter_effects"]) == 9
        assert all(row["significant"] and row["params"] == {"tuned": True} for row in analysis["parameter_effects"])

    def test_the_ledger_keeps_the_found_configurations(self):
        _, _, ledger, _ = build()
        entry = find(ledger, "dataset", "tb_credit")
        assert entry["tuning"]["models"]["MLP"]["params"]["alpha"] == 0.001 and entry["tuning"]["rows_tune"] == 1200

    def test_an_untuned_ledger_has_an_empty_tuning_record(self):
        _, _, ledger, _ = build(PLAIN, equal_default=True)
        assert find(ledger, "dataset", "tb_credit")["tuning"] == {}

    def protocol(self, markdown):
        return markdown.split("## Protocol")[1].split("## Results")[0]

    def test_the_protocol_describes_the_search(self):
        _, _, _, markdown = build()
        assert (
            "Models and configuration: every model was tuned on each dataset by a random search of 12 configurations "
            "(3-fold cross-validated ROC-AUC on a separate tuning set of 20% of the rows that was excluded from evaluation) "
            "and also ran once with library defaults as its control. Every other argument is fixed by the protocol."
        ) in self.protocol(markdown)
        assert "ran with the listed parameters" not in markdown

    def test_the_datasets_show_how_many_rows_were_evaluated(self):
        _, _, ledger, markdown = build()
        entry = find(ledger, "dataset", "tb_credit")
        assert f"- tb_credit: inria-soda/tabular-benchmark (clf_num_credit), 6000 rows (4800 used for evaluation), 10 features [{entry['id']}]" in markdown

    def test_the_selected_configurations_are_listed_per_dataset_with_a_reference(self):
        _, _, ledger, markdown = build()
        entry = find(ledger, "dataset", "tb_credit")
        block = self.protocol(markdown)
        assert "Selected configurations (best cross-validated ROC-AUC on the tuning set):" in block
        assert f"- tb_credit: RandomForest (n_estimators=200, max_depth=10, min_samples_leaf=2); GradientBoosting (n_estimators=100, learning_rate=0.1, max_depth=3); MLP (hidden_layer_sizes=[100], alpha=0.001, learning_rate_init=0.003) [{entry['id']}]" in block

    def test_an_untuned_report_has_no_selected_configurations(self):
        _, _, _, markdown = build(PLAIN, equal_default=True)
        assert "Selected configurations" not in markdown and "used for evaluation" not in markdown

    def test_the_effects_are_stated_as_tuning(self):
        _, _, _, markdown = build()
        assert "RandomForest tuned by random search scored higher than RandomForest with default parameters on ROC-AUC on 9 of 9 datasets" in markdown
        assert "with the listed parameters" not in markdown

    def test_a_missing_effect_is_stated_as_no_effect_of_tuning(self):
        _, _, _, markdown = build(equal_default=True)
        assert "No significant effect of tuning of RandomForest on ROC-AUC across datasets was found" in markdown
        assert "the listed parameters of" not in markdown

    def test_the_folds_and_the_iterations_come_from_the_setting(self):
        _, _, _, markdown = build({**SPEC, "tuning": {"iterations": 8, "folds": 5}})
        assert "random search of 8 configurations (5-fold cross-validated ROC-AUC" in self.protocol(markdown)

    def test_the_tuning_share_comes_from_the_protocol_constant(self, monkeypatch):
        import app.campaign.report as report_module

        monkeypatch.setattr(report_module, "TUNING_SHARE", 0.3)
        _, _, _, markdown = build()
        assert "separate tuning set of 30% of the rows" in markdown

    def test_a_search_that_kept_the_defaults_is_listed_as_defaults(self):
        data = outcome()
        data["datasets"]["tb_credit"]["tuning"]["models"]["MLP"]["params"] = {}
        analysis = analyze_campaign(SPEC, data)
        markdown, _ = render_report(SPEC, data, analysis)
        assert "MLP (defaults) [" in markdown

    def test_a_listed_parameter_campaign_keeps_its_original_wording(self):
        spec = {**PLAIN, "params": {"MLP": {"alpha": 0.01}}}
        data, analysis, ledger, markdown = build(spec, equal_default=True)
        assert "MLP ran with the listed parameters" in markdown or "ran with the listed parameters" in markdown
        assert "No significant effect of the listed parameters of MLP" in markdown

    def test_the_limitation_names_the_small_search(self):
        _, _, _, markdown = build()
        assert "Tuning used a small random search over fixed discrete grids with one tuning set per dataset; a larger search could change the ranking." in markdown
        assert "the listed parameters are single configurations" not in markdown

    def test_the_traceability_check_is_clean(self):
        _, _, ledger, markdown = build()
        assert report_issues(markdown, ledger) == []

    def test_significant_effects_become_discussion_facts(self):
        _, analysis, ledger, _ = build()
        sentences = effect_sentences(analysis, ledger)
        entry = find(ledger, "effect", "RandomForest:roc_auc")
        assert f"RandomForest tuned by random search scored higher than RandomForest with library defaults on ROC-AUC across the datasets [{entry['id']}]." in sentences
        assert len(sentences) == 9

    def test_a_tuning_that_lowered_the_score_is_stated_as_lower(self):
        _, analysis, ledger, _ = build(worse=True)
        sentences = effect_sentences(analysis, ledger)
        assert sentences and all(" scored lower than " in sentence and " scored higher than " not in sentence for sentence in sentences)

    def test_the_effects_reach_the_discussion_facts(self):
        _, analysis, ledger, _ = build()
        facts = discussion_facts(analysis, ledger)
        assert all(sentence in facts for sentence in effect_sentences(analysis, ledger))

    def test_a_listed_parameter_effect_keeps_its_wording_in_the_facts(self):
        spec = {**PLAIN, "params": {"MLP": {"alpha": 0.01}}}
        _, analysis, ledger, _ = build(spec)
        assert any("MLP with the listed parameters scored higher than MLP with library defaults" in sentence for sentence in effect_sentences(analysis, ledger))

    def test_no_significant_effect_gives_no_facts(self):
        _, analysis, ledger, _ = build(equal_default=True)
        assert effect_sentences(analysis, ledger) == [] and effect_sentences({}, []) == []


class TestPlanning:
    def test_a_tuned_spec_has_a_deviation_note_instead_of_the_no_search_one(self):
        notes = planning.deviation_notes(benchmark_keys(), {}, [], TUNING)
        assert notes[0] == (
            "Each model was tuned on every dataset with a random search of 12 configurations from a small fixed grid "
            "(3-fold cross-validated ROC-AUC on a separate 20% tuning set), a much smaller search than a full study would run; the remaining rows were used for evaluation."
        )
        assert not any("No hyperparameter search" in note for note in notes)

    def test_without_tuning_the_notes_are_unchanged(self):
        assert planning.deviation_notes(benchmark_keys(), {}, [])[0].startswith("No hyperparameter search")
        assert planning.deviation_notes(benchmark_keys(), {}, [], {})[0].startswith("No hyperparameter search")

    def test_the_assembled_spec_carries_the_tuning(self):
        spec = assemble_spec("T", MODELS, [CLAIMS[0]], {}, tuning=TUNING)
        assert spec["tuning"] == TUNING and spec["source"]["deviations"][0].startswith("Each model was tuned")

    def test_an_untuned_assembled_spec_has_an_empty_setting(self):
        assert assemble_spec("T", MODELS, [CLAIMS[0]], {})["tuning"] == {}

    def test_tuning_and_parameters_together_are_refused(self):
        with pytest.raises(CampaignSpecError, match="cannot be combined"):
            assemble_spec("T", MODELS, [CLAIMS[0]], {}, params={"MLP": {"alpha": 0.01}}, tuning=TUNING)

    def test_the_tuned_estimate_adds_the_search_and_the_controls(self):
        plain = estimate_cost({"models": MODELS, "datasets": list("abcdefghi")})
        tuned = estimate_cost({"models": MODELS, "tuning": TUNING, "datasets": list("abcdefghi")})
        assert plain["seconds_per_dataset"] == 20 + 14 * 3 + 18
        assert tuned["seconds_per_dataset"] == 20 + 14 * 6 + 18 + int(36 * (0.6 + 1.2 + 1.5) / 2)
        assert tuned["model_runs"] == 6 and plain["model_runs"] == 3
        assert tuned["estimated_seconds"] == 3 * tuned["seconds_per_dataset"]

    def test_more_iterations_cost_more_time(self):
        small = estimate_cost({"models": MODELS, "tuning": {"iterations": 4, "folds": 3}, "datasets": ["a"]})
        large = estimate_cost({"models": MODELS, "tuning": {"iterations": 40, "folds": 5}, "datasets": ["a"]})
        assert large["seconds_per_dataset"] > small["seconds_per_dataset"]

    def test_an_unknown_model_uses_the_default_fit_time(self):
        cost = estimate_cost({"models": ["KNN", "GaussianNB"], "tuning": {"iterations": 10, "folds": 3}, "datasets": ["a"]})
        assert cost["seconds_per_dataset"] == 20 + 14 * 4 + int(30 * 0.3 * 2 / 2)


class TestPlanner:
    ABSTRACT = "We show that tree-based models remain state-of-the-art on medium-sized data, even without accounting for their superior speed."
    SOURCES = [{"title": "Why trees win", "abstract": ABSTRACT, "url": ""}]

    def reply(self, **changes):
        import json

        candidate = {
            "title": "Trees against networks",
            "source_index": 1,
            "pool": "benchmark",
            "claims": [{"statement": "Trees beat the MLP", "metrics": ["roc_auc"], "subject": ["RandomForest"], "other": ["MLP"], "source_quote": "tree-based models remain state-of-the-art on medium-sized data"}],
            **changes,
        }
        return json.dumps({"unsupported": "", "candidates": [candidate]})

    @pytest.fixture
    def llm(self, monkeypatch):
        replies = []
        monkeypatch.setattr(planner, "OPENAI_API_KEY", "key")
        monkeypatch.setattr(planner, "_complete", lambda user: replies.pop(0))
        return replies

    def test_a_tuned_candidate_gets_the_default_search(self, llm):
        llm.append(self.reply(tuned=True))
        spec = planner.run_campaign_planner("q", self.SOURCES)[0]["spec"]
        assert spec["tuning"] == {"iterations": DEFAULT_ITERATIONS, "folds": DEFAULT_FOLDS}

    @pytest.mark.parametrize("tuned", [False, None])
    def test_an_untuned_or_silent_candidate_has_no_search(self, llm, tuned):
        llm.append(self.reply(tuned=tuned) if tuned is not None else self.reply())
        assert planner.run_campaign_planner("q", self.SOURCES)[0]["spec"]["tuning"] == {}

    def test_a_non_boolean_flag_is_refused(self, llm):
        for _ in range(planner.MAX_PLAN_ATTEMPTS):
            llm.append(self.reply(tuned="yes"))
        with pytest.raises(RuntimeError, match="tuned must be true or false"):
            planner.run_campaign_planner("q", self.SOURCES)

    def test_the_estimate_of_a_tuned_candidate_is_larger(self, llm):
        llm.append(self.reply(tuned=True))
        llm.append(self.reply())
        tuned = planner.run_campaign_planner("q", self.SOURCES)[0]["estimate"]["estimated_seconds"]
        plain = planner.run_campaign_planner("q", self.SOURCES)[0]["estimate"]["estimated_seconds"]
        assert tuned > plain

    def test_the_prompt_explains_when_to_tune(self):
        assert "tuned (true only when the user asks for tuned models or the source tuned its models" in planner.SYSTEM_PROMPT


class TestSandbox:
    class Box:
        created = []
        timeouts = []

        def __init__(self):
            self.files = SimpleNamespace(write=lambda path, text: None)

        @classmethod
        def create(cls, api_key, timeout):
            cls.created.append(timeout)
            return cls()

        def run_code(self, code, timeout):
            self.timeouts.append(timeout)
            return SimpleNamespace(error=None, logs=SimpleNamespace(stdout=["ok"]))

        def kill(self):
            return None

    @pytest.fixture(autouse=True)
    def fake(self, monkeypatch):
        self.Box.created.clear()
        self.Box.timeouts.clear()
        monkeypatch.setattr(sandbox, "Sandbox", self.Box)
        monkeypatch.setattr(sandbox, "E2B_API_KEY", "key")

    def test_the_normal_run_keeps_the_short_limits(self):
        assert sandbox.run_classification("x = 1", "a:float, b:int") == "ok"
        assert self.Box.created == [sandbox.SANDBOX_LIFETIME_SECONDS] and self.Box.timeouts[-1] == sandbox.RUN_TIMEOUT_SECONDS

    def test_the_tuned_run_gets_a_longer_box_and_run_limit(self):
        assert sandbox.run_tuned_classification("x = 1", "a:float, b:int") == "ok"
        assert self.Box.created == [1100] and self.Box.timeouts[-1] == 900
        assert (sandbox.TUNED_RUN_TIMEOUT_SECONDS, sandbox.TUNED_LIFETIME_SECONDS) == (900, 1100)

    def test_the_box_outlives_the_run(self):
        assert sandbox.TUNED_LIFETIME_SECONDS > sandbox.TUNED_RUN_TIMEOUT_SECONDS + sandbox.INSTALL_TIMEOUT_SECONDS

    def test_explicit_limits_are_honoured(self):
        sandbox.run_classification("x = 1", "a:float, b:int", run_timeout=11, lifetime=22)
        assert self.Box.created == [22] and self.Box.timeouts[-1] == 11


class TestCli:
    def test_the_tuning_flag_puts_the_iterations_into_the_specification(self, monkeypatch):
        import app.campaign.__main__ as cli

        seen = []
        monkeypatch.setattr(cli, "execute_campaign", lambda spec, campaign_id, execute, workers, tracker=None: seen.append(spec) or {"id": "abc", "status": "completed", "datasets": {}})
        out = io.StringIO()
        cli_main(["run", "--demo", "grinsztajn-2022", "--tuning", "8"], None, out)
        cli_main(["run", "--demo", "grinsztajn-2022"], None, out)
        assert seen[0]["tuning"] == {"iterations": 8} and "tuning" not in seen[1]

    def test_the_default_executor_is_left_to_the_runner(self, monkeypatch):
        import app.campaign.__main__ as cli

        seen = []
        monkeypatch.setattr(cli, "execute_campaign", lambda spec, campaign_id, execute, workers, tracker=None: seen.append(execute) or {"id": "abc", "status": "completed", "datasets": {}})
        cli_main(["run", "--demo", "grinsztajn-2022"], None, io.StringIO())
        assert seen == [None]


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mlflow_tuned")
    patch = pytest.MonkeyPatch()
    patch.chdir(folder)
    uri = f"sqlite:///{(folder / 'mlflow.db').as_posix()}"
    patch.setattr(tracking, "MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri
    patch.undo()


class TestTracking:
    def test_the_found_configurations_are_logged_per_dataset(self, store):
        data, analysis, ledger, markdown = build()
        run = mlflow.get_run(tracking.log_campaign("tuned", SPEC, data, analysis, markdown, ledger, "completed"))
        experiment = mlflow.get_experiment_by_name(tracking.EXPERIMENT)
        nested = mlflow.search_runs(experiment_ids=[experiment.experiment_id], filter_string=f"tags.mlflow.parentRunId = '{run.info.run_id}'")
        first = nested[nested["tags.mlflow.runName"] == "tb_credit"].iloc[0]
        assert first["params.tuned/MLP"] == '{"hidden_layer_sizes": [100], "alpha": 0.001, "learning_rate_init": 0.003}'
        assert first["metrics.tuned/RandomForest/cv_roc_auc"] == pytest.approx(0.88)

    def test_an_untuned_campaign_logs_no_tuned_parameters(self, store):
        data, analysis, ledger, markdown = build(PLAIN, equal_default=True)
        run = mlflow.get_run(tracking.log_campaign("untuned", PLAIN, data, analysis, markdown, ledger, "completed"))
        experiment = mlflow.get_experiment_by_name(tracking.EXPERIMENT)
        nested = mlflow.search_runs(experiment_ids=[experiment.experiment_id], filter_string=f"tags.mlflow.parentRunId = '{run.info.run_id}'")
        assert not any(column.startswith("params.tuned/") for column in nested.columns)
