import io

import pytest

import app.research.__main__ as cli
import app.research.session as session
from tests.test_research_session import MODELS, make_runner, planted

OK, UNFINISHED, USAGE = cli.EXIT_OK, cli.EXIT_UNFINISHED, cli.EXIT_USAGE


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "ROOT", tmp_path / "research")
    monkeypatch.setattr(session, "known_claims", lambda exclude=None: frozenset())
    return tmp_path / "research"


def run(*arguments, runner=None):
    out = io.StringIO()
    code = cli.main(list(arguments), runner=runner or make_runner(planted()), out=out)
    return code, out.getvalue()


BASE = ["run", "--models", ",".join(MODELS), "--id", "c1"]


def test_the_exit_codes_are_the_documented_numbers():
    assert (cli.EXIT_OK, cli.EXIT_UNFINISHED, cli.EXIT_USAGE) == (0, 1, 2)


class TestHeartbeat:
    def test_a_cli_run_keeps_its_heartbeat_while_it_works(self):
        import app.research.service as service

        inner = make_runner(planted())
        seen = []

        def runner(spec, execute, workers):
            seen.append(service.is_alive("c1"))
            return inner(spec, execute, workers)

        run(*BASE, runner=runner)
        assert seen == [True] and session.load("c1")["status"] == "completed"


class TestDefaults:
    def test_the_defaults_of_a_plain_run(self):
        run(*BASE)
        from app.research import generate
        from app.research.protocol import ALPHA

        saved = session.load("c1")["config"]
        assert saved["explore"] == 6 and saved["seed"] == 0 and saved["tuning"] is None and saved["per_stage"] == 8
        assert saved["effect"] == generate.DEFAULT_EFFECT and saved["consistency"] == generate.DEFAULT_CONSISTENCY
        assert saved["tuning_trigger"] == generate.TUNING_TRIGGER and saved["alpha"] == ALPHA

    def test_the_alpha_can_be_chosen(self):
        run(*BASE[:-2], "--id", "c9", "--alpha", "0.01")
        assert session.load("c9")["config"]["alpha"] == 0.01 and session.load("c9")["alpha"] == 0.01

    def test_two_runs_without_an_id_do_not_collide(self):
        run("run", "--models", ",".join(MODELS))
        run("run", "--models", ",".join(MODELS))
        assert len(session.list_sessions()) == 2

    def test_the_workers_reach_the_runner(self):
        seen = []
        inner = make_runner(planted())

        def runner(spec, execute, workers):
            seen.append(workers)
            return inner(spec, execute, workers)

        run(*BASE, "--workers", "5", runner=runner)
        run(*BASE[:-2], "--id", "c10", runner=runner)
        from app.campaign.runner import DEFAULT_WORKERS

        assert seen == [5, DEFAULT_WORKERS]


class TestGeneratorOption:
    def test_the_default_is_the_rule_generator(self):
        run(*BASE)
        assert session.load("c1")["config"]["generator"] == "rules" and session.load("c1")["config"]["llm_model"] == "gpt-4o"

    def test_the_llm_generator_and_its_model_can_be_chosen(self, monkeypatch):
        monkeypatch.setattr(session.llm_generator, "make_complete", lambda model: lambda prompt: '{"hypotheses": []}')
        run(*BASE[:-2], "--id", "c11", "--generator", "llm", "--llm-model", "gpt-test")
        saved = session.load("c11")["config"]
        assert saved["generator"] == "llm" and saved["llm_model"] == "gpt-test"

    def test_an_unknown_generator_is_refused_by_the_parser(self):
        with pytest.raises(SystemExit):
            run(*BASE, "--generator", "oracle")


class TestReuseOption:
    def test_the_results_of_an_earlier_session_are_reused_without_a_runner(self):
        run(*BASE)

        def never(spec, execute, workers):
            raise AssertionError("no experiment may run")

        code, text = run(*BASE[:-2], "--id", "c12", "--reuse", "c1", runner=never)
        assert code == OK and session.load("c12")["config"]["reuse"] == "c1"

    def test_a_missing_source_is_a_usage_error(self):
        code, text = run(*BASE, "--reuse", "nope")
        assert code == USAGE and "nothing to reuse" in text

    def test_no_reuse_is_the_default(self):
        run(*BASE)
        assert session.load("c1")["config"]["reuse"] is None


