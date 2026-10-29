import json

import numpy as np
import pytest

import app.research.session as session
from app.datasets import research_pool
from app.research import generate, protocol
from app.research.protocol import ProtocolError

POOL = research_pool()
MODELS = ["RandomForest", "ExtraTrees", "MLP", "DecisionTree"]


def make_runner(abilities, tuned_abilities=None, noise=0.002, seed=0, fail=(), calls=None, shift=None, fail_tuned=()):
    generator = np.random.default_rng(seed)
    base = {dataset: generator.uniform(0.6, 0.9) for dataset in POOL}
    extra = {dataset: {model: generator.normal(0, noise) for model in abilities} for dataset in POOL}
    default_extra = {dataset: {model: generator.normal(0, noise) for model in abilities} for dataset in POOL}

    def runner(spec, execute, workers, should_stop=None, on_update=None):
        tuned = bool(spec.get("tuning"))
        if calls is not None:
            calls.append({"datasets": list(spec["datasets"]), "tuned": tuned, "models": list(spec["models"])})
        levels = (tuned_abilities if tuned and tuned_abilities else abilities)
        datasets, failed = {}, {}
        for dataset in spec["datasets"]:
            if on_update:
                on_update(dataset, {"status": "running"})
            if dataset in fail or (tuned and dataset in fail_tuned):
                failed[dataset] = {"error": "boom", "attempts": 2}
                if on_update:
                    on_update(dataset, {"status": "failed", "error": "boom", "attempts": 2})
                continue
            record = {}
            for model in spec["models"]:
                score = base[dataset] + levels[model] + extra[dataset][model] + (shift(dataset) if shift else 0.0)
                record[model] = {f"{metric}_mean": float(score) for metric in ("roc_auc", "pr_auc", "f1")}
                if tuned:
                    default = base[dataset] + abilities[model] + default_extra[dataset][model]
                    record[f"{model}__default"] = {f"{metric}_mean": float(default) for metric in ("roc_auc", "pr_auc", "f1")}
            datasets[dataset] = {"summary": record}
            if on_update:
                on_update(dataset, {"status": "finished", "attempts": 1})
        return {"order": list(spec["datasets"]), "datasets": datasets, "failed": failed}

    return runner


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    return tmp_path / "research"


@pytest.fixture(autouse=True)
def no_history(monkeypatch, request):
    if request.node.cls is not None and request.node.cls.__name__ in {"TestNovelty", "TestReport"}:
        return
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())


def config(**changes):
    base = {"id": "s1", "models": MODELS, "explore": 6, "seed": 0, "tuning": None, "per_stage": 8}
    return session.SessionConfig(**{**base, **changes})


def planted():
    return {"RandomForest": 0.05, "ExtraTrees": 0.045, "MLP": 0.0, "DecisionTree": -0.03}


class TestConfig:
    def test_the_defaults(self):
        item = session.SessionConfig(id="s", models=MODELS)
        assert item.explore == 6 and item.seed == 0 and item.tuning is None and item.per_stage == 8
        assert item.effect == generate.DEFAULT_EFFECT and item.consistency == generate.DEFAULT_CONSISTENCY
        assert item.tuning_trigger == generate.TUNING_TRIGGER and item.pool == POOL

    def test_the_id_must_be_a_safe_name(self):
        for bad in ["", "../x", "a b", "x" * 80, ".hidden"]:
            with pytest.raises(ProtocolError, match="id"):
                session.SessionConfig(id=bad, models=MODELS)

    def test_at_least_two_different_models_are_needed(self):
        with pytest.raises(ProtocolError, match="models"):
            session.SessionConfig(id="s", models=["MLP"])
        with pytest.raises(ProtocolError, match="models"):
            session.SessionConfig(id="s", models=["MLP", "MLP"])

    def test_unknown_models_are_refused(self):
        with pytest.raises(ProtocolError, match="unknown"):
            session.SessionConfig(id="s", models=["MLP", "Nope"])

    def test_unknown_datasets_are_refused(self):
        with pytest.raises(ProtocolError, match="unknown"):
            session.SessionConfig(id="s", models=MODELS, pool=POOL + ["nope"])

    def test_the_tuning_iterations_follow_the_campaign_rules(self):
        with pytest.raises(ProtocolError, match="tuning"):
            session.SessionConfig(id="s", models=MODELS, tuning=1)

    def test_it_is_plain_json(self):
        json.dumps(config().to_dict())


