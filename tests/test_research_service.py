import os
import threading

import pytest

import app.research.service as service
import app.research.session as session
from app.datasets import research_pool
from tests.test_research_session import config, make_runner, planted


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    return tmp_path / "research"


def age_heartbeat(session_id, seconds):
    path = session.session_dir(session_id) / service.HEARTBEAT_FILE
    stamp = path.stat().st_mtime - seconds
    os.utime(path, (stamp, stamp))


class TestHeartbeat:
    def test_there_is_no_age_before_the_first_beat(self):
        session.queue_session(config())
        assert service.heartbeat_age("s1") is None and not service.is_alive("s1")

    def test_a_fresh_beat_is_alive_and_an_old_one_is_not(self):
        session.queue_session(config())
        service.beat("s1")
        assert service.is_alive("s1")
        age_heartbeat("s1", service.ALIVE_SECONDS + 5)
        assert not service.is_alive("s1")

    def test_the_age_counts_from_the_given_clock(self):
        session.queue_session(config())
        service.beat("s1")
        stamp = (session.session_dir("s1") / service.HEARTBEAT_FILE).stat().st_mtime
        assert service.heartbeat_age("s1", stamp + 30) == pytest.approx(30)

    def test_the_beating_context_writes_and_stops(self):
        session.queue_session(config())
        with service.beating("s1"):
            assert service.is_alive("s1")
            assert any(thread.name == "research-heartbeat" for thread in threading.enumerate())
        assert not any(thread.name == "research-heartbeat" for thread in threading.enumerate())


class TestCancelFlag:
    def test_the_flag_is_set_and_cleared(self):
        session.queue_session(config())
        assert not service.cancel_requested("s1")
        service.request_cancel("s1")
        assert service.cancel_requested("s1")
        service.clear_cancel("s1")
        assert not service.cancel_requested("s1")


class TestEffectiveState:
    def test_a_finished_state_is_unchanged(self):
        state = session.run_session(config(), runner=make_runner(planted()))
        assert service.effective_state(state) == state

    def test_a_queued_state_is_unchanged(self):
        state = session.queue_session(config())
        assert service.effective_state(state) == state

    def test_a_running_state_with_a_live_worker_is_unchanged(self):
        state = {**session.queue_session(config()), "status": "running"}
        service.beat("s1")
        assert service.effective_state(state) == state

    def test_a_running_state_without_a_live_worker_is_failed_and_stale(self):
        state = {**session.queue_session(config()), "status": "running"}
        shown = service.effective_state(state)
        assert shown["status"] == "failed" and shown["stale"] is True and "worker" in shown["reason"]
        service.beat("s1")
        age_heartbeat("s1", service.ALIVE_SECONDS + 5)
        assert service.effective_state(state)["status"] == "failed"

    def test_a_pending_cancel_is_shown_on_a_running_state(self):
        state = {**session.queue_session(config()), "status": "running"}
        service.beat("s1")
        service.request_cancel("s1")
        assert service.effective_state(state)["cancel_requested"] is True

    def test_the_original_state_is_not_mutated(self):
        state = {**session.queue_session(config()), "status": "running"}
        service.effective_state(state)
        assert state["status"] == "running" and "stale" not in state


class TestExecute:
    def test_it_runs_a_queued_session_to_the_end(self):
        session.queue_session(config())
        state = service.execute_session("s1", runner=make_runner(planted()))
        assert state["status"] == "completed" and session.load("s1")["status"] == "completed"

    def test_it_runs_with_the_cancel_flag_honoured(self):
        session.queue_session(config())
        service.request_cancel("s1")
        state = service.execute_session("s1", runner=make_runner(planted()))
        assert state["status"] == "cancelled"

    def test_it_does_nothing_for_a_session_that_is_not_queued(self):
        done = session.run_session(config(), runner=make_runner(planted()))
        calls = []
        again = service.execute_session("s1", runner=make_runner(planted(), calls=calls))
        assert calls == [] and again["status"] == "completed" and again == done

    def test_an_unknown_session_returns_none(self):
        assert service.execute_session("nope", runner=make_runner(planted())) is None

    def test_an_unexpected_error_marks_the_session_failed(self):
        session.queue_session(config())

        def broken(spec, execute, workers, should_stop=None):
            raise KeyError("boom")

        state = service.execute_session("s1", runner=broken)
        assert state["status"] == "failed" and "KeyError" in state["reason"]

    def test_a_crash_outside_the_session_marks_it_failed(self, monkeypatch):
        session.queue_session(config())

        def explode(*arguments, **keywords):
            raise RuntimeError("disk gone")

        monkeypatch.setattr(session, "run_session", explode)
        state = service.execute_session("s1", runner=make_runner(planted()))
        assert state["status"] == "failed" and "disk gone" in state["reason"]
        assert session.load("s1")["status"] == "failed"

    def test_the_heartbeat_stops_after_the_run(self):
        session.queue_session(config())
        service.execute_session("s1", runner=make_runner(planted()))
        assert not any(thread.name == "research-heartbeat" for thread in threading.enumerate())


