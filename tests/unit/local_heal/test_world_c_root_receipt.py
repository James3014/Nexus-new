from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from nexus.contracts.root_receipt import (
    build_root_receipt,
    build_world_c_verifier_projection,
    validate_root_receipt,
)
from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
from nexus.services.local_heal.interface import LocalizedFile, PhaseResult, RepairPlan
from nexus.services.local_heal.pipeline_isolation import prepare_world_c_workspace
from nexus.services.local_heal.world_c_receipt import (
    WORLD_C_STAGES,
    build_world_c_receipt,
    record_world_c_phase_result,
    validate_world_c_receipt,
)


def _context(tmp_path: Path, task_id: str = "world-c-1") -> HealContext:
    isolated = tmp_path / "isolated"
    isolated.mkdir(exist_ok=True)
    op = OperationalContext(
        instance_id=task_id,
        repo_dir=tmp_path,
        problem_statement="repair the bug",
        route_context={
            "planner_decision_id": "plan-1",
            "world_c_source_root": str(tmp_path),
            "world_c_workspace_path": str(isolated),
            "signal_snapshot": {
                "execution_topology": "ISOLATED_TARGET",
                "executor_topology": "localheal_pipeline",
                "execution_world": "local_armor",
                "canonical_execution_topology": "ISOLATED_TARGET",
                "canonical_execution": {"context_hash": "a" * 64},
                "capability_evidence_bundle": {"source_hash": "sha256:source"},
                "planner_decision_id": "plan-1",
            },
        },
    )
    op.task_id = task_id
    return HealContext(op=op, gov=GovernanceContext())


def _complete_world_c(
    tmp_path: Path,
    *,
    execution_world: str = "local_armor",
    canonical_execution_topology: str = "ISOLATED_TARGET",
    canonical_execution_hash: str = "a" * 64,
) -> dict:
    ctx = _context(tmp_path)
    snapshot = ctx.op.route_context["signal_snapshot"]
    snapshot["execution_world"] = execution_world
    snapshot["canonical_execution_topology"] = canonical_execution_topology
    snapshot["canonical_execution"]["context_hash"] = canonical_execution_hash
    for stage in WORLD_C_STAGES:
        _set_stage_evidence(ctx, stage)
        record_world_c_phase_result(ctx, stage, PhaseResult(success=True))
    return build_world_c_receipt(ctx)


def _set_stage_evidence(ctx: HealContext, stage: str) -> None:
    if stage == "reproduction":
        ctx.op.repro_evidence = "reproduced failure"
        ctx.op.reproduced = True
    elif stage == "planning":
        ctx.op.plan = RepairPlan(search_symbols=["target"], repair_strategy="bounded edit")
    elif stage == "localization":
        ctx.op.localized_files = [LocalizedFile(path="target.py", content="value = 1\n")]
    elif stage == "patch_synthesis":
        ctx.op.final_patch = "--- a/target.py\n+++ b/target.py\n@@ -1 +1 @@\n-value=1\n+value=2\n"
    elif stage == "verification":
        ctx.op.evaluation_report = "PASS"
        ctx.op.solve_eligible = True


def _stage(name: str, *, response: dict | None = None) -> dict:
    return {
        "name": name,
        "status": "SUCCEEDED",
        "invoked": True,
        "gate_passed": True,
        "evidence_present": True,
        "evidence_refs": [f"evidence:{name}"],
        "response": dict(response or {}),
    }


