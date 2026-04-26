import json

from scripts.ops.select_tests import ImpactRule, load_impact_rules, main, select_target_details, select_targets


def test_load_impact_rules_reads_active_markdown_rows(tmp_path):
    impact_map = tmp_path / "test_impact_map.md"
    impact_map.write_text(
        "\n".join(
            [
                "| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 |",
                "| :--- | :--- | :--- |",
                "| nexus/core | tests/core, tests/test_core_*.py | active |",
                "| nexus/legacy | tests/legacy | retired |",
            ]
        ),
        encoding="utf-8",
    )

    rules = load_impact_rules(impact_map)

    assert rules == [
        ImpactRule(
            code_path="nexus/core",
            targets=("tests/core", "tests/test_core_*.py"),
            status="active",
        )
    ]


def test_select_targets_prefers_most_specific_prefix_and_deduplicates_targets():
    rules = [
        ImpactRule("nexus/core", ("tests/core", "tests/shared"), "active"),
        ImpactRule("nexus/core/policy", ("tests/core/policy", "tests/shared"), "active"),
        ImpactRule("nexus/core/policy", ("tests/core/policy-extra",), "active"),
    ]

    targets, reasons = select_targets(["nexus/core/policy/gate.py"], rules)

    assert targets == ["tests/core/policy", "tests/shared", "tests/core/policy-extra"]
    assert reasons == [
        "nexus/core/policy/gate.py: matched nexus/core/policy",
        "nexus/core/policy/gate.py: matched nexus/core/policy",
    ]


def test_select_targets_adds_fallback_for_unmapped_mixed_changes():
    rules = [ImpactRule("nexus/core", ("tests/core",), "active")]

    targets, reasons = select_targets(
        ["nexus/core/state.py", "docs/testing/test_runbook.md"],
        rules,
        fallback_targets=("tests/smoke",),
    )

    assert targets == ["tests/core", "tests/smoke"]
    assert reasons == [
        "nexus/core/state.py: matched nexus/core",
        "docs/testing/test_runbook.md: fallback",
    ]


def test_select_targets_uses_fallback_when_no_paths_match():
    targets, reasons = select_targets(
        ["nexus/app/flow.py"],
        [ImpactRule("nexus/core", ("tests/core",), "active")],
        fallback_targets=("tests/smoke",),
    )

    assert targets == ["tests/smoke"]
    assert reasons == ["nexus/app/flow.py: fallback"]


def test_select_targets_drops_unmatched_globs():
    targets, _ = select_targets(
        ["nexus/core/state.py"],
        [ImpactRule("nexus/core", ("tests/core", "tests/no_such_*.py"), "active")],
        fallback_targets=("tests/smoke",),
    )

    assert targets == ["tests/core"]


def test_main_emits_json_payload(tmp_path, capsys):
    impact_map = tmp_path / "test_impact_map.md"
    impact_map.write_text(
        "| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 |\n"
        "| :--- | :--- | :--- |\n"
        "| nexus/engine | tests/engine | active |\n",
        encoding="utf-8",
    )

    assert main(["--impact-map", str(impact_map), "--json", "nexus/engine/foo.py"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["targets"] == ["tests/engine"]
    assert payload["rules_loaded"] == 1


def test_select_target_details_merges_import_index_and_impact_map(tmp_path):
    index_path = tmp_path / "test_impact_index.json"
    index_path.write_text(
        json.dumps(
            {
                "version": 1,
                "mappings": {
                    "nexus/core/state.py": ["tests/core/test_state.py"],
                },
            }
        ),
        encoding="utf-8",
    )
    rules = [ImpactRule("nexus/core", ("tests/core",), "active")]

    details = select_target_details(["nexus/core/state.py"], rules, index_path=index_path)

    assert details.targets == ["tests/core/test_state.py", "tests/core"]
    assert details.confidence == 0.9
    assert details.risk == "low"
    assert details.sources == ["import_index", "impact_map"]
    assert "nexus/core/state.py: import-index" in details.reasons


def test_select_target_details_does_not_fallback_when_import_index_matches(tmp_path):
    index_path = tmp_path / "test_impact_index.json"
    index_path.write_text(
        json.dumps({"version": 1, "mappings": {"nexus/new_module.py": ["tests/test_new_module.py"]}}),
        encoding="utf-8",
    )

    details = select_target_details(["nexus/new_module.py"], [], index_path=index_path)

    assert details.targets == ["tests/test_new_module.py"]
    assert details.confidence == 0.9
    assert details.risk == "low"
    assert details.sources == ["import_index"]


def test_select_target_details_handles_empty_changed_paths():
    details = select_target_details([], [], fallback_targets=("tests/smoke",))

    assert details.targets == ["tests/smoke"]
    assert details.confidence == 0.4
    assert details.risk == "high"
    assert details.sources == ["fallback"]


def test_main_json_includes_selection_metadata(tmp_path, capsys):
    impact_map = tmp_path / "test_impact_map.md"
    impact_map.write_text(
        "| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 |\n"
        "| :--- | :--- | :--- |\n"
        "| nexus/core | tests/core | active |\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "test_impact_index.json"
    index_path.write_text(
        json.dumps({"version": 1, "mappings": {"nexus/core/state.py": ["tests/core/test_state.py"]}}),
        encoding="utf-8",
    )

    assert main(
        [
            "--impact-map",
            str(impact_map),
            "--impact-index",
            str(index_path),
            "--json",
            "nexus/core/state.py",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["targets"] == ["tests/core/test_state.py", "tests/core"]
    assert payload["confidence"] == 0.9
    assert payload["risk"] == "low"
    assert payload["sources"] == ["import_index", "impact_map"]
