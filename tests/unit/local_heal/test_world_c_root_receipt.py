from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

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
    build_world_c_adequacy_projection,
    build_world_c_receipt,
    record_world_c_phase_result,
    validate_world_c_adequacy_projection,
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


def test_world_c_workspace_is_copied_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")
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


def test_world_c_workspace_rejects_ephemeral_root_without_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", raising=False)

    with pytest.raises(ValueError, match="must not be ephemeral OS temp"):
        prepare_world_c_workspace(tmp_path, "ephemeral-denied", target_file="target.py")


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


def _root_for_world_c(world_c: dict) -> dict:
    root = {
        "schema": "nexus.root_receipt.v1",
        "task_id": world_c["task_id"],
        "world_c_receipt_hash": world_c["receipt_hash"],
        "world_c_receipt_valid": True,
        "source_hash": world_c["source_hash"],
        "verifier_source": "HealOrchestrator.VerificationPhase",
        "verifier_bound_to_world_c": True,
        "receipt_complete": True,
        "missing_evidence": [],
        "public_claim_allowed": False,
    }
    payload = json.dumps(root, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    root["root_receipt_hash"] = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    return root


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _upstream_item(gate: str, world_c: dict) -> dict:
    identity = {
        "task_id": world_c["task_id"],
        "attempt_id": "attempt-1",
        "source_hash": world_c["source_hash"],
        "base_sha": "base-sha",
        "candidate_sha": "candidate-sha",
    }
    if gate == "g1":
        payload = {
            "schema": "nexus.local_heal.reproduction_provenance.v1",
            "status": "PHYSICAL_REPRODUCTION_VERIFIED",
            **identity,
            "receipt": {
                "source_kind": "physical",
                "source_identity": "git:base-sha",
                "command": ["python3", "reproduce_bug.py"],
                "cwd": "/isolated/base",
                "script_sha256": "1" * 64,
                "source_sha256": "2" * 64,
                "evidence_sha256": "3" * 64,
                "exit_status": 7,
                "reason_code": "physical_fail",
                "physical": True,
            },
        }
    elif gate == "g2":
        payload = {
            "schema": "nexus.local_heal.same_oracle_verification.v1",
            "status": "SAME_ORACLE_VERIFIED",
            **identity,
            "receipt": {
                "eligible": True,
                "reason_code": "SAME_ORACLE_VERIFIED",
                "oracle_sha256": "4" * 64,
                "base_receipt": {
                    "task_id": "oracle-base",
                    "verifier_status": "fail",
                    "exit_code": 7,
                    "stdout_tail": "expected base failure",
                    "stderr_tail": "",
                    "verifier_error": "",
                    "verifier_allowed": True,
                    "public_claim_allowed": False,
                    "production_ready": False,
                },
                "candidate_receipt": {
                    "task_id": "oracle-candidate",
                    "verifier_status": "pass",
                    "exit_code": 0,
                    "stdout_tail": "candidate passed",
                    "stderr_tail": "",
                    "verifier_error": "",
                    "verifier_allowed": True,
                    "public_claim_allowed": False,
                    "production_ready": False,
                },
            },
        }
    else:
        payload = {
            "schema": "nexus.local_heal.regression_suite_binding.v1",
            "status": "AFFECTED_SUITE_PASS",
            **identity,
            "receipt": {
                "eligible": True,
                "reason_code": "AFFECTED_SUITE_PASS",
                "suite_identity": "affected-suite-v1:" + "5" * 64,
                "suite_hash": "5" * 64,
                "test_count": 3,
                "base_sha": identity["base_sha"],
                "candidate_sha": identity["candidate_sha"],
                "failure_evidence": [],
            },
        }
    content_hash = _canonical_hash(payload)
    return {"ref": content_hash, "content_hash": content_hash, "payload": payload}


def _upstream_evidence(world_c: dict) -> dict:
    return {gate: _upstream_item(gate, world_c) for gate in ("g1", "g2", "g3")}


def _rehash_upstream(item: dict) -> None:
    item["content_hash"] = _canonical_hash(item["payload"])
    item["ref"] = item["content_hash"]


def test_world_c_adequacy_projects_bound_g1_g3_evidence(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    root = _root_for_world_c(world_c)
    evidence = _upstream_evidence(world_c)

    projection = build_world_c_adequacy_projection(world_c, root, evidence)

    assert projection["status"] == "VERIFIED_REPAIR"
    assert projection["reasons"] == []
    assert projection["upstream_evidence_refs"] == {
        gate: evidence[gate]["ref"] for gate in ("g1", "g2", "g3")
    }
    assert projection["upstream_evidence"] == evidence
    assert projection["world_c_receipt_hash"] == world_c["receipt_hash"]
    assert projection["root_receipt_hash"]
    assert projection["public_claim_allowed"] is False
    valid, reasons = validate_world_c_adequacy_projection(projection)
    assert valid is True, reasons


@pytest.mark.parametrize("missing_gate", ("g1", "g2", "g3"))
def test_world_c_adequacy_missing_each_upstream_stage_is_partial(
    tmp_path: Path, missing_gate: str
) -> None:
    world_c = _complete_world_c(tmp_path)
    root = _root_for_world_c(world_c)
    evidence = _upstream_evidence(world_c)
    evidence.pop(missing_gate)

    projection = build_world_c_adequacy_projection(world_c, root, evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [f"{missing_gate}_evidence_missing"]
    assert projection["public_claim_allowed"] is False


def test_world_c_adequacy_rejects_forged_self_declared_ref(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    evidence = _upstream_evidence(world_c)
    evidence["g1"]["ref"] = "sha256:" + "f" * 64

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == ["g1_ref_hash_mismatch"]


def test_world_c_adequacy_rejects_opaque_refs_without_payloads(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    opaque_refs = {gate: [f"{gate}-self-declared-ref"] for gate in ("g1", "g2", "g3")}

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), opaque_refs)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [
        "g1_evidence_missing",
        "g2_evidence_missing",
        "g3_evidence_missing",
    ]


@pytest.mark.parametrize(
    ("missing_field", "reason"),
    (
        ("payload", "g1_payload_missing"),
        ("ref", "g1_ref_missing"),
        ("content_hash", "g1_content_hash_missing"),
    ),
)
def test_world_c_adequacy_rejects_incomplete_upstream_item(
    tmp_path: Path, missing_field: str, reason: str
) -> None:
    world_c = _complete_world_c(tmp_path)
    evidence = _upstream_evidence(world_c)
    evidence["g1"].pop(missing_field)

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [reason]


@pytest.mark.parametrize("gate", ("g1", "g2", "g3"))
def test_world_c_adequacy_rejects_forged_payload_with_recomputed_hash(
    tmp_path: Path, gate: str
) -> None:
    world_c = _complete_world_c(tmp_path)
    evidence = _upstream_evidence(world_c)
    receipt = evidence[gate]["payload"]["receipt"]
    if gate == "g1":
        receipt["physical"] = False
    elif gate == "g2":
        receipt["base_receipt"]["verifier_status"] = "pass"
        receipt["base_receipt"]["exit_code"] = 0
    else:
        receipt["eligible"] = False
    _rehash_upstream(evidence[gate])

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [f"{gate}_receipt_invalid"]


def test_world_c_adequacy_rejects_payload_content_hash_mismatch(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    evidence = _upstream_evidence(world_c)
    evidence["g3"]["payload"]["receipt"]["test_count"] = 99

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == ["g3_content_hash_mismatch"]


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    (
        ("schema", "nexus.local_heal.forged.v1", "g3_schema_mismatch"),
        ("status", "SELF_DECLARED_PASS", "g3_status_mismatch"),
    ),
)
def test_world_c_adequacy_rejects_wrong_schema_or_status_with_recomputed_hash(
    tmp_path: Path, field: str, replacement: str, reason: str
) -> None:
    world_c = _complete_world_c(tmp_path)
    evidence = _upstream_evidence(world_c)
    evidence["g3"]["payload"][field] = replacement
    _rehash_upstream(evidence["g3"])

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [reason]


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("task_id", "g2_task_id_mismatch"),
        ("attempt_id", "g2_attempt_id_mismatch"),
        ("source_hash", "g2_source_hash_mismatch"),
        ("base_sha", "g2_base_sha_mismatch"),
        ("candidate_sha", "g2_candidate_sha_mismatch"),
    ),
)
def test_world_c_adequacy_rejects_cross_identity_substitution(
    tmp_path: Path, field: str, reason: str
) -> None:
    world_c = _complete_world_c(tmp_path)
    evidence = _upstream_evidence(world_c)
    evidence["g2"]["payload"][field] = f"substituted-{field}"
    _rehash_upstream(evidence["g2"])

    projection = build_world_c_adequacy_projection(world_c, _root_for_world_c(world_c), evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [reason]


def test_world_c_adequacy_rejects_stale_or_tampered_lineage(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    root = _root_for_world_c(world_c)
    root["world_c_receipt_hash"] = "sha256:" + "b" * 64
    evidence = _upstream_evidence(world_c)

    projection = build_world_c_adequacy_projection(world_c, root, evidence)

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == [
        "root_receipt_hash_mismatch",
        "root_receipt_world_c_hash_mismatch",
    ]


def test_world_c_adequacy_rejects_stale_but_self_hashed_root_receipt(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    root = _root_for_world_c(world_c)
    root["world_c_receipt_hash"] = "sha256:" + "b" * 64
    root.pop("root_receipt_hash")
    root["root_receipt_hash"] = _canonical_hash(root)

    projection = build_world_c_adequacy_projection(world_c, root, _upstream_evidence(world_c))

    assert projection["status"] == "PARTIALLY_VERIFIED"
    assert projection["reasons"] == ["root_receipt_world_c_hash_mismatch"]


def test_world_c_adequacy_projection_tamper_fails_closed(tmp_path: Path) -> None:
    world_c = _complete_world_c(tmp_path)
    root = _root_for_world_c(world_c)
    projection = build_world_c_adequacy_projection(
        world_c,
        root,
        _upstream_evidence(world_c),
    )
    projection["status"] = "PARTIALLY_VERIFIED"

    valid, reasons = validate_world_c_adequacy_projection(projection)

    assert valid is False
    assert reasons == ["adequacy_projection_hash_mismatch", "status_reason_mismatch"]
