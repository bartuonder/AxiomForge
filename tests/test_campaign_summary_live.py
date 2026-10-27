import pytest

from app.campaign.runner import DEFAULT_WORKERS
from app.campaign.summary import build_summary
from app.campaign.vocabulary import STATUS_LABELS
from app.friendly_errors import explain_error

KEYS = ["tb_credit", "tb_pol", "tb_house", "tb_eye", "tb_cover", "tb_jannis"]


def live_state(statuses, status="running", seconds=60.0, **extra):
    datasets = {}
    for key, item in zip(KEYS, statuses):
        datasets[key] = {"status": item, **({"seconds": seconds} if item == "finished" else {})}
    return {"id": "abc", "title": "T", "status": status, "datasets": datasets, **extra}


def live(state, language="tr"):
    return build_summary(state, None, None, None, language)["live"]


def actions(state):
    return build_summary(state, None, None, None, "tr")["actions"]


class TestEta:
    def test_the_remaining_batches_times_the_mean_time(self):
        state = live_state(["finished", "finished", "running", "running", "queued", "queued"])
        assert live(state)["eta_seconds"] == 60 * 2

    def test_a_single_batch_left(self):
        state = live_state(["finished", "finished", "finished", "running", "running", "queued"])
        assert live(state)["eta_seconds"] == 60

    def test_it_uses_the_mean_of_the_finished_ones(self):
        state = live_state(["finished", "finished", "queued", "queued", "queued", "queued"])
        state["datasets"][KEYS[0]]["seconds"] = 30.0
        state["datasets"][KEYS[1]]["seconds"] = 90.0
        assert live(state)["eta_seconds"] == 60 * 2

    def test_failed_and_cancelled_datasets_are_not_waited_for(self):
        state = live_state(["finished", "failed", "cancelled", "queued", "queued", "queued"])
        assert live(state)["eta_seconds"] == 60

    def test_the_number_of_workers_is_the_runner_default(self):
        statuses = ["finished"] + ["queued"] * (DEFAULT_WORKERS * 2)
        keys = [f"k{i}" for i in range(len(statuses))]
        state = {"id": "a", "status": "running", "datasets": {key: {"status": item, **({"seconds": 10.0} if item == "finished" else {})} for key, item in zip(keys, statuses)}}
        assert live(state)["eta_seconds"] == 20

    def test_nothing_is_known_before_the_first_dataset_ends(self):
        assert live(live_state(["running", "running", "running", "queued", "queued", "queued"]))["eta_seconds"] is None

    def test_a_queued_campaign_has_no_estimate(self):
        assert live(live_state(["queued"] * 6, status="queued"))["eta_seconds"] is None

    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "needs_review"])
    def test_a_stopped_campaign_has_no_estimate(self, status):
        assert live(live_state(["finished", "queued", "queued", "queued", "queued", "queued"], status=status))["eta_seconds"] is None

    def test_finished_ones_without_a_time_give_no_estimate(self):
        state = live_state(["finished", "queued", "queued", "queued", "queued", "queued"])
        del state["datasets"][KEYS[0]]["seconds"]
        assert live(state)["eta_seconds"] is None

    def test_no_dataset_left_means_no_estimate(self):
        assert live(live_state(["finished"] * 6))["eta_seconds"] is None

    def test_it_is_a_whole_number(self):
        state = live_state(["finished", "queued", "queued", "queued", "queued", "queued"], seconds=10.4)
        assert isinstance(live(state)["eta_seconds"], int) and live(state)["eta_seconds"] == 21


class TestRunningList:
    def test_the_running_datasets_are_named_in_the_language(self):
        state = live_state(["finished", "running", "running", "queued", "queued", "queued"])
        assert [item["key"] for item in live(state)["running"]] == [KEYS[1], KEYS[2]]
        assert all(item["label"] for item in live(state, "en")["running"])

    def test_nothing_runs_in_a_finished_campaign(self):
        assert live(live_state(["finished"] * 6, status="completed"))["running"] == []

    def test_a_dataset_without_a_registered_name_keeps_its_key(self):
        state = {"id": "a", "status": "running", "datasets": {"zz_new": {"status": "running"}}}
        assert live(state)["running"] == [{"key": "zz_new", "label": "zz_new"}]


class TestCancelAndRetryActions:
    @pytest.mark.parametrize("status,cancel,retry", [("queued", True, False), ("running", True, False), ("failed", False, True), ("cancelled", False, True), ("completed", False, False), ("needs_review", False, False)])
    def test_which_buttons_make_sense(self, status, cancel, retry):
        assert actions(live_state(["queued"] * 6, status=status)) == {"cancel": cancel, "retry": retry}

    def test_a_pending_cancel_request_is_passed_on(self):
        assert live(live_state(["running"] * 3, cancel_requested=True))["cancel_requested"] is True

    def test_it_is_false_without_a_request(self):
        assert live(live_state(["running"] * 3))["cancel_requested"] is False

    def test_the_number_of_restarts_is_shown(self):
        assert build_summary(live_state(["queued"] * 6, recoveries=2), None, None, None, "tr")["recoveries"] == 2

    def test_it_is_zero_by_default(self):
        assert build_summary(live_state(["queued"] * 6), None, None, None, "tr")["recoveries"] == 0


class TestCancelledStatus:
    def test_it_has_names_and_a_tone(self):
        for language in ("tr", "en"):
            assert STATUS_LABELS[language]["cancelled"]
        result = build_summary(live_state(["cancelled"] * 6, status="cancelled"), None, None, None, "tr")
        assert result["status"] == {"code": "cancelled", "label": "İptal edildi", "tone": "muted"}

    def test_progress_counts_only_finished_and_failed(self):
        result = build_summary(live_state(["finished", "finished", "cancelled", "cancelled", "cancelled", "cancelled"], status="cancelled"), None, None, None, "tr")
        assert result["progress"] == {"finished": 2, "failed": 0, "total": 6, "percent": 33}


class TestCancelledError:
    def test_it_is_explained_in_both_languages(self):
        for language in ("tr", "en"):
            info = explain_error("campaign cancelled: the campaign was stopped before it finished", language)
            assert info["code"] == "campaign_cancelled" and info["title"] and info["hint"]

    def test_it_is_not_confused_with_a_failure(self):
        assert explain_error("campaign failed: boom", "tr")["code"] == "campaign_failed"
