import pytest

import app.research.session as session
from app.research.protocol import ProtocolError
from tests.test_research_session import MODELS, config, make_runner, planted


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    return tmp_path / "research"


class TestQueue:
    def test_it_saves_a_queued_state_with_the_split_and_the_budget(self):
        state = session.queue_session(config())
        assert state["status"] == "queued" and state["id"] == "s1"
        assert len(state["explore"]) == 6 and len(state["confirm"]) == 10 and state["budget"] == 25
        assert state["hypotheses"] == [] and state["stages"] == [] and state["config"]["models"] == MODELS
        assert session.load("s1") == state

    def test_it_refuses_an_id_that_exists(self):
        session.queue_session(config())
        with pytest.raises(ProtocolError, match="exists already"):
            session.queue_session(config())

    def test_a_queued_summary_has_zero_counts(self):
        summary = session.summary_of(session.queue_session(config()))
        assert summary["status"] == "queued" and summary["registered"] == 0 and summary["stages"] == []

    def test_a_queued_session_runs_and_keeps_its_split(self):
        queued = session.queue_session(config())
        state = session.run_session(config(), runner=make_runner(planted()))
        assert state["status"] == "completed" and state["explore"] == queued["explore"] and state["confirm"] == queued["confirm"]

    def test_the_creation_time_of_the_queue_is_kept(self):
        session.save({**session.queue_session(config()), "created": "2026-10-28T08:00:00+00:00"})
        state = session.run_session(config(), runner=make_runner(planted()))
        assert state["created"] == "2026-10-28T08:00:00+00:00"

    def test_a_session_that_ran_cannot_be_run_again(self):
        session.run_session(config(), runner=make_runner(planted()))
        with pytest.raises(ProtocolError, match="exists already"):
            session.run_session(config(), runner=make_runner(planted()))

    def test_a_running_session_cannot_be_run_again(self):
        session.save({**session.queue_session(config()), "status": "running"})
        with pytest.raises(ProtocolError, match="exists already"):
            session.run_session(config(), runner=make_runner(planted()))


class TestPhase:
    def test_the_phase_names_the_stage_that_is_running(self):
        seen = []
        inner = make_runner(planted(), tuned_abilities=planted())

        def runner(spec, execute, workers, should_stop=None):
            seen.append((session.load("s1")["status"], session.load("s1")["phase"]))
            return inner(spec, execute, workers)

        session.run_session(config(tuning=12), runner=runner)
        assert seen[0] == ("running", "default")
        assert all(status == "running" for status, _ in seen)

    def test_a_finished_session_has_no_phase(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert state["phase"] == ""

    def test_the_summary_carries_the_phase(self):
        state = session.queue_session(config())
        assert session.summary_of({**state, "phase": "tuned"})["phase"] == "tuned"
        assert session.summary_of(state)["phase"] == ""


class TestStop:
    def test_it_cancels_before_the_first_experiment(self):
        calls = []
        state = session.run_session(config(), runner=make_runner(planted(), calls=calls), should_stop=lambda: True)
        assert state["status"] == "cancelled" and calls == [] and state["hypotheses"] == []
        assert session.load("s1")["status"] == "cancelled"

    def test_it_cancels_after_a_stage_without_registering_anything(self):
        flags = {"stop": False}
        inner = make_runner(planted())

        def runner(spec, execute, workers, should_stop=None):
            result = inner(spec, execute, workers)
            flags["stop"] = True
            return result

        state = session.run_session(config(), runner=runner, should_stop=lambda: flags["stop"])
        assert state["status"] == "cancelled" and state["hypotheses"] == [] and "confirmations" not in state

    def test_a_stage_that_was_stopped_is_not_saved_for_a_later_retry(self, root):
        inner = make_runner(planted())

        def runner(spec, execute, workers, should_stop=None):
            outcome = inner(spec, execute, workers)
            outcome["datasets"] = dict(list(outcome["datasets"].items())[:3])
            outcome["cancelled"] = [key for key in spec["datasets"] if key not in outcome["datasets"]]
            return outcome

        flags = {"stop": False}

        def stop_after_run():
            return flags["stop"]

        def stopping_runner(spec, execute, workers, should_stop=None):
            outcome = runner(spec, execute, workers)
            flags["stop"] = True
            return outcome

        state = session.run_session(config(), runner=stopping_runner, should_stop=stop_after_run)
        assert state["status"] == "cancelled"
        assert not session.has_stage("s1", "default")

    def test_the_stop_callback_reaches_the_runner(self):
        received = []

        def runner(spec, execute, workers, should_stop=None):
            received.append(should_stop)
            return make_runner(planted())(spec, execute, workers)

        session.run_session(config(), runner=runner, should_stop=lambda: False)
        assert callable(received[0])

    def test_without_a_stop_callback_the_runner_gets_none(self):
        calls = []
        session.run_session(config(), runner=make_runner(planted(), calls=calls))
        assert len(calls) == 1

    def test_a_cancelled_session_writes_a_report(self, root):
        session.run_session(config(), runner=make_runner(planted()), should_stop=lambda: True)
        assert (root / "s1" / session.REPORT).exists()
        assert "cancelled" in (root / "s1" / session.REPORT).read_text(encoding="utf-8")


class TestResume:
    def test_saved_stages_of_the_same_session_are_reused(self):
        calls = []
        first = session.run_session(config(), runner=make_runner(planted(), calls=calls))
        assert first["status"] == "completed" and len(calls) == 1
        session.reset_for_retry("s1")
        calls.clear()
        again = session.run_session(config(reuse="s1"), runner=make_runner(planted(), calls=calls))
        assert calls == [] and again["status"] == "completed"

    def test_reset_keeps_the_stage_files_and_drops_the_state(self, root):
        session.run_session(config(), runner=make_runner(planted()))
        session.reset_for_retry("s1")
        assert session.load("s1") is None
        assert (root / "s1" / session.STAGE_DIR / "default.json").exists()
        assert not (root / "s1" / session.REPORT).exists()

    def test_reset_of_an_unknown_session_fails(self):
        with pytest.raises(ProtocolError, match="not found"):
            session.reset_for_retry("nope")

    def test_report_names_the_resume(self):
        session.run_session(config(), runner=make_runner(planted()))
        session.reset_for_retry("s1")
        state = session.run_session(config(reuse="s1"), runner=make_runner(planted()))
        text = session.render_report(state)
        assert "earlier attempt of this session" in text and "reused from session s1" not in text
