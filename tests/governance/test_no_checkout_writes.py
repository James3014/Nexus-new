"""The governance conftest guard flags writes into the checkout (cairnwork#209)."""


def test_checkout_guard_flags_new_and_modified_nexus_files(tmp_path, checkout_guard_helpers):
    snapshot, changes = checkout_guard_helpers
    (tmp_path / ".nexus").mkdir()
    tracked = tmp_path / ".nexus" / "test_impact_index.json"
    tracked.write_text("{}")
    before = snapshot(tmp_path)
    assert changes(before, snapshot(tmp_path)) == []

    (tmp_path / ".nexus" / "events").mkdir()
    (tmp_path / ".nexus" / "events" / "learning_loop.jsonl").write_text("{}\n")
    tracked.write_text('{"changed": true}')
    assert changes(before, snapshot(tmp_path)) == [
        ".nexus/events/learning_loop.jsonl",
        ".nexus/test_impact_index.json",
    ]


def test_checkout_guard_flags_new_top_level_entries(tmp_path, checkout_guard_helpers):
    snapshot, changes = checkout_guard_helpers
    before = snapshot(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "stray.log").write_text("x")
    assert changes(before, snapshot(tmp_path)) == ["stray.log"]