class TestHistoryFlag:
    def test_the_history_is_used_by_default_and_can_be_switched_off(self):
        run(*BASE)
        assert session.load("c1")["config"]["use_history"] is True
        run(*BASE[:-2], "--id", "c13", "--no-history")
        assert session.load("c13")["config"]["use_history"] is False


class TestRun:
    def test_a_run_prints_the_summary_and_exits_zero(self):
        code, text = run(*BASE)
        assert code == OK
        assert "session c1: completed" in text and "registered" in text and "confirmed" in text

    def test_it_saves_the_session_and_the_report(self, root):
        run(*BASE)
        assert (root / "c1" / "session.json").exists() and (root / "c1" / "report.md").exists()

    def test_it_prints_where_the_report_is(self, root):
        _, text = run(*BASE)
        assert str(root / "c1" / "report.md") in text

    def test_the_options_reach_the_configuration(self):
        run(*BASE[:-2], "--id", "c2", "--explore", "7", "--seed", "3", "--tuning", "12", "--per-stage", "3", "--effect", "0.02", "--consistency", "0.9", "--tuning-trigger", "0.5")
        saved = session.load("c2")["config"]
        assert saved["explore"] == 7 and saved["seed"] == 3 and saved["tuning"] == 12 and saved["per_stage"] == 3
        assert saved["effect"] == 0.02 and saved["consistency"] == 0.9 and saved["tuning_trigger"] == 0.5

    def test_the_pool_can_be_chosen(self):
        from app.datasets import research_pool

        pool = research_pool()[:12]
        run(*BASE[:-2], "--id", "c3", "--pool", ",".join(pool), runner=make_runner(planted()))
        assert session.load("c3")["config"]["pool"] == pool

    def test_a_default_id_is_generated(self):
        code, text = run("run", "--models", ",".join(MODELS))
        assert code == OK and session.list_sessions() and session.list_sessions()[0] in text

    def test_an_aborted_session_exits_with_the_unfinished_code(self):
        probe, _ = run(*BASE[:-2], "--id", "probe")
        failed = tuple(session.load("probe")["explore"][:4])
        code, text = run(*BASE[:-2], "--id", "c4", runner=make_runner(planted(), fail=failed))
        assert code == UNFINISHED and "aborted" in text and "exploration datasets finished" in text

    def test_bad_input_exits_with_the_usage_code_and_a_message(self):
        code, text = run("run", "--models", "MLP", "--id", "c5")
        assert code == USAGE and text.startswith("invalid session:") and "at least two" in text
        code, text = run("run", "--models", "MLP,Nope", "--id", "c6")
        assert code == USAGE and "unknown" in text

    def test_an_existing_id_is_refused(self):
        run(*BASE)
        code, text = run(*BASE)
        assert code == USAGE and "exists" in text

    def test_models_are_required(self):
        with pytest.raises(SystemExit):
            run("run", "--id", "c7")


class TestShow:
    def test_it_prints_the_report(self):
        run(*BASE)
        code, text = run("show", "c1")
        assert code == OK and text.startswith("# Research session c1")

    def test_an_unknown_session_is_a_usage_error(self):
        code, text = run("show", "nope")
        assert code == USAGE and "no report" in text

    def test_a_bad_id_is_a_usage_error(self):
        code, text = run("show", "../x")
        assert code == USAGE and "not valid" in text


class TestList:
    def test_it_lists_the_sessions_with_their_status(self):
        run(*BASE)
        code, text = run("list")
        assert code == OK and "c1 completed" in text

    def test_an_empty_list_prints_nothing(self):
        code, text = run("list")
        assert code == OK and text == ""


class TestVerify:
    def test_an_untouched_session_verifies(self):
        run(*BASE)
        code, text = run("verify", "c1")
        assert code == OK and "intact" in text

    def test_a_changed_hypothesis_is_reported(self, root):
        import json

        run(*BASE)
        path = root / "c1" / "session.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["hypotheses"][0]["subject"] = ["MLP"]
        path.write_text(json.dumps(data), encoding="utf-8")
        code, text = run("verify", "c1")
        assert code == UNFINISHED and "digest" in text

    def test_an_unknown_session_is_a_usage_error(self):
        code, text = run("verify", "nope")
        assert code == USAGE and "not found" in text
