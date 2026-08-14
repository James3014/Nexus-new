import json
from pathlib import Path

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
        "\n".join([
            "| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |",
            "| :--- | :--- | :--- | :--- | :--- |",
            "| nexus/core | tests/core, tests/test_core_*.py | active | high | core_contract |",
            "| nexus/legacy | tests/legacy | retired | low | legacy |",
        ]),
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


def test_issue153_event_feedback_rows_map_without_fallback():
    rules = load_impact_rules()
    details = select_target_details(
        ["nexus/events/log_store.py", "nexus/events/transport.py", "nexus/feedback/contracts.py"],
        rules,
        index_path=Path("/tmp/missing-issue153-impact-index.json"),
        history_path=Path("/tmp/missing-issue153-history.jsonl"),
    )

    assert details.targets == [
        "tests/events",
        "tests/core/test_event_bus.py",
        "tests/architecture/test_boundaries_v4.py",
        "tests/unit/evaluation/test_policy_delta.py",
        "tests/unit/committee/test_data_flow_v267.py",
        "tests/architecture/test_boundaries_v3.py",
        "tests/services/test_policy_gate.py",
    ]
    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.risk == "high"
    assert details.risk_reasons == [
        "event_store_and_transport_contract",
        "developer_feedback_contract",
    ]


def test_worker_registry_contract_maps_exact_targets_without_fallback():
    details = select_target_details(
        ["nexus/executors/worker_registry.py"],
        load_impact_rules(),
        index_path=Path("/tmp/missing-worker-registry-impact-index.json"),
        history_path=Path("/tmp/missing-worker-registry-history.jsonl"),
    )

    assert details.targets == [
        "tests/nexus/executors/test_worker_contract.py",
        "tests/services/test_agy_account_pool.py",
        "tests/services/test_policy_gate.py",
    ]
    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.risk == "high"
    assert details.high_risk_escalated is True
    assert details.risk_reasons == ["worker_registry_contract"]


def test_unrelated_worker_registry_path_remains_fallback():
    details = select_target_details(
        ["nexus/executors/worker_registry_unknown.py"],
        load_impact_rules(),
        index_path=Path("/tmp/missing-worker-registry-impact-index.json"),
        history_path=Path("/tmp/missing-worker-registry-history.jsonl"),
    )

    assert details.fallback_used is True
    assert details.unmatched_paths == ["nexus/executors/worker_registry_unknown.py"]


def test_issue153_feedback_row_maps_exact_targets_without_fallback():
    rules = load_impact_rules()
    details = select_target_details(
        ["nexus/feedback/contracts.py"],
        rules,
        index_path=Path("/tmp/missing-issue153-impact-index.json"),
        history_path=Path("/tmp/missing-issue153-history.jsonl"),
    )

    assert details.targets == [
        "tests/events",
        "tests/unit/evaluation/test_policy_delta.py",
        "tests/unit/committee/test_data_flow_v267.py",
        "tests/architecture/test_boundaries_v3.py",
        "tests/architecture/test_boundaries_v4.py",
        "tests/services/test_policy_gate.py",
    ]
    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.risk == "high"
    assert details.risk_reasons == ["developer_feedback_contract"]


def test_issue153_unrelated_event_path_remains_fallback():
    rules = load_impact_rules()
    targets, reasons = select_targets(
        ["nexus/events_unknown/transport.py"],
        rules,
        fallback_targets=("tests/ops/test_select_tests.py",),
    )

    assert targets == ["tests/ops/test_select_tests.py"]
    assert reasons == ["nexus/events_unknown/transport.py: fallback"]


def test_issue153_unknown_feedback_path_remains_fallback():
    rules = load_impact_rules()
    targets, reasons = select_targets(
        ["nexus/feedback_unknown/foo.py"],
        rules,
        fallback_targets=("tests/ops/test_select_tests.py",),
    )

    assert targets == ["tests/ops/test_select_tests.py"]
    assert reasons == ["nexus/feedback_unknown/foo.py: fallback"]


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