class TestCancel:
    def test_a_queued_session_is_cancelled_at_once(self):
        session.queue_session(config())
        state = service.cancel_session("s1")
        assert state["status"] == "cancelled" and session.load("s1")["status"] == "cancelled"
        assert (session.session_dir("s1") / session.REPORT).exists()

    def test_a_cancelled_queue_is_not_run(self):
        session.queue_session(config())
        service.cancel_session("s1")
        calls = []
        service.execute_session("s1", runner=make_runner(planted(), calls=calls))
        assert calls == []

    def test_a_running_session_gets_the_flag(self):
        session.save({**session.queue_session(config()), "status": "running"})
        service.beat("s1")
        state = service.cancel_session("s1")
        assert state["status"] == "running" and state["cancel_requested"] is True and service.cancel_requested("s1")

    def test_a_finished_session_cannot_be_cancelled(self):
        session.run_session(config(), runner=make_runner(planted()))
        with pytest.raises(service.SessionControlError) as caught:
            service.cancel_session("s1")
        assert caught.value.status_code == 409

    def test_a_stale_session_cannot_be_cancelled(self):
        session.save({**session.queue_session(config()), "status": "running"})
        with pytest.raises(service.SessionControlError) as caught:
            service.cancel_session("s1")
        assert caught.value.status_code == 409

    def test_an_unknown_session_is_not_found(self):
        with pytest.raises(service.SessionControlError) as caught:
            service.cancel_session("nope")
        assert caught.value.status_code == 404


class TestRetry:
    def failed(self, **changes):
        session.save({**session.queue_session(config(**changes)), "status": "failed", "reason": "boom"})

    def test_a_failed_session_is_queued_again(self):
        self.failed()
        queued = service.retry_session("s1")
        assert queued["status"] == "queued" and queued["reason"] == "" and session.load("s1")["status"] == "queued"

    def test_a_completed_session_cannot_be_retried(self):
        session.run_session(config(), runner=make_runner(planted()))
        with pytest.raises(service.SessionControlError) as caught:
            service.retry_session("s1")
        assert caught.value.status_code == 409

    def test_a_queued_or_running_session_cannot_be_retried(self):
        session.queue_session(config())
        with pytest.raises(service.SessionControlError) as caught:
            service.retry_session("s1")
        assert caught.value.status_code == 409
        session.save({**session.load("s1"), "status": "running"})
        service.beat("s1")
        with pytest.raises(service.SessionControlError):
            service.retry_session("s1")

    def test_a_stale_session_can_be_retried(self):
        session.save({**session.queue_session(config()), "status": "running"})
        service.beat("s1")
        age_heartbeat("s1", service.ALIVE_SECONDS + 5)
        queued = service.retry_session("s1")
        assert queued["status"] == "queued"
        assert service.heartbeat_age("s1") is None

    def test_a_cancelled_session_can_be_retried_and_the_flag_is_cleared(self):
        session.queue_session(config())
        service.cancel_session("s1")
        service.request_cancel("s1")
        queued = service.retry_session("s1")
        assert queued["status"] == "queued" and not service.cancel_requested("s1")

    def test_saved_stages_are_reused_by_the_retry(self):
        calls = []
        session.queue_session(config())
        done = session.run_session(config(), runner=make_runner(planted(), calls=calls))
        session.save({**done, "status": "failed", "reason": "late failure"})
        queued = service.retry_session("s1")
        assert queued["config"]["reuse"] == "s1"
        calls.clear()
        again = service.execute_session("s1", runner=make_runner(planted(), calls=calls))
        assert calls == [] and again["status"] == "completed"

    def test_an_aborted_session_is_rerun_from_scratch(self):
        runner = make_runner(planted(), fail=tuple(research_pool()[:12]))
        state = session.run_session(config(), runner=runner)
        assert state["status"] == "aborted"
        queued = service.retry_session("s1")
        assert queued["config"]["reuse"] is None

    def test_the_before_callback_runs_only_when_the_retry_is_allowed(self):
        calls = []
        session.run_session(config(), runner=make_runner(planted()))
        with pytest.raises(service.SessionControlError):
            service.retry_session("s1", before=lambda: calls.append(1))
        assert calls == []
        self.failed(id="s2")
        service.retry_session("s2", before=lambda: calls.append(1))
        assert calls == [1]

    def test_an_unknown_session_is_not_found(self):
        with pytest.raises(service.SessionControlError) as caught:
            service.retry_session("nope")
        assert caught.value.status_code == 404

    def test_the_other_session_reuse_is_kept_when_there_are_no_own_stages(self):
        session.save({**session.queue_session(config(reuse="s0")), "status": "failed", "reason": "boom"})
        assert service.retry_session("s1")["config"]["reuse"] == "s0"


class TestNewId:
    def test_ids_are_valid_and_different(self):
        first, second = service.new_session_id(), service.new_session_id()
        assert first != second and first.startswith("r-")
        session.session_dir(first)