class TestRun:
    def test_a_planted_effect_is_found_and_confirmed(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert state["status"] == "completed"
        confirmed = {item["id"] for item in state["confirmations"] if item["status"] == "confirmed"}
        statements = {item["id"]: item["statement"] for item in state["hypotheses"]}
        assert confirmed and any("RandomForest scores higher than MLP" in statements[key] for key in confirmed)

    def test_the_split_the_budget_and_the_alpha_are_recorded(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert len(state["explore"]) == 6 and len(state["confirm"]) == 10
        assert state["budget"] == protocol.max_hypotheses(10) == 25 and state["alpha"] == protocol.ALPHA
        assert set(state["explore"]) | set(state["confirm"]) == set(POOL)

    def test_every_dataset_of_the_pool_is_run_in_each_stage(self):
        calls = []
        session.run_session(config(), runner=make_runner(planted(), calls=calls))
        assert len(calls) == 1 and calls[0]["datasets"] == POOL and calls[0]["tuned"] is False and calls[0]["models"] == MODELS

    def test_the_generator_only_ever_sees_exploration_datasets(self, monkeypatch):
        seen = []
        original = generate.propose

        def spy(view, *args, **kwargs):
            seen.append(set(view.per_dataset))
            return original(view, *args, **kwargs)

        monkeypatch.setattr(generate, "propose", spy)
        state = session.run_session(config(), runner=make_runner(planted()))
        assert seen and all(names == set(state["explore"]) for names in seen)

    def test_the_hypotheses_are_saved_before_any_confirmation_result_is_read(self, monkeypatch, root):
        snapshots = []
        original = protocol.confirm

        def spy(registry, results):
            saved = json.loads((root / "s1" / "session.json").read_text(encoding="utf-8"))
            snapshots.append({"saved": [item["digest"] for item in saved["hypotheses"]], "registry": [item["digest"] for item in registry.records], "confirmations": saved.get("confirmations")})
            return original(registry, results)

        monkeypatch.setattr(protocol, "confirm", spy)
        session.run_session(config(), runner=make_runner(planted()))
        assert len(snapshots) == 1 and snapshots[0]["saved"] == snapshots[0]["registry"] and snapshots[0]["saved"]
        assert not snapshots[0]["confirmations"]

    def test_the_registered_hypotheses_do_not_depend_on_the_confirmation_results(self):
        first = session.run_session(config(id="a"), runner=make_runner(planted(), seed=0))
        confirm = set(first["confirm"])
        second = session.run_session(config(id="b"), runner=make_runner(planted(), seed=0, shift=lambda dataset: -0.2 if dataset in confirm else 0.0))
        assert [item["digest"] for item in first["hypotheses"]] == [item["digest"] for item in second["hypotheses"]]

    def test_a_different_confirmation_result_changes_the_verdict_not_the_hypothesis(self):
        base = session.run_session(config(id="a"), runner=make_runner(planted(), seed=0))
        confirm = set(base["confirm"])
        flipped = {"RandomForest": 0.0, "ExtraTrees": 0.0, "MLP": 0.05, "DecisionTree": 0.05}

        def runner(spec, execute, workers, **_):
            outcome = make_runner(planted(), seed=0)(spec, execute, workers)
            other = make_runner(flipped, seed=0)(spec, execute, workers)
            for dataset in confirm:
                outcome["datasets"][dataset] = other["datasets"][dataset]
            return outcome

        second = session.run_session(config(id="b"), runner=runner)
        assert [item["digest"] for item in base["hypotheses"]] == [item["digest"] for item in second["hypotheses"]]
        assert [item["status"] for item in base["confirmations"]] != [item["status"] for item in second["confirmations"]]
        assert any(item["status"] == "reversed" for item in second["confirmations"])

    def test_the_number_of_hypotheses_never_exceeds_the_budget(self):
        state = session.run_session(config(per_stage=100), runner=make_runner(planted()))
        assert len(state["hypotheses"]) <= state["budget"]

    def test_the_count_per_stage_is_respected(self):
        state = session.run_session(config(per_stage=2), runner=make_runner(planted()))
        assert len(state["hypotheses"]) == 2

    def test_the_largest_exploration_effects_are_proposed_first(self):
        state = session.run_session(config(per_stage=1), runner=make_runner(planted()))
        assert state["hypotheses"][0]["evidence"]["median_difference"] == max(item["evidence"]["median_difference"] for item in state["hypotheses"])
        assert "RandomForest" in state["hypotheses"][0]["statement"] or "ExtraTrees" in state["hypotheses"][0]["statement"]

    def test_the_exploration_estimate_is_labelled_and_kept_apart_from_the_confirmation(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert all(item["evidence"]["scope"] == "exploration" for item in state["hypotheses"])
        assert all("median_difference" in item for item in state["confirmations"])


class TestRecordedSettings:
    def test_the_seed_and_the_explore_size_decide_the_split(self):
        state = session.run_session(config(seed=3, explore=7), runner=make_runner(planted()))
        assert (state["explore"], state["confirm"]) == protocol.split_pool(POOL, 7, 3)

    def test_the_alpha_decides_the_budget_and_is_recorded(self):
        state = session.run_session(config(alpha=0.01), runner=make_runner(planted()))
        assert state["alpha"] == 0.01 and state["budget"] == protocol.max_hypotheses(10, 0.01)

    def test_the_effect_threshold_reaches_the_generator(self):
        assert session.run_session(config(effect=0.2), runner=make_runner(planted()))["hypotheses"] == []

    def test_the_consistency_threshold_reaches_the_generator(self):
        assert session.run_session(config(consistency=1.01), runner=make_runner(planted()))["hypotheses"] == []

    def test_a_finished_session_records_when_it_finished(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert state["finished"].endswith("+00:00") and state["created"].endswith("+00:00")

    def test_the_session_is_saved_before_the_first_stage_runs(self, root):
        seen = []

        def runner(spec, execute, workers, **_):
            saved = json.loads((root / "s1" / "session.json").read_text(encoding="utf-8"))
            seen.append({"status": saved["status"], "budget": saved["budget"]})
            return make_runner(planted())(spec, execute, workers)

        session.run_session(config(alpha=0.01), runner=runner)
        assert seen == [{"status": "running", "budget": protocol.max_hypotheses(10, 0.01)}]

    def test_a_smaller_confirmation_set_lowers_the_budget(self):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        state = session.run_session(config(id="q"), runner=make_runner(planted(), fail=(probe["confirm"][0],)))
        assert state["budget"] == protocol.max_hypotheses(9) == 12

    def test_the_budget_never_drops_below_what_is_already_registered(self):
        tuned = {"RandomForest": 0.05, "ExtraTrees": 0.05, "MLP": 0.045, "DecisionTree": -0.01}
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = tuple(probe["confirm"][:3])
        state = session.run_session(config(id="q", tuning=12, per_stage=30), runner=make_runner(planted(), tuned_abilities=tuned, fail_tuned=failed))
        registered = len(state["hypotheses"])
        assert state["status"] == "completed" and registered > protocol.max_hypotheses(7)
        assert state["budget"] == registered
        assert {item["stage"] for item in state["hypotheses"]} == {"default"}


class TestGenerator:
    def test_the_default_generator_is_the_rule_based_one(self):
        assert session.SessionConfig(id="s", models=MODELS).generator == "rules"
        assert session.run_session(config(), runner=make_runner(planted()))["generator"] == "rules"

    def test_the_generators_and_the_default_model_are_fixed(self):
        assert session.GENERATORS == ("rules", "llm")
        assert session.SessionConfig(id="s", models=MODELS).llm_model == "gpt-4o"

    def test_an_unknown_generator_is_refused(self):
        with pytest.raises(ProtocolError, match="generator"):
            session.SessionConfig(id="s", models=MODELS, generator="oracle")

    def test_a_custom_generator_proposes_instead_of_the_rules(self):
        def custom(view, registry, stage, count, effect, consistency, known):
            item = protocol.Hypothesis("H1", ("MLP",), ("DecisionTree",), stage, "roc_auc", "custom claim", {"median_difference": 0.0, "wins": 0, "datasets": 6, "scope": "exploration"})
            return [item], [{"statement": "x", "reason": "because"}]

        state = session.run_session(config(), runner=make_runner(planted()), generator=custom)
        assert [item["statement"] for item in state["hypotheses"]] == ["custom claim"]
        assert state["generator"] == "custom" and state["skipped"] == [{"stage": "default", "statement": "x", "reason": "because"}]

    def test_a_custom_generator_receives_the_view_the_registry_and_the_settings(self):
        seen = {}

        def custom(view, registry, stage, count, effect, consistency, known):
            seen.update(datasets=set(view.per_dataset), stage=stage, count=count, effect=effect, consistency=consistency, remaining=registry.remaining)
            return [], []

        state = session.run_session(config(per_stage=3, effect=0.02, consistency=0.9), runner=make_runner(planted()), generator=custom)
        assert seen == {"datasets": set(state["explore"]), "stage": "default", "count": 3, "effect": 0.02, "consistency": 0.9, "remaining": 25}

    def test_the_protocol_checks_a_generator_that_proposes_nonsense_at_confirmation_time(self):
        def reckless(view, registry, stage, count, effect, consistency, known):
            return [protocol.Hypothesis("H1", ("MLP",), ("RandomForest",), stage, "roc_auc", "reckless", {"median_difference": 0.5, "wins": 6, "datasets": 6, "scope": "exploration"})], []

        state = session.run_session(config(), runner=make_runner(planted()), generator=reckless)
        assert state["confirmations"][0]["status"] == "reversed"

    def test_the_llm_generator_is_built_from_the_configured_model(self, monkeypatch):
        built = []
        monkeypatch.setattr(session.llm_generator, "make_complete", lambda model: built.append(model) or (lambda prompt: '{"hypotheses": []}'))
        state = session.run_session(config(generator="llm", llm_model="gpt-test"), runner=make_runner(planted()))
        assert built == ["gpt-test"] and state["generator"] == "llm" and state["hypotheses"] == []

    def test_a_language_model_that_proposes_a_real_pair_gets_it_registered_and_confirmed(self, monkeypatch):
        reply = '{"hypotheses": [{"higher": "RandomForest", "lower": "MLP", "rationale": "forests are strong"}]}'
        monkeypatch.setattr(session.llm_generator, "make_complete", lambda model: lambda prompt: reply)
        state = session.run_session(config(generator="llm"), runner=make_runner(planted()))
        assert [item["statement"] for item in state["hypotheses"]] == [generate.statement("RandomForest", "MLP", "roc_auc", "default")]
        assert state["hypotheses"][0]["evidence"]["rationale"] == "forests are strong" and state["confirmations"][0]["status"] == "confirmed"

    def test_the_report_names_the_generator(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert "Hypothesis generator: rules." in session.render_report(state)

    def test_the_report_names_the_model_of_an_llm_generator(self, monkeypatch):
        monkeypatch.setattr(session.llm_generator, "make_complete", lambda model: lambda prompt: '{"hypotheses": []}')
        state = session.run_session(config(generator="llm", llm_model="gpt-test"), runner=make_runner(planted()))
        assert "Hypothesis generator: llm (gpt-test)." in session.render_report(state)


class TestStages:
    def tuned(self):
        return {"RandomForest": 0.05, "ExtraTrees": 0.05, "MLP": 0.045, "DecisionTree": -0.01}

    def test_without_tuning_only_the_default_stage_runs(self):
        calls = []
        session.run_session(config(), runner=make_runner(planted(), calls=calls))
        assert [call["tuned"] for call in calls] == [False]

    def test_a_large_exploration_effect_triggers_the_tuned_stage(self):
        calls = []
        state = session.run_session(config(tuning=12), runner=make_runner(planted(), self.tuned(), calls=calls))
        assert [call["tuned"] for call in calls] == [False, True]
        assert {item["stage"] for item in state["hypotheses"]} == {"default", "tuned"}
        assert [item["name"] for item in state["stages"]] == ["default", "tuned"]

    def test_small_exploration_effects_skip_the_tuned_stage(self):
        calls = []
        state = session.run_session(config(tuning=12), runner=make_runner({"RandomForest": 0.011, "ExtraTrees": 0.0, "MLP": 0.0, "DecisionTree": 0.0}, calls=calls))
        assert [call["tuned"] for call in calls] == [False] and {item["stage"] for item in state["hypotheses"]} == {"default"}

    def test_the_tuned_stage_includes_the_tuning_effects(self):
        state = session.run_session(config(tuning=12, per_stage=30), runner=make_runner(planted(), self.tuned()))
        tuned = [item for item in state["hypotheses"] if item["stage"] == "tuned"]
        assert any("__default" in item["statement"] for item in tuned)

    def test_the_tuning_iterations_reach_the_stage_spec(self, monkeypatch):
        specs = []
        original = make_runner(planted(), self.tuned())

        def runner(spec, execute, workers, **_):
            specs.append(spec.get("tuning"))
            return original(spec, execute, workers)

        session.run_session(config(tuning=12), runner=runner)
        assert specs[0] in (None, {}) and specs[1]["iterations"] == 12

    def test_every_hypothesis_of_a_stage_is_confirmed_on_that_stage(self):
        state = session.run_session(config(tuning=12, per_stage=30), runner=make_runner(planted(), self.tuned()))
        assert {item["stage"] for item in state["confirmations"]} == {"default", "tuned"}
        assert len(state["confirmations"]) == len(state["hypotheses"])


class TestFailures:
    def test_a_failed_confirmation_dataset_leaves_the_rest_to_confirm(self):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = probe["confirm"][0]
        state = session.run_session(config(id="q"), runner=make_runner(planted(), fail=(failed,)))
        assert state["status"] == "completed" and failed not in state["stages"][0]["finished"]
        assert state["confirmations"][0]["datasets"] == 9

    def test_too_few_finished_confirmation_datasets_abort_the_session(self):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = tuple(probe["confirm"][:5])
        state = session.run_session(config(id="q"), runner=make_runner(planted(), fail=failed))
        assert state["status"] == "aborted" and "confirmation" in state["reason"] and state["hypotheses"] == []

    def test_too_few_finished_exploration_datasets_abort_the_session(self):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = tuple(probe["explore"][:4])
        state = session.run_session(config(id="q"), runner=make_runner(planted(), fail=failed))
        assert state["status"] == "aborted" and "exploration" in state["reason"]

    def test_an_aborted_session_is_saved_and_has_no_confirmations(self, root):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = tuple(probe["explore"][:4])
        session.run_session(config(id="q"), runner=make_runner(planted(), fail=failed))
        saved = json.loads((root / "q" / "session.json").read_text(encoding="utf-8"))
        assert saved["status"] == "aborted" and not saved.get("confirmations")

    def test_a_runner_that_raises_marks_the_session_failed(self):
        def broken(spec, execute, workers, **_):
            raise RuntimeError("sandbox down")

        state = session.run_session(config(), runner=broken)
        assert state["status"] == "failed" and "sandbox down" in state["reason"]


class TestNovelty:
    def test_a_claim_confirmed_in_an_earlier_session_is_not_registered_again(self):
        first = session.run_session(config(id="a"), runner=make_runner(planted()))
        second = session.run_session(config(id="b"), runner=make_runner(planted()))
        confirmed = {(tuple(item["subject"]), tuple(item["other"])) for item in first["hypotheses"] if any(c["id"] == item["id"] and c["status"] == "confirmed" for c in first["confirmations"])}
        again = {(tuple(item["subject"]), tuple(item["other"])) for item in second["hypotheses"]}
        assert confirmed and not confirmed & again
        assert any(item["reason"] == generate.ALREADY_KNOWN for item in second["skipped"])

    def stored(self, session_id, status, confirmation, subject="A"):
        record = {"id": "H1", "subject": [subject], "other": ["B"], "stage": "default", "metric": "roc_auc", "statement": "x", "evidence": {}, "digest": "d", "registered_at": "t"}
        session.save({"id": session_id, "status": status, "hypotheses": [record], "confirmations": [{"id": "H1", "status": confirmation}]})

    def test_only_completed_sessions_count(self):
        self.stored("done", "completed", "confirmed", "A")
        self.stored("broken", "failed", "confirmed", "F")
        self.stored("stopped", "aborted", "confirmed", "S")
        assert session.known_claims() == frozenset({(("A",), ("B",))})

    def test_only_the_confirmed_status_counts(self):
        for index, status in enumerate(["reversed", "not_confirmed", "not_testable"]):
            self.stored(f"s{index}", "completed", status)
        assert session.known_claims() == frozenset()

    def test_the_pair_is_stored_in_the_direction_it_was_confirmed(self):
        self.stored("done", "completed", "confirmed")
        assert (("B",), ("A",)) not in session.known_claims()

    def test_a_named_session_can_be_left_out(self):
        self.stored("done", "completed", "confirmed")
        assert session.known_claims(exclude="done") == frozenset()

    def test_the_known_claims_come_only_from_confirmed_hypotheses(self, root):
        session.run_session(config(id="a"), runner=make_runner({"RandomForest": 0.0, "ExtraTrees": 0.0, "MLP": 0.0, "DecisionTree": 0.0}, noise=0.02))
        assert session.known_claims() == frozenset()

    def test_the_session_that_is_running_is_not_its_own_history(self):
        first = session.run_session(config(id="a"), runner=make_runner(planted()))
        assert session.known_claims(exclude="a") == frozenset()
        assert session.known_claims() != frozenset() or not [c for c in first["confirmations"] if c["status"] == "confirmed"]


class TestStore:
    def test_a_saved_session_can_be_loaded_and_listed(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert session.load("s1") == state and session.list_sessions() == ["s1"]

    def test_the_sessions_are_listed_in_name_order(self):
        for name in ["b", "c", "a"]:
            session.save({"id": name, "status": "completed", "hypotheses": []})
        assert session.list_sessions() == ["a", "b", "c"]

    def test_verifying_an_unknown_session_is_an_error(self):
        with pytest.raises(ProtocolError, match="not found"):
            session.verify("nope")

    def test_an_unknown_session_is_none(self):
        assert session.load("nope") is None

    def test_a_bad_id_is_refused(self):
        with pytest.raises(ProtocolError, match="id"):
            session.load("../x")

    def test_an_existing_session_id_is_not_overwritten(self):
        session.run_session(config(), runner=make_runner(planted()))
        with pytest.raises(ProtocolError, match="exists"):
            session.run_session(config(), runner=make_runner(planted()))

    def test_the_tampering_of_a_saved_hypothesis_is_detected_on_load_for_report(self, root):
        session.run_session(config(), runner=make_runner(planted()))
        path = root / "s1" / "session.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["hypotheses"][0]["subject"] = ["MLP"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ProtocolError, match="digest"):
            session.verify("s1")

    def test_an_untouched_session_verifies(self):
        session.run_session(config(), runner=make_runner(planted()))
        assert session.verify("s1") is True


class TestReport:
    def report(self, **changes):
        state = session.run_session(config(**changes), runner=make_runner(planted()))
        return state, session.render_report(state)

    def test_the_report_is_saved_next_to_the_session(self, root):
        self.report()
        assert (root / "s1" / "report.md").read_text(encoding="utf-8").startswith("# ")

    def test_it_states_the_protocol_in_plain_words(self):
        _, text = self.report()
        for phrase in ["exploration", "confirmation", "registered", "Holm", "Benjamini", "sealed"]:
            assert phrase.lower() in text.lower()

    def test_it_lists_every_registered_hypothesis_with_its_adjusted_p_value_and_status(self):
        state, text = self.report()
        for item in state["hypotheses"]:
            assert item["statement"] in text
        assert "confirmed" in text and "adjusted p" in text.lower()

    def test_the_exploration_estimate_and_the_confirmation_effect_are_labelled_apart(self):
        _, text = self.report()
        assert "exploration estimate" in text.lower() and "confirmation effect" in text.lower()

    def test_the_limits_are_stated(self):
        _, text = self.report()
        assert "Limits" in text and "binary classification" in text and "not a new scientific" in text.lower()

    def test_the_counts_add_up(self):
        state, text = self.report()
        counts = {name: sum(1 for item in state["confirmations"] if item["status"] == name) for name in protocol.STATUSES}
        assert f"{counts['confirmed']} confirmed" in text and f"{len(state['hypotheses'])} registered" in text

    def test_an_aborted_session_says_why(self):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = tuple(probe["explore"][:4])
        state = session.run_session(config(id="q"), runner=make_runner(planted(), fail=failed))
        text = session.render_report(state)
        assert "aborted" in text.lower() and state["reason"] in text

    def test_the_skipped_claims_are_listed_with_their_reason(self):
        session.run_session(config(id="a"), runner=make_runner(planted()))
        state = session.run_session(config(id="b"), runner=make_runner(planted()))
        text = session.render_report(state)
        assert generate.ALREADY_KNOWN in text


class TestNullWorld:
    def test_without_any_true_difference_almost_nothing_is_confirmed(self):
        confirmed = 0
        for seed in range(12):
            state = session.run_session(
                config(id=f"n{seed}", per_stage=25),
                runner=make_runner({"RandomForest": 0.0, "ExtraTrees": 0.0, "MLP": 0.0, "DecisionTree": 0.0}, noise=0.01, seed=seed),
            )
            confirmed += sum(1 for item in state["confirmations"] if item["status"] == "confirmed")
        assert confirmed <= 1
