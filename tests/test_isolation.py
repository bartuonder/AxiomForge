from pathlib import Path

import app.guard as guard

REAL = Path(__file__).resolve().parents[1] / "reports" / "usage.json"


def test_the_tests_never_count_their_starts_in_the_real_usage_file():
    assert guard.USAGE_FILE != REAL


def test_the_tests_start_without_a_key_or_a_limit_from_the_environment(monkeypatch):
    import os

    assert "API_KEY" not in os.environ and "DAILY_START_LIMIT" not in os.environ


def test_a_start_spent_in_one_test_is_not_seen_by_the_next_one_part_one():
    guard.spend_start()
    assert guard.usage()["used"] == 1


def test_a_start_spent_in_one_test_is_not_seen_by_the_next_one_part_two():
    assert guard.usage()["used"] == 0
