# pyright: reportOptionalMemberAccess=false, reportMissingImports=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false
"""Capability wiring audit: verdict logic on synthetic receipts and two real end-to-end runs.

The end-to-end tests drive ``mempalace_gate`` and ``sandbox`` through the production chain
(CapabilityPlanner -> run_mainchain -> UnifiedRuntime -> registry invoker -> executor) on the
tracked fixtures; neither needs a model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.ops import capability_wiring_audit as audit


def _passing_obs(**overrides: Any) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "selected": True,
        "status": "SUCCEEDED",
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": ["ev_cap_x_1"],
        "checks": [{"name": "effect", "passed": True, "detail": ""}],
    }
    obs.update(overrides)
    return obs


def test_real_requires_evidence_and_passing_artifact_assertions() -> None:
    verdict, reason = audit.classify_verdict(_passing_obs())
    assert verdict == audit.REAL
    assert "artifact_assertions_passed" in reason


def test_simulated_flag_default_yields_real_unattested() -> None:
    """The ClaimBoundary default (simulated=True) cannot discriminate; the artifact decides."""
    verdict, _ = audit.classify_verdict(_passing_obs(receipt_claims_simulated=True))
    assert verdict == audit.REAL_UNATTESTED
    assert audit.classify_verdict(_passing_obs(receipt_claims_simulated=False))[0] == audit.REAL
    assert (
        audit.classify_verdict(_passing_obs(receipt_claims_simulated=True, stub=True))[0]
        == audit.STUB
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"hard_coded": [{"pattern": '"id": "c0"', "file": "x.py", "line": 3}]}, audit.SIMULATED),
        ({"fixture_provider": True}, audit.SIMULATED),
        ({"stub": True}, audit.STUB),
        ({"input_insensitive": True}, audit.STUB),
        ({"checks": [{"name": "effect", "passed": False, "detail": "no file"}]}, audit.STUB),
        ({"evidence_refs": []}, audit.STUB),
        ({"checks": []}, audit.STUB),
    ],
)
def test_synthetic_receipts_that_pass_the_gate_without_an_effect(
    overrides: dict[str, Any], expected: str
) -> None:
    verdict, _ = audit.classify_verdict(_passing_obs(**overrides))
    assert verdict == expected


def test_hard_coded_reason_names_the_location() -> None:
    _, reason = audit.classify_verdict(
        _passing_obs(hard_coded=[{"pattern": "c0", "file": "reg.py", "line": 12}])
    )
    assert reason.endswith("c0@reg.py:12")


def test_blocked_keeps_exact_reason_without_double_prefix() -> None:
    verdict, _ = audit.classify_verdict({
        "selected": True,
        "status": "BLOCKED",
        "gate_passed": False,
        "block_reason": "BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution",
    })
    assert verdict == "BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution"
    verdict, _ = audit.classify_verdict({
        "selected": True,
        "status": "BLOCKED",
        "gate_passed": False,
        "block_reason": "TARGET_SYMBOL_REQUIRED",
    })
    assert verdict == "BLOCKED_TARGET_SYMBOL_REQUIRED"


def test_skip_receipt_is_blocked_not_real() -> None:
    verdict, _ = audit.classify_verdict({
        "selected": True,
        "status": "SKIPPED",
        "skip_reason": "SKIPPED_POLICY_NOT_TRIGGERED",
        "gate_passed": True,
    })
    assert verdict == "BLOCKED_SKIPPED_POLICY_NOT_TRIGGERED"


def test_gate_failure_on_a_valid_fixture_is_blocked() -> None:
    verdict, reason = audit.classify_verdict({
        "selected": True,
        "status": "FAILED",
        "gate_passed": False,
        "invoked": True,
        "checks": [{"name": "effect", "passed": False, "detail": "exit 3"}],
    })
    assert verdict.startswith("BLOCKED_")
    assert "exit 3" in reason


def test_unreached_capability_reports_the_admission_reason() -> None:
    verdict, _ = audit.classify_verdict({
        "selected": True,
        "status": "MISSING",
        "block_reason": "workforce_admission_blocked: role mismatch",
    })
    assert verdict == "BLOCKED_workforce_admission_blocked: role mismatch"


def test_terminal_non_runtime_verdicts() -> None:
    assert audit.classify_verdict({"retiring": "archive PR"})[0] == audit.RETIRING
    assert (
        audit.classify_verdict({"selected": False, "not_selectable_reason": "tier_cost_control"})[0]
        == audit.NOT_SELECTABLE
    )
    assert (
        audit.classify_verdict({
            "selected": True,
            "model_required": True,
            "model_available": False,
        })[0]
        == audit.MODEL_UNAVAILABLE
    )


def test_obs_normalization_distinguishes_blocked_from_real_stage() -> None:
    real_stage = {
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": ["ev1"],
        "physical_callable": "capability_executor_registry:codeintel",
        "response": {"stub": False, "response": {"outcome": {"found": True}}},
    }
    obs = audit.make_obs("codeintel", source="e2e", stage=real_stage)
    assert obs.status() == "SUCCEEDED" and obs.outcome == {"found": True}
    blocked_stage = {
        "invoked": True,
        "gate_passed": False,
        "evidence_refs": ["ev2"],
        "response": {
            "reason": "execution_contract_violation",
            "response": {
                "contract_violations": ["missing_outcome_field:semantic_status"],
                "outcome": {},
            },
        },
    }
    blocked = audit.make_obs("hyper", source="e2e", stage=blocked_stage)
    assert blocked.status() == "BLOCKED"
    assert (
        blocked.block_reason()
        == "execution_contract_violation:missing_outcome_field:semantic_status"
    )
    assert audit.make_obs("x", source="e2e", stage=None).status() == "MISSING"


def test_default_flags_detect_stub_and_fixture_provider() -> None:
    stub = audit.make_obs(
        "c",
        source="e2e",
        stage={
            "invoked": True,
            "gate_passed": True,
            "physical_callable": "capability_registry.structural_stub:c",
            "response": {"stub": True},
        },
    )
    assert audit.default_flags(stub)["stub"] is True
    fixture = audit.make_obs(
        "local_model_executor",
        source="e2e",
        stage={
            "invoked": True,
            "gate_passed": True,
            "physical_callable": "LocalModelExecutor.run",
            "response": {"response": {"source": "fixture_local_provider"}},
        },
    )
    assert audit.default_flags(fixture)["fixture_provider"] is True


def test_scan_hard_coded_finds_literal_in_executor_source() -> None:
    from nexus.core.capability_executor_registry import _exec_ddtree

    found = audit.scan_hard_coded(_exec_ddtree, ["_candidate_pool(plan)", "pattern-that-is-absent"])
    assert [item["pattern"] for item in found] == ["_candidate_pool(plan)"]
    assert found[0]["line"] > 0 and found[0]["file"].endswith("capability_executor_registry.py")


def test_every_scope_capability_has_a_spec_or_is_marked_retiring() -> None:
    required = {
        "codeintel",
        "research",
        "research_route",
        "hyper",
        "nightshift",
        "swarm",
        "multi_agent",
        "drone",
        "ultra_review",
        "autoreason",
        "ddtree",
        "lancedb",
        "memory",
        "mempalace_gate",
        "belief",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "acceptance_check",
        "pregate",
        "forecast_gate",
        "plan_quality_gate",
        "sandbox",
        "harness_preflight_sensor",
        "repair_loop",
        "local_model_executor",
        "committee",
        "xray",
        "metabolism",
        "meta_opt",
    }
    assert required <= set(audit.SPECS)
    assert {
        "federation",
        "oracle_shadow",
        "stress_test",
        "ui_validator",
        "benchmark",
        "learning_closure",
        # second archive batch (ARCHIVED_2026-10-13.md, #1906)
        *ARCHIVED_2026_10_13_NODES,
    } == set(audit.RETIRING_CAPABILITIES)
    assert not set(audit.SPECS) & set(audit.RETIRING_CAPABILITIES)
    for spec in audit.SPECS.values():
        if spec.fixture:
            assert (audit.FIXTURE_ROOT / spec.fixture).is_dir(), spec.fixture


def test_model_probe_never_raises_when_the_endpoint_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audit, "OLLAMA_URL", "http://127.0.0.1:9")
    probe = audit.probe_model(timeout=0.3)
    assert probe["available"] is False and probe["reason"]


def test_markdown_table_lists_every_row() -> None:
    rows = [
        {
            "capability": "a",
            "verdict": "REAL",
            "executor": {
                "function": "_exec_a",
                "file": "f.py",
                "line": 3,
                "reached_via": "EXECUTOR_REGISTRY",
            },
            "receipt_claims_simulated": True,
        },
        {"capability": "b", "verdict": "RETIRING", "executor": {}, "verdict_reason": "archive"},
    ]
    table = audit.markdown_table(rows)
    assert "_exec_a @ f.py:3" in table and "| b | RETIRING" in table


@pytest.fixture(scope="module")
def e2e_matrix(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    out_root = tmp_path_factory.mktemp("wiring_audit")
    matrix = audit.run_audit(
        ["mempalace_gate", "sandbox", "federation"], out_root, allow_model=False, smoke_summary=None
    )
    return {
        "matrix": matrix,
        "rows": {row["capability"]: row for row in matrix["rows"]},
        "out": Path(matrix["_out_dir"]),
    }


def test_end_to_end_mempalace_gate_blocks_the_blacklisted_tool(e2e_matrix: dict[str, Any]) -> None:
    row = e2e_matrix["rows"]["mempalace_gate"]
    assert row["verdict"] == audit.REAL, row.get("checks")
    assert row["path"] == "e2e" and row["product_path_reachable"] is True
    by_name = {check["name"]: check for check in row["checks"]}
    assert by_name["roundtrip_verified"]["passed"] and by_name["shard_written_to_disk"]["passed"]
    control = row["negative_control"]
    assert (
        control["passed"] is True
        and control["name"] == "negative_control:blacklisted_tool_is_blocked"
    )
    assert row["executor"]["function"] == "_exec_mempalace" and row["executor"]["line"] > 0


def test_end_to_end_sandbox_returns_stdout_from_an_isolated_workspace(
    e2e_matrix: dict[str, Any],
) -> None:
    row = e2e_matrix["rows"]["sandbox"]
    assert row["verdict"] == audit.REAL, row.get("checks")
    by_name = {check["name"]: check for check in row["checks"]}
    assert (
        by_name["stdout_token_in_result_file"]["passed"]
        and by_name["workspace_isolated_copy"]["passed"]
    )
    assert row["untriggered_production_default"]["skip_reason"] == "SKIPPED_POLICY_NOT_TRIGGERED"
    assert row["trigger_switch"]
    assert row["negative_control"]["passed"] is True


def test_end_to_end_records_flag_receipts_and_retiring_rows(e2e_matrix: dict[str, Any]) -> None:
    matrix, rows, out = e2e_matrix["matrix"], e2e_matrix["rows"], e2e_matrix["out"]
    # the audit reads the Nexus-side attested receipt (invoked + evidence refs => simulated=false)
    assert rows["mempalace_gate"]["receipt_claims_simulated"] is False
    assert rows["federation"]["verdict"] == audit.RETIRING
    saved = json.loads((out / "matrix.json").read_text(encoding="utf-8"))
    assert saved["schema"] == audit.SCHEMA and {r["capability"] for r in saved["rows"]} == {
        "mempalace_gate",
        "sandbox",
        "federation",
    }
    assert (out / "receipts" / "sandbox.json").is_file() and (out / "matrix.md").is_file()
    assert matrix["verdict_counts"].get("REAL") == 2


def test_route_smoke_row_validator_ignores_the_simulated_flag(tmp_path: Path) -> None:
    result = audit.smoke_probe(tmp_path)
    assert result["passes_on_simulated_receipts"] is True
    assert result["synthetic_row_failures"] == []
    assert all(count == 0 for count in result["mentions_of_simulated_in_validators"].values())


# --------------------------------------------- 2026-10-13 extension: every planner node


# Planner nodes archived 2026-10-13: the audit reports them RETIRING with the archived skip reason.
ARCHIVED_2026_10_13_NODES = {
    "integration_manager": "archived_retired_integration_manager_2026-10-13",
    "swarm_quiet_moment": "archived_echo_swarm_quiet_moment_2026-10-13",
    "llm_judge_panel": "archived_alias_llm_judge_panel_2026-10-13",
    # legacy-engine batch (ARCHIVED_2026-10-13-legacy-engine.md)
    "autonomic_router": "archived_legacy_engine_autonomic_router_2026-10-13",
}

EXTENSION_NODES = {
    "semantic_failure_sensor",
    "bdd_acceptance_skill",
    "jit_validation",
    "semantic_searcher",
    "prompt_compression",
    "asi_constraint_extractor",
    "architecture_scout",
    "formal_report",
    "learn_mode",
    "learn_phase_slo",
    "file_lock",
    "direct_mode",
    "msa_router",
    "research_control_plane",
    "swarm_quiet_moment",
    "integration_manager",
    "autonomic_router",
    "judge_panel",
    "llm_judge_panel",
    "external_doc_scout",
    "learn_scheduler",
    "registry_sync",
}


def test_every_pinned_planner_node_has_a_spec_or_is_retiring() -> None:
    from nexus.services.capability_registry import list_planner_capability_names

    planner = set(list_planner_capability_names())
    covered = set(audit.SPECS) | set(audit.RETIRING_CAPABILITIES)
    assert planner - covered == set()
    assert EXTENSION_NODES - set(ARCHIVED_2026_10_13_NODES) <= set(audit.SPECS)
    assert set(ARCHIVED_2026_10_13_NODES) <= set(audit.RETIRING_CAPABILITIES)
    assert EXTENSION_NODES <= set(audit.NATURAL_TRIGGERS)
    for cap, reason in ARCHIVED_2026_10_13_NODES.items():
        row = audit.retiring_row(cap, audit.RETIRING_CAPABILITIES[cap])
        assert row["verdict"] == audit.RETIRING
        assert row["archived_skip_reason"] == reason


def test_not_executable_specs_are_exactly_the_nodes_without_a_runnable_callable() -> None:
    from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
    from nexus.services.capability_registry import PLANNER_EXECUTION_CONTRACTS

    flagged = {cap for cap, spec in audit.SPECS.items() if spec.not_executable}
    assert flagged == {"direct_mode", "msa_router", "research_control_plane", "external_doc_scout"}
    for cap in flagged:
        assert PLANNER_EXECUTION_CONTRACTS[cap]["physical_callable"] is None
    for cap in {"direct_mode", "msa_router", "research_control_plane"}:
        key = PLANNER_EXECUTION_CONTRACTS[cap]["executor_key"]
        assert key not in EXECUTOR_REGISTRY


def test_verdict_bucket_collapses_prefixed_verdicts() -> None:
    assert audit.verdict_bucket("BLOCKED_EXTERNAL_AUTH") == "BLOCKED"
    assert audit.verdict_bucket("NOT_EXECUTABLE:control_plane_reference") == audit.NOT_EXECUTABLE
    assert audit.verdict_bucket(audit.REAL) == audit.REAL


def test_executor_only_keys_are_the_seventeen_unreachable_executors() -> None:
    # Second archive batch (2026-10-13, #1906): all seventeen keys left EXECUTOR_REGISTRY.
    # Node id kept: entropy_guard_v2 got its planner node with the runtime 68e86ed pin
    # (nexus-runtime #198, #1907), so sixteen remain.
    keys = audit.executor_only_keys()
    assert keys["unlisted"] == [] and keys["listed_but_reachable"] == []
    assert set(keys["computed"]) - set(keys["retiring_excluded"]) == set()
    assert set(keys["retired_from_registry"]) == set(audit.EXECUTOR_ONLY)
    assert len(audit.EXECUTOR_ONLY) == 16
    assert "entropy_guard_v2" not in audit.EXECUTOR_ONLY


def test_executor_only_quotes_hard_coded_tmp_lines() -> None:
    # The /tmp-bound executors were archived 2026-10-13; their recorded description keeps the
    # evidence and the registry no longer exposes them.
    from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY

    for key in ("policy_capability_gate", "learn_refresh_service", "reflex_loop"):
        assert key not in EXECUTOR_REGISTRY, key
        literals = audit.EXECUTOR_ONLY[key]["literals"]
        assert any("/tmp" in literal for literal in literals), key


def test_executor_only_direct_invocation_records_outcome(tmp_path: Path) -> None:
    # policy_capability_gate: registry key removed 2026-10-13, module kept (entropy_guard_v2,
    # used here before, got its planner node with the runtime 68e86ed pin, #1907).
    row = audit.audit_executor_only("policy_capability_gate", tmp_path)
    assert row["verdict"] == audit.RETIRING
    assert row["verdict_reason"].startswith(audit.RETIRED_EXECUTOR_ONLY_REASON)
    assert "policy_gate.py" in row["verdict_reason"]
    assert row["invoked"] is None and row["gate_passed"] is None


def test_natural_selection_reports_rules_whose_input_the_seam_drops() -> None:
    msa = audit.natural_selection("msa_router")
    assert msa["selected_without_forcing"] is False
    assert msa["trigger_route_keys_dropped_by_seam"] == ["msa_routing"]
    jit = audit.natural_selection("jit_validation")
    assert jit["selected_without_forcing"] is True and "jit_validation_signal" in jit["reasons"]
    assert audit.natural_selection("learn_scheduler")["selected_without_forcing"] is False


@pytest.fixture(scope="module")
def extension_matrix(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    out_root = tmp_path_factory.mktemp("wiring_audit_ext")
    matrix = audit.run_audit(
        ["file_lock", "learn_mode", "direct_mode", "asi_constraint_extractor"],
        out_root,
        allow_model=False,
        smoke_summary=None,
    )
    return {row["capability"]: row for row in matrix["rows"]}


def test_end_to_end_file_lock_writes_a_lock_and_blocks_without_targets(
    extension_matrix: dict[str, Any],
) -> None:
    row = extension_matrix["file_lock"]
    assert row["verdict"] == audit.REAL, row.get("checks")
    assert row["negative_control"]["passed"] is True
    # one registry per workspace keyed by file: the second task is refused (2026-10-13)
    assert row["component_probe"]["second_task_refused"] is True
    assert row["component_probe"]["holders"] == {"target.py": "lock-task-a"}
    assert row["production_default_selection"]["selected_without_forcing"] is True


def test_end_to_end_learn_mode_ignores_project_claims(extension_matrix: dict[str, Any]) -> None:
    # name kept for the exact-base impact gate; since 2026-10-13 it asserts the store is read
    row = extension_matrix["learn_mode"]
    assert row["verdict"] == audit.REAL, row.get("checks")
    assert row["negative_control"]["passed"] is True
    probe = row["component_probe"]
    assert probe["project_root_report_claims_count"] >= 1
    assert probe["per_task_run_root_claims_count"] == 0


def test_end_to_end_control_plane_node_is_not_executable(extension_matrix: dict[str, Any]) -> None:
    row = extension_matrix["direct_mode"]
    assert row["verdict"] == "NOT_EXECUTABLE:control_plane_reference"
    # Since group D the receipt itself says NOT_EXECUTABLE (explicit skip, never invoked).
    assert "NOT_EXECUTABLE:control_plane_reference" in row["observed_verdict"]
    honest = {c["name"]: c["passed"] for c in row["checks"]}
    assert honest == {"receipt_states_not_executable": True}
    assert row["production_default_selection"]["trigger_route_keys_dropped_by_seam"] == [
        "recommended_flow"
    ]


def test_end_to_end_asi_extractor_depends_on_its_records(extension_matrix: dict[str, Any]) -> None:
    row = extension_matrix["asi_constraint_extractor"]
    assert row["verdict"] == audit.REAL, row.get("checks")
    assert row["negative_control"]["passed"] is True


def test_not_executable_specs_match_the_registry_receipt_reasons() -> None:
    from nexus.services.capability_registry import NOT_EXECUTABLE_CAPABILITY_REASONS

    flagged = {cap: spec.not_executable for cap, spec in audit.SPECS.items() if spec.not_executable}
    assert {cap: f"NOT_EXECUTABLE:{reason}" for cap, reason in flagged.items()} == dict(
        NOT_EXECUTABLE_CAPABILITY_REASONS
    )
