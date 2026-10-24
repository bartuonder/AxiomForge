import json
import threading

import pytest

import app.campaign.store as store


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "campaigns")
    return tmp_path / "campaigns"


def test_a_new_id_is_a_unique_safe_token():
    first, second = store.new_campaign_id(), store.new_campaign_id()
    assert first != second
    assert store.campaign_dir(first).name == first


@pytest.mark.parametrize("bad", ["", "../escape", "a/b", "a\\b", "..", ".hidden", "x" * 65, "a b", "ü"])
def test_an_unsafe_id_is_refused(bad):
    with pytest.raises(store.CampaignStoreError, match="not valid"):
        store.campaign_dir(bad)


def test_state_round_trips_and_gets_an_update_stamp(root):
    store.save_state("abc", {"status": "running", "datasets": {"tb_credit": {"status": "running"}}})
    state = store.load_state("abc")
    assert state["status"] == "running"
    assert state["datasets"]["tb_credit"]["status"] == "running"
    assert state["updated"].endswith("+00:00")
    assert (root / "abc" / "state.json").exists()


def test_a_second_save_replaces_the_first(root):
    store.save_state("abc", {"status": "running"})
    store.save_state("abc", {"status": "completed"})
    assert store.load_state("abc")["status"] == "completed"
    assert [item.name for item in (root / "abc").iterdir()] == ["state.json"]


def test_a_missing_campaign_has_no_state_and_no_report():
    assert store.load_state("nope") is None
    assert store.load_report("nope") is None


def test_artifacts_are_written_side_by_side(root):
    store.save_artifacts(
        "abc",
        "# Report\n\nÇalışma\n",
        [{"id": "E1", "kind": "dataset", "key": "tb_credit"}],
        {"claims": []},
        {"tb_credit": "print(1)\n", "tb_pol": "print(2)\n"},
    )
    folder = root / "abc"
    assert store.load_report("abc") == "# Report\n\nÇalışma\n"
    assert json.loads((folder / "ledger.json").read_text(encoding="utf-8")) == [{"id": "E1", "kind": "dataset", "key": "tb_credit"}]
    assert json.loads((folder / "analysis.json").read_text(encoding="utf-8")) == {"claims": []}
    assert (folder / "scripts" / "tb_credit.py").read_text(encoding="utf-8") == "print(1)\n"
    assert (folder / "scripts" / "tb_pol.py").read_text(encoding="utf-8") == "print(2)\n"


def test_the_ledger_is_read_back_and_a_missing_one_is_none():
    assert store.load_ledger("abc") is None
    store.save_artifacts("abc", "r", [{"id": "E1", "note": "Çalışma"}], {}, {})
    assert store.load_ledger("abc") == [{"id": "E1", "note": "Çalışma"}]


def test_a_dataset_key_cannot_escape_the_scripts_folder(root):
    with pytest.raises(store.CampaignStoreError, match="dataset key"):
        store.save_artifacts("abc", "r", [], {}, {"../../evil": "x"})
    assert not (root / "evil.py").exists()


def test_non_ascii_text_is_stored_readably_in_the_json_files(root):
    store.save_artifacts("abc", "r", [{"id": "E1", "note": "Çalışma"}], {"claim": "Ağaçlar üstün"}, {})
    assert "Çalışma" in (root / "abc" / "ledger.json").read_text(encoding="utf-8")
    assert "Ağaçlar üstün" in (root / "abc" / "analysis.json").read_text(encoding="utf-8")


def test_files_are_written_with_unix_line_endings(root):
    store.save_artifacts("abc", "a\nb\n", [], {}, {})
    assert b"\r" not in (root / "abc" / "report.md").read_bytes()


def test_a_failed_write_leaves_no_temporary_file(root, monkeypatch):
    def broken(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", broken)
    with pytest.raises(OSError, match="disk full"):
        store.save_state("abc", {"status": "running"})
    assert list((root / "abc").iterdir()) == []
    assert store.load_state("abc") is None


def test_campaigns_are_listed_only_when_they_have_a_state(root):
    store.save_state("b", {"status": "queued"})
    store.save_state("a", {"status": "queued"})
    (root / "empty").mkdir()
    assert store.list_campaigns() == ["a", "b"]


def test_nothing_is_listed_before_the_first_campaign():
    assert store.list_campaigns() == []


def test_concurrent_saves_never_leave_a_half_written_state(root):
    def writer(number):
        for step in range(20):
            store.save_state("abc", {"status": "running", "writer": number, "step": step, "padding": "x" * 5000})

    threads = [threading.Thread(target=writer, args=(number,)) for number in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    state = store.load_state("abc")
    assert state["status"] == "running" and len(state["padding"]) == 5000
    assert [item.name for item in (root / "abc").iterdir()] == ["state.json"]


def test_a_busy_target_is_retried_until_it_is_free(root, monkeypatch):
    real = store.os.replace
    calls = []

    def busy_twice(source, destination):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError("in use")
        return real(source, destination)

    monkeypatch.setattr(store.os, "replace", busy_twice)
    monkeypatch.setattr(store, "REPLACE_PAUSE_SECONDS", 0)
    store.save_state("abc", {"status": "running"})
    assert len(calls) == 3
    assert store.load_state("abc")["status"] == "running"


def test_a_target_that_stays_busy_ends_in_the_error_and_no_temporary_file(root, monkeypatch):
    monkeypatch.setattr(store.os, "replace", lambda source, destination: (_ for _ in ()).throw(PermissionError("in use")))
    monkeypatch.setattr(store, "REPLACE_PAUSE_SECONDS", 0)
    with pytest.raises(PermissionError):
        store.save_state("abc", {"status": "running"})
    assert list((root / "abc").iterdir()) == []


def test_a_busy_state_file_is_read_again(root, monkeypatch):
    store.save_state("abc", {"status": "running"})
    real = store.Path.read_text
    calls = []

    def busy_once(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("in use")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(store.Path, "read_text", busy_once)
    monkeypatch.setattr(store, "REPLACE_PAUSE_SECONDS", 0)
    assert store.load_state("abc")["status"] == "running"
    assert len(calls) == 2