def test_skill_descriptors_select_artifact_catalog_and_trust_contracts(tmp_path):
    rules = load_impact_rules()
    expected = [
        "tests/ops/test_skill_file_contract.py",
        "tests/learning/test_skill_catalog.py",
        "tests/learning/test_skill_schema.py",
        "tests/ops/test_ci_gate_report_trust_audit.py",
        "tests/services/test_policy_gate.py",
    ]

    for path in (
        ".agents/skills/example/SKILL.md",
        ".agents/skills/example/agents/openai.yaml",
    ):
        details = select_target_details(
            [path],
            rules,
            index_path=tmp_path / "missing-index.json",
            stats_path=tmp_path / "missing-stats.json",
            history_path=tmp_path / "missing-history.jsonl",
        )
        assert details.targets == expected
        assert details.risk == "high"
        assert details.fallback_used is False
        assert details.unmatched_paths == []
        assert details.risk_reasons == ["skill_artifact_contract_and_catalog_governance"]


def test_unrelated_agents_path_remains_fail_closed_fallback(tmp_path):
    details = select_target_details(
        [".agents/other/config.yaml"],
        load_impact_rules(),
        index_path=tmp_path / "missing-index.json",
        stats_path=tmp_path / "missing-stats.json",
        history_path=tmp_path / "missing-history.jsonl",
    )

    assert details.fallback_used is True
    assert details.unmatched_paths == [".agents/other/config.yaml"]


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


def test_issue_86_pr_cleanup_surfaces_resolve_to_intended_targets(tmp_path):
    rules = load_impact_rules()
    issue_86_paths = [
        "scripts/brain_de_entropy.py",
        "scripts/core/migration_validator.py",
        "scripts/core/drclaw_diagnosis.py",
        "muse_nexus.egg-info/SOURCES.txt",
    ]

    details = select_target_details(
        issue_86_paths,
        rules,
        index_path=tmp_path / "missing_impact_index.json",
        stats_path=tmp_path / "missing_impact_stats.json",
        history_path=tmp_path / "missing_test_history.jsonl",
    )

    assert details.unmatched_paths == []
    assert details.fallback_used is False

    targets = details.targets
    assert "tests/core/test_context_hub_strict_deps.py" in targets
    assert "tests/core/test_context_budget_sources.py" in targets
    assert "tests/core/test_context_text_store.py" in targets
    assert "tests/core/test_migration_validator_contract.py" in targets
    assert "tests/benchmark/test_drclaw_diagnosis_contract.py" in targets
    assert "tests/ops/test_source_inventory_integrity.py" in targets


def test_default_impact_map_covers_new_learning_modules_without_shadowing_specific_rules(tmp_path):
    rules = load_impact_rules()

    new_details = select_target_details(
        ["nexus/learning/new_contract.py"],
        rules,
        index_path=tmp_path / "missing_impact_index.json",
        stats_path=tmp_path / "missing_impact_stats.json",
        history_path=tmp_path / "missing_test_history.jsonl",
    )
    specific_details = select_target_details(
        ["nexus/learning/skill_registry.py"],
        rules,
        index_path=tmp_path / "missing_impact_index.json",
        stats_path=tmp_path / "missing_impact_stats.json",
        history_path=tmp_path / "missing_test_history.jsonl",
    )
    unknown_details = select_target_details(
        ["nexus/unknown_subsystem/new.py"],
        rules,
        index_path=tmp_path / "missing_impact_index.json",
        stats_path=tmp_path / "missing_impact_stats.json",
        history_path=tmp_path / "missing_test_history.jsonl",
    )

    assert "tests/learning" in new_details.targets
    assert new_details.high_risk_escalated is True
    assert "learning_contract" in new_details.risk_reasons
    assert new_details.unmatched_paths == []

    assert "tests/learning" not in specific_details.targets
    assert (
        "nexus/learning/skill_registry.py: matched nexus/learning/skill_registry.py"
        in specific_details.reasons
    )

    assert unknown_details.fallback_used is True
    assert "tests/learning" not in unknown_details.targets


