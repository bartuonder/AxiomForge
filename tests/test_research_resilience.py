import json

import pytest

import app.research.session as session
from app.datasets import research_pool
from app.research import generate, protocol
from app.research.protocol import ProtocolError
from tests.test_research_session import MODELS, config, make_runner, planted

POOL = research_pool()
TUNED = {"RandomForest": 0.05, "ExtraTrees": 0.05, "MLP": 0.045, "DecisionTree": -0.01}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    return tmp_path / "research"


class TestLaterStageFailure:
    def runner_failing_when_tuned(self, error):
        inner = make_runner(planted(), TUNED)

        def runner(spec, execute, workers):
            if spec.get("tuning"):
                raise error
            return inner(spec, execute, workers)

        return runner

    def test_a_tuned_stage_that_raises_keeps_the_default_stage_results(self):
        state = session.run_session(config(tuning=12), runner=self.runner_failing_when_tuned(RuntimeError("connection dropped")))
        assert state["status"] == "completed" and state["confirmations"]
        assert "tuned stage failed" in state["reason"] and "connection dropped" in state["reason"]
        assert {item["stage"] for item in state["hypotheses"]} == {"default"}
        assert [item["name"] for item in state["stages"]] == ["default", "tuned"]
        assert state["stages"][1]["error"] == "RuntimeError: connection dropped"

    def test_the_report_says_that_the_tuned_stage_failed(self):
        state = session.run_session(config(tuning=12), runner=self.runner_failing_when_tuned(RuntimeError("down")))
        assert "tuned stage failed" in session.render_report(state)

    def test_a_tuned_stage_with_too_few_finished_datasets_is_dropped_the_same_way(self):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = tuple(probe["confirm"][:5])
        state = session.run_session(config(id="q", tuning=12, per_stage=30), runner=make_runner(planted(), tuned_abilities=TUNED, fail_tuned=failed))
        assert state["status"] == "completed" and "tuned stage" in state["reason"] and "confirmation datasets" in state["reason"]
        assert {item["stage"] for item in state["hypotheses"]} == {"default"} and state["confirmations"]

    def test_a_default_stage_that_raises_still_fails_the_session(self):
        def broken(spec, execute, workers):
            raise RuntimeError("down")

        assert session.run_session(config(tuning=12), runner=broken)["status"] == "failed"


class TestStageResults:
    def test_each_stage_saves_its_results_for_every_dataset(self, root):
        session.run_session(config(tuning=12), runner=make_runner(planted(), TUNED))
        for name, tuning in (("default", None), ("tuned", 12)):
            saved = json.loads((root / "s1" / "stages" / f"{name}.json").read_text(encoding="utf-8"))
            assert saved["stage"] == name and saved["models"] == MODELS and saved["pool"] == POOL and saved["tuning"] == tuning
            assert set(saved["results"]) == set(POOL) and saved["failed"] == {}

    def test_the_results_are_saved_before_any_hypothesis_is_proposed(self, root, monkeypatch):
        seen = []
        original = generate.propose

        def spy(*args, **kwargs):
            seen.append((root / "s1" / "stages" / "default.json").exists())
            return original(*args, **kwargs)

        monkeypatch.setattr(generate, "propose", spy)
        session.run_session(config(), runner=make_runner(planted()))
        assert seen == [True]

    def test_failed_datasets_are_recorded_in_the_stage_file(self, root):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = probe["confirm"][0]
        session.run_session(config(id="q"), runner=make_runner(planted(), fail=(failed,)))
        saved = json.loads((root / "q" / "stages" / "default.json").read_text(encoding="utf-8"))
        assert failed not in saved["results"] and failed in saved["failed"]


