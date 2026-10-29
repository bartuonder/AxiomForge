import pytest

import app.research.session as session
from tests.test_research_session import config, make_runner, planted


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    return tmp_path / "research"


def statuses(state):
    return {key: item["status"] for key, item in state["progress"]["datasets"].items()}


class TestProgressOnDisk:
    def test_every_dataset_starts_queued_when_the_stage_starts(self):
        seen = []
        inner = make_runner(planted())

        def runner(spec, execute, workers, should_stop=None, on_update=None):
            state = session.load("s1")
            seen.append((state["progress"]["stage"], set(statuses(state).values()), len(state["progress"]["datasets"])))
            return inner(spec, execute, workers, should_stop, on_update)

        session.run_session(config(), runner=runner)
        assert seen == [("default", {"queued"}, 16)]

    def test_updates_reach_the_disk_while_the_stage_runs(self):
        seen = []
        inner = make_runner(planted(), fail=("tb_magic",))

        def runner(spec, execute, workers, should_stop=None, on_update=None):
            def spying(dataset, result):
                on_update(dataset, result)
                seen.append((dataset, result["status"], statuses(session.load("s1"))[dataset]))

            return inner(spec, execute, workers, should_stop, spying)

        session.run_session(config(), runner=runner)
        assert ("tb_magic", "running", "running") in seen
        assert ("tb_magic", "failed", "failed") in seen
        assert any(status == "finished" and shown == "finished" for _, status, shown in seen)

    def test_the_progress_restarts_for_the_tuned_stage(self):
        stages = []
        inner = make_runner(planted(), tuned_abilities=planted())

        def runner(spec, execute, workers, should_stop=None, on_update=None):
            stages.append((session.load("s1")["progress"]["stage"], set(statuses(session.load("s1")).values())))
            return inner(spec, execute, workers, should_stop, on_update)

        session.run_session(config(tuning=12), runner=runner)
        assert stages == [("default", {"queued"}), ("tuned", {"queued"})]

    def test_a_finished_session_keeps_no_progress(self):
        assert session.run_session(config(), runner=make_runner(planted()))["progress"] == {}
        assert session.load("s1")["progress"] == {}

    def test_a_cancelled_session_keeps_no_progress(self):
        assert session.run_session(config(), runner=make_runner(planted()), should_stop=lambda: True)["progress"] == {}

    def test_a_queued_session_has_no_progress(self):
        assert session.queue_session(config())["progress"] == {}


class TestSummary:
    def test_it_counts_the_datasets_by_status(self):
        state = {
            **session.queue_session(config()),
            "status": "running",
            "progress": {
                "stage": "tuned",
                "datasets": {"a": {"status": "finished"}, "b": {"status": "finished"}, "c": {"status": "failed"}, "d": {"status": "running"}, "e": {"status": "queued"}},
            },
        }
        assert session.summary_of(state)["progress"] == {"stage": "tuned", "total": 5, "finished": 2, "failed": 1, "running": ["d"]}

    def test_a_state_without_progress_has_an_empty_summary(self):
        queued = session.queue_session(config())
        assert session.summary_of(queued)["progress"] == {"stage": "", "total": 0, "finished": 0, "failed": 0, "running": []}
        old = dict(queued)
        del old["progress"]
        assert session.summary_of(old)["progress"]["total"] == 0

    def test_the_running_datasets_are_in_the_order_of_the_pool(self):
        state = {
            **session.queue_session(config()),
            "progress": {"stage": "default", "datasets": {"z": {"status": "running"}, "a": {"status": "running"}}},
        }
        assert session.summary_of(state)["progress"]["running"] == ["z", "a"]
