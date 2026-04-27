import json

from scripts.ops.select_tests import (
    ImpactRule,
    load_impact_rules,
    load_test_history,
    main,
    select_target_details,
    select_targets,
)


def test_load_impact_rules_reads_active_markdown_rows(tmp_path):
    impact_map = tmp_path / "test_impact_map.md"
    impact_map.write_text(
        "\n".join(
            [
                "| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |",
                "| :--- | :--- | :--- | :--- | :--- |",
                "| nexus/core | tests/core, tests/test_core_*.py | active | high | core_contract |",
                "| nexus/legacy | tests/legacy | retired | low | legacy |",
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
            risk="high",
            risk_reason="core_contract",
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
    rules = [ImpactRule("nexus/core", ("tests/core",), "active", "high", "core_contract")]

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
    rules = [ImpactRule("nexus/core", ("tests/core",), "active", "high", "core_contract")]

    details = select_target_details(["nexus/core/state.py"], rules, index_path=index_path, history_path=tmp_path / "missing.jsonl")

    assert details.targets == ["tests/core/test_state.py", "tests/core", "tests/services/test_policy_gate.py"]
    assert details.confidence == 0.85
    assert details.risk == "high"
    assert details.risk_reasons == ["core_contract"]
    assert details.sources == ["import_index", "impact_map", "high_risk"]
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
    assert details.risk_reasons == ["fallback"]
    assert details.sources == ["fallback"]
    assert details.fallback_used is True


def test_load_test_history_aggregates_duration_failures_and_flaky(tmp_path):
    history = tmp_path / "test_history.jsonl"
    history.write_text(
        "\n".join(
            [
                json.dumps({"targets": ["tests/a.py"], "success": True, "duration_sec": 2.0}),
                json.dumps({"targets": ["tests/a.py"], "success": False, "duration_sec": 4.0}),
                json.dumps({"targets": ["tests/b.py"], "success": True, "target_durations": {"tests/b.py": 1.0}}),
            ]
        ),
        encoding="utf-8",
    )

    stats = load_test_history(history)

    assert stats["tests/a.py"]["runs"] == 2
    assert stats["tests/a.py"]["failures"] == 1
    assert stats["tests/a.py"]["avg_duration_sec"] == 3.0
    assert stats["tests/a.py"]["flaky"] is True
    assert stats["tests/b.py"]["avg_duration_sec"] == 1.0


def test_select_target_details_uses_history_and_high_risk_escalation(tmp_path):
    history = tmp_path / "test_history.jsonl"
    history.write_text(
        "\n".join(
            [
                json.dumps({"targets": ["tests/core/slow.py"], "success": True, "duration_sec": 10.0}),
                json.dumps({"targets": ["tests/core/flaky.py"], "success": False, "duration_sec": 1.0}),
                json.dumps({"targets": ["tests/core/flaky.py"], "success": True, "duration_sec": 1.0}),
            ]
        ),
        encoding="utf-8",
    )
    rules = [ImpactRule("nexus/core", ("tests/core/slow.py", "tests/core/flaky.py"), "active", "high", "core_contract")]

    details = select_target_details(["nexus/core/state.py"], rules, history_path=history)

    assert details.targets[:2] == ["tests/core/flaky.py", "tests/core/slow.py"]
    assert details.risk == "high"
    assert details.risk_reasons == ["core_contract"]
    assert "high_risk" in details.sources
    assert details.history["tests/core/flaky.py"]["flaky"] is True
    assert "tests/services/test_policy_gate.py" in details.targets
    assert details.retry_recommended == ["tests/core/flaky.py"]
    assert details.high_risk_escalated is True


def test_select_target_details_reports_unmatched_paths_and_fallback(tmp_path):
    details = select_target_details(
        ["docs/testing/unknown.md"],
        [ImpactRule("nexus/core", ("tests/core",), "active")],
        fallback_targets=("tests/smoke",),
        history_path=tmp_path / "missing.jsonl",
    )

    assert details.targets == ["tests/smoke"]
    assert details.unmatched_paths == ["docs/testing/unknown.md"]
    assert details.fallback_used is True
    assert details.high_risk_escalated is False


def test_main_json_includes_selection_metadata(tmp_path, capsys):
    impact_map = tmp_path / "test_impact_map.md"
    impact_map.write_text(
        "| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |\n"
        "| :--- | :--- | :--- | :--- | :--- |\n"
        "| nexus/core | tests/core | active | high | core_contract |\n",
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
            "--test-history",
            str(tmp_path / "missing.jsonl"),
            "--json",
            "nexus/core/state.py",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["targets"] == ["tests/core/test_state.py", "tests/core", "tests/services/test_policy_gate.py"]
    assert payload["confidence"] == 0.85
    assert payload["risk"] == "high"
    assert payload["risk_reasons"] == ["core_contract"]
    assert payload["sources"] == ["import_index", "impact_map", "high_risk"]
    assert payload["selected_count"] == 3
    assert payload["fallback_used"] is False
    assert payload["high_risk_escalated"] is True
    assert payload["unmatched_paths"] == []
    assert payload["retry_recommended"] == []