class TestReuse:
    def base(self, **changes):
        return session.run_session(config(id="src", **changes), runner=make_runner(planted()))

    @staticmethod
    def never(spec, execute, workers):
        raise AssertionError("the runner must not be called")

    def test_a_session_can_reuse_the_results_of_another_without_running_anything(self):
        first = self.base()
        second = session.run_session(config(id="again", reuse="src"), runner=self.never)
        assert [item["digest"] for item in second["hypotheses"]] == [item["digest"] for item in first["hypotheses"]]
        assert [item["status"] for item in second["confirmations"]] == [item["status"] for item in first["confirmations"]]
        assert second["config"]["reuse"] == "src"

    def test_the_reused_stage_is_saved_again_so_the_new_session_can_be_reused_too(self, root):
        self.base()
        session.run_session(config(id="again", reuse="src"), runner=self.never)
        assert (root / "again" / "stages" / "default.json").exists()
        session.run_session(config(id="third", reuse="again"), runner=self.never)

    def test_another_generator_can_work_on_the_same_results(self):
        self.base()

        def custom(view, registry, stage, count, effect, consistency, known):
            item = protocol.Hypothesis("H1", ("MLP",), ("DecisionTree",), stage, "roc_auc", "custom", {"median_difference": 0.03, "wins": 6, "datasets": 6, "scope": "exploration"})
            return [item], []

        state = session.run_session(config(id="other", reuse="src"), runner=self.never, generator=custom)
        assert [item["statement"] for item in state["hypotheses"]] == ["custom"] and state["confirmations"][0]["status"] == "confirmed"

    def test_another_split_seed_works_on_the_same_results(self):
        self.base()
        state = session.run_session(config(id="reseeded", reuse="src", seed=3), runner=self.never)
        assert state["explore"] != session.load("src")["explore"] and state["status"] == "completed"

    def test_a_missing_source_is_refused_before_anything_is_saved(self, root):
        with pytest.raises(ProtocolError, match="nothing to reuse"):
            session.run_session(config(id="x", reuse="nope"), runner=self.never)
        assert not (root / "x").exists()

    def test_a_bad_source_id_is_refused(self):
        with pytest.raises(ProtocolError, match="id"):
            session.run_session(config(id="x", reuse="../y"), runner=self.never)

    def test_different_models_cannot_reuse(self):
        self.base()
        with pytest.raises(ProtocolError, match="models"):
            session.run_session(config(id="x", reuse="src", models=["RandomForest", "MLP"]), runner=self.never)

    def test_a_different_pool_cannot_reuse(self):
        self.base()
        with pytest.raises(ProtocolError, match="pool"):
            session.run_session(config(id="x", reuse="src", pool=POOL[:12]), runner=self.never)

    def test_a_different_tuning_cannot_reuse_the_tuned_stage(self):
        session.run_session(config(id="src", tuning=12), runner=make_runner(planted(), TUNED))
        with pytest.raises(ProtocolError, match="tuning"):
            session.run_session(config(id="x", reuse="src", tuning=20), runner=self.never)

    def test_a_stage_the_source_never_ran_is_run_fresh(self):
        self.base()
        calls = []
        state = session.run_session(config(id="more", reuse="src", tuning=12), runner=make_runner(planted(), TUNED, calls=calls))
        assert [call["tuned"] for call in calls] == [True] and {item["stage"] for item in state["hypotheses"]} == {"default", "tuned"}

    def test_a_source_that_ran_a_tuned_stage_can_be_reused_without_one(self):
        session.run_session(config(id="src", tuning=12), runner=make_runner(planted(), TUNED))
        state = session.run_session(config(id="plain", reuse="src"), runner=self.never)
        assert state["status"] == "completed" and {item["stage"] for item in state["hypotheses"]} == {"default"}

    def test_the_failed_datasets_of_the_source_are_kept(self, root):
        probe = session.run_session(config(id="p"), runner=make_runner(planted()))
        failed = probe["confirm"][0]
        session.run_session(config(id="src", seed=0), runner=make_runner(planted(), fail=(failed,)))
        session.run_session(config(id="again", reuse="src"), runner=self.never)
        saved = json.loads((root / "again" / "stages" / "default.json").read_text(encoding="utf-8"))
        assert failed in saved["failed"] and failed not in saved["results"]

    def test_a_bad_source_id_is_refused_when_the_configuration_is_made(self):
        with pytest.raises(ProtocolError, match="id"):
            session.SessionConfig(id="x", models=MODELS, reuse="../y")

    def test_the_report_says_where_the_results_came_from(self):
        self.base()
        state = session.run_session(config(id="again", reuse="src"), runner=self.never)
        assert "reused from session src" in session.render_report(state)


class TestHistoryOption:
    def test_a_session_can_ignore_the_history(self, monkeypatch):
        calls = []
        monkeypatch.setattr(session, "known_claims", lambda exclude=None: calls.append(1) or frozenset({(("RandomForest",), ("MLP",))}))
        with_history = session.run_session(config(id="a"), runner=make_runner(planted()))
        without = session.run_session(config(id="b", use_history=False), runner=make_runner(planted()))
        assert len(calls) == 1
        assert any("RandomForest scores higher than MLP" in item["statement"] for item in without["hypotheses"])
        assert not any("RandomForest scores higher than MLP" in item["statement"] for item in with_history["hypotheses"])

    def test_the_default_is_to_use_the_history(self):
        assert session.SessionConfig(id="s", models=MODELS).use_history is True