def test_world_c_receipt_requires_all_five_physical_stage_results(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    for stage in WORLD_C_STAGES[:-1]:
        _set_stage_evidence(ctx, stage)
        record_world_c_phase_result(ctx, stage, PhaseResult(success=True))

    receipt = build_world_c_receipt(ctx)
    valid, reasons = validate_world_c_receipt(receipt)

    assert valid is False
    assert receipt["receipt_complete"] is False
    assert "verification_not_invoked" in reasons
    assert [stage["name"] for stage in receipt["stages"]] == list(WORLD_C_STAGES)


def test_world_c_workspace_is_copied_before_mutation(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    target = tmp_path / "src" / "target.py"
    target.parent.mkdir()
    target.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored", encoding="utf-8")

    workspace = prepare_world_c_workspace(
        tmp_path,
        "isolation-test",
        target_file="src/target.py",
    )
    isolated_target = workspace / "src" / "target.py"
    isolated_target.write_text("value = 2\n", encoding="utf-8")

    assert target.read_text(encoding="utf-8") == "value = 1\n"
    assert isolated_target.read_text(encoding="utf-8") == "value = 2\n"
    assert not (workspace / ".git").exists()


def test_world_c_receipt_binds_final_verifier_attempt(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    for stage in WORLD_C_STAGES[:-1]:
        _set_stage_evidence(ctx, stage)
        record_world_c_phase_result(ctx, stage, PhaseResult(success=True))
    ctx.op.evaluation_report = "FAIL"
    ctx.op.solve_eligible = False
    record_world_c_phase_result(
        ctx,
        "verify_attempt_1",
        PhaseResult(success=False, failure_reason="assertion failed"),
    )
    ctx.op.evaluation_report = "PASS"
    ctx.op.solve_eligible = True
    record_world_c_phase_result(ctx, "verify_attempt_2", PhaseResult(success=True))

    receipt = build_world_c_receipt(ctx)
    valid, reasons = validate_world_c_receipt(receipt)

    assert valid is True, reasons
    assert receipt["receipt_complete"] is True
    verifier = receipt["stages"][-1]
    assert verifier["attempt_count"] == 2
    assert verifier["final_success"] is True
    assert receipt["execution_world"] == "local_armor"
    assert receipt["canonical_execution_topology"] == "ISOLATED_TARGET"
    assert receipt["canonical_execution_hash"] == "a" * 64
    assert receipt["source_hash"] == "sha256:source"


def test_root_receipt_references_world_c_as_the_single_verifier_source(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    verifier = _stage(
        "verifier",
        response={
            "source": "HealOrchestrator.VerificationPhase",
            "world_c_receipt_hash": world_c["receipt_hash"],
        },
    )
    runtime = {
        "task_id": "world-c-1",
        "workspace_revision": "rev-1",
        "planner_decision_id": "plan-1",
        "canonical_execution": {
            "task_id": "world-c-1",
            "execution_id": "exec-1",
            "execution_world": "local_armor",
            "canonical_execution_topology": "ISOLATED_TARGET",
            "context_hash": "a" * 64,
        },
        "planner": {"planner_decision_id": "plan-1"},
        "workforce_admission": {"aggregate_binding_hash": "sha256:workforce"},
        "capability_evidence_bundle": {"source_hash": "sha256:source"},
        "local": _stage(
            "local",
            response={"local_outputs": {"world_c_receipt": world_c}},
        ),
        "online": {"name": "online", "status": "NOT_REQUESTED"},
        "verifier": verifier,
        "learning": _stage("learning"),
        "capability_results": {
            "claim_gate": _stage("claim_gate"),
            "delivery_gate": {
                "name": "delivery_gate",
                "invoked": True,
                "gate_passed": False,
                "evidence_present": True,
            },
        },
    }

    root = build_root_receipt(runtime)
    valid, reasons = validate_root_receipt(root)

    assert valid is True, reasons
    assert root["receipt_complete"] is True
    assert root["verifier_bound_to_world_c"] is True
    assert root["public_claim_allowed"] is False


def test_root_receipt_rejects_world_c_canonical_identity_tamper(tmp_path: Path) -> None:
    world_c = _complete_world_c(
        tmp_path,
        canonical_execution_topology="ASSISTED_CANONICAL",
        canonical_execution_hash="b" * 64,
    )
    runtime = {
        "task_id": "world-c-1",
        "workspace_revision": "rev-1",
        "planner_decision_id": "plan-1",
        "canonical_execution": {
            "task_id": "world-c-1",
            "execution_id": "exec-1",
            "execution_world": "local_armor",
            "canonical_execution_topology": "ISOLATED_TARGET",
            "context_hash": "a" * 64,
        },
        "planner": {"planner_decision_id": "plan-1"},
        "workforce_admission": {"aggregate_binding_hash": "sha256:workforce"},
        "capability_evidence_bundle": {"source_hash": "sha256:source"},
        "local": _stage("local", response={"local_outputs": {"world_c_receipt": world_c}}),
        "verifier": _stage(
            "verifier",
            response={
                "source": "HealOrchestrator.VerificationPhase",
                "world_c_receipt_hash": world_c["receipt_hash"],
            },
        ),
        "learning": _stage("learning"),
        "capability_results": {},
    }

    root = build_root_receipt(runtime)

    assert root["receipt_complete"] is False
    assert "world_c_canonical_execution_topology_mismatch" in root["missing_evidence"]
    assert "world_c_canonical_execution_hash_mismatch" in root["missing_evidence"]


def test_root_receipt_fails_closed_when_runtime_verifier_is_not_world_c_projection(
    tmp_path: Path,
) -> None:
    world_c = _complete_world_c(tmp_path)
    runtime = {
        "task_id": "world-c-1",
        "workspace_revision": "rev-1",
        "planner_decision_id": "plan-1",
        "canonical_execution": {"task_id": "world-c-1", "execution_id": "exec-1"},
        "planner": {"planner_decision_id": "plan-1"},
        "workforce_admission": {"aggregate_binding_hash": "sha256:workforce"},
        "capability_evidence_bundle": {"source_hash": "sha256:source"},
        "local": _stage(
            "local",
            response={"local_outputs": {"world_c_receipt": world_c}},
        ),
        "online": {"name": "online", "status": "NOT_REQUESTED"},
        "verifier": _stage("verifier", response={"source": "response_contract"}),
        "learning": _stage("learning"),
        "capability_results": {},
    }

    root = build_root_receipt(runtime)
    valid, reasons = validate_root_receipt(root)

    assert valid is False
    assert root["receipt_complete"] is False
    assert "verifier_not_bound_to_world_c" in reasons


def test_world_c_verifier_projection_reuses_the_physical_verifier_receipt(
    tmp_path: Path,
) -> None:
    world_c = _complete_world_c(tmp_path)
    context = {
        "task_id": "world-c-1",
        "capability_evidence_bundle": {"source_hash": "sha256:source"},
        "local": _stage(
            "local",
            response={"local_outputs": {"world_c_receipt": world_c}},
        ),
    }

    projection = build_world_c_verifier_projection(context)

    assert projection["gate_passed"] is True
    assert projection["source"] == "HealOrchestrator.VerificationPhase"
    assert projection["world_c_receipt_hash"] == world_c["receipt_hash"]
    assert projection["evidence_refs"] == world_c["authoritative_verifier"]["evidence_refs"]
    assert projection["verifier_status"] == "pass"
    assert projection["source_hash"] == "sha256:source"
    assert projection["verifier_artifact"] == world_c["receipt_hash"]


def test_root_receipt_hash_tamper_fails_closed(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    runtime = {
        "task_id": "world-c-1",
        "workspace_revision": "rev-1",
        "planner_decision_id": "plan-1",
        "canonical_execution": {"task_id": "world-c-1", "execution_id": "exec-1"},
        "planner": {"planner_decision_id": "plan-1"},
        "workforce_admission": {"aggregate_binding_hash": "sha256:workforce"},
        "capability_evidence_bundle": {"source_hash": "sha256:source"},
        "local": _stage(
            "local",
            response={"local_outputs": {"world_c_receipt": world_c}},
        ),
        "online": {"name": "online", "status": "NOT_REQUESTED"},
        "verifier": _stage(
            "verifier",
            response={
                "source": "HealOrchestrator.VerificationPhase",
                "world_c_receipt_hash": world_c["receipt_hash"],
            },
        ),
        "learning": _stage("learning"),
        "capability_results": {},
    }
    root = build_root_receipt(runtime)
    tampered = deepcopy(root)
    tampered["planner_decision_id"] = "forged-plan"

    valid, reasons = validate_root_receipt(tampered)

    assert valid is False
    assert "root_receipt_hash_mismatch" in reasons