def test_model_workforce_policy_uses_exact_contract_targets_without_fallback(tmp_path):
    rules = load_impact_rules()
    workforce_rule = next(
        rule for rule in rules if rule.code_path == "nexus/config/model_workforce.yaml"
    )
    details = select_target_details(
        ["nexus/config/model_workforce.yaml"],
        rules,
        index_path=tmp_path / "missing_impact_index.json",
        stats_path=tmp_path / "missing_impact_stats.json",
        history_path=tmp_path / "missing_test_history.jsonl",
    )

    assert details.targets == [
        "tests/contracts/test_model_workforce_policy.py",
        "tests/services/test_model_workforce_policy_loader.py",
    ]
    assert workforce_rule.risk_reason == "workforce_policy_contract"
    assert details.risk == "medium"
    assert details.high_risk_escalated is False
    assert details.fallback_used is False
    assert details.unmatched_paths == []


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
        json.dumps({
            "version": 1,
            "mappings": {
                "nexus/core/state.py": ["tests/core/test_state.py"],
            },
        }),
        encoding="utf-8",
    )
    rules = [ImpactRule("nexus/core", ("tests/core",), "active", "high", "core_contract")]

    details = select_target_details(
        ["nexus/core/state.py"],
        rules,
        index_path=index_path,
        history_path=tmp_path / "missing.jsonl",
    )

    assert details.targets == [
        "tests/core/test_state.py",
        "tests/core",
        "tests/services/test_policy_gate.py",
    ]
    assert details.confidence == 0.85
    assert details.risk == "high"
    assert details.risk_reasons == ["core_contract"]
    assert details.sources == ["import_index", "impact_map", "high_risk"]
    assert "nexus/core/state.py: import-index" in details.reasons


def test_select_target_details_does_not_fallback_when_import_index_matches(tmp_path):
    index_path = tmp_path / "test_impact_index.json"
    index_path.write_text(
        json.dumps({
            "version": 1,
            "mappings": {"nexus/new_module.py": ["tests/test_new_module.py"]},
        }),
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
        "\n".join([
            json.dumps({"targets": ["tests/a.py"], "success": True, "duration_sec": 2.0}),
            json.dumps({"targets": ["tests/a.py"], "success": False, "duration_sec": 4.0}),
            json.dumps({
                "targets": ["tests/b.py"],
                "success": True,
                "target_durations": {"tests/b.py": 1.0},
            }),
        ]),
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
        "\n".join([
            json.dumps({"targets": ["tests/core/slow.py"], "success": True, "duration_sec": 10.0}),
            json.dumps({"targets": ["tests/core/flaky.py"], "success": False, "duration_sec": 1.0}),
            json.dumps({"targets": ["tests/core/flaky.py"], "success": True, "duration_sec": 1.0}),
        ]),
        encoding="utf-8",
    )
    rules = [
        ImpactRule(
            "nexus/core",
            ("tests/core/slow.py", "tests/core/flaky.py"),
            "active",
            "high",
            "core_contract",
        )
    ]

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
        json.dumps({
            "version": 1,
            "mappings": {"nexus/core/state.py": ["tests/core/test_state.py"]},
        }),
        encoding="utf-8",
    )

    assert (
        main([
            "--impact-map",
            str(impact_map),
            "--impact-index",
            str(index_path),
            "--test-history",
            str(tmp_path / "missing.jsonl"),
            "--json",
            "nexus/core/state.py",
        ])
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["targets"] == [
        "tests/core/test_state.py",
        "tests/core",
        "tests/services/test_policy_gate.py",
    ]
    assert payload["confidence"] == 0.85
    assert payload["risk"] == "high"
    assert payload["risk_reasons"] == ["core_contract"]
    assert payload["sources"] == ["import_index", "impact_map", "high_risk"]
    assert payload["selected_count"] == 3
    assert payload["fallback_used"] is False
    assert payload["high_risk_escalated"] is True
    assert payload["unmatched_paths"] == []
    assert payload["retry_recommended"] == []
