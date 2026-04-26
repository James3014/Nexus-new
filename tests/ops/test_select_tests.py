import json

from scripts.ops.select_tests import ImpactRule, load_impact_rules, main, select_targets


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
