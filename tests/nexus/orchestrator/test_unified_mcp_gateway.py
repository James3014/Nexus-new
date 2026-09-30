import hashlib
import io
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.contracts.autonomy_goal import (  # noqa: E402
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.engine.canonical_task_seam import (  # noqa: E402
    VerifiedCampaignIdentity,
    VerifiedTaskCardIdentity,
    _derive_campaign_id_from_task_card,
    build_canonical_planner_admission,
)
from nexus.orchestrator.execution_readiness import PlaneObservation  # noqa: E402
from nexus.orchestrator.lifecycle_guards import LifecycleGuardError  # noqa: E402
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService  # noqa: E402
from nexus.orchestrator.standing_grant_store import StandingGrantReceipt  # noqa: E402
from nexus.orchestrator.unified_mcp_gateway import (  # noqa: E402
    FULL_TOOL_SCHEMA_HASH,
    GATEWAY_NAME,
    LIFECYCLE_REVISION,
    PERMISSION_POLICY_HASH,
    PUBLIC_TOOL_NAMES,
    SERVER_INSTANCE_ID,
    TOOL_MANIFEST_REVISION,
    GatewayInputError,
    UnifiedMCPGateway,
    _compile_agy_command,
    observe_github_issue,
)
from nexus.services.model_workforce_policy import WorkforcePolicyLoader  # noqa: E402
from nexus.services.runtime_workforce_admission import (  # noqa: E402
    evaluate_runtime_workforce_admission,
)


def _readiness_observation(plane: str, status: str) -> PlaneObservation:
    """Minimal typed observation bridge (tests may monkeypatch _readiness_plane_observations)."""

    from nexus.contracts.execution_readiness import (
        ExecutionReadinessPlane,
        ExecutionReadinessStatus,
    )

    return PlaneObservation(
        plane=ExecutionReadinessPlane(plane),
        status=ExecutionReadinessStatus(status),
        evidence_identities=(f"{plane}:{status}",),
    )

_TEST_CARD_ROOT: Path | None = None


@pytest.fixture(autouse=True)
def _tracked_card_test_repo(request, tmp_path, monkeypatch):
    global _TEST_CARD_ROOT
    needs_card = any(
        marker in request.node.name
        for marker in ("worker_candidate", "model_probe_feedback_loop", "probe_receipt_tamper")
    )
    if not needs_card:
        yield
        return
    import nexus.orchestrator.self_hosted_task_service as service_module
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    card_root = tmp_path / "canonical-test-repo"
    card_root.mkdir()
    _TEST_CARD_ROOT = card_root
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", card_root)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", card_root)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    original_guard = gateway_module.pre_action_guard

    def test_repo_guard(action, **kwargs):
        return original_guard(action, canonical_root=card_root, **kwargs)

    monkeypatch.setattr(gateway_module, "pre_action_guard", test_repo_guard)
    yield
    _TEST_CARD_ROOT = None


def _task_card_evidence(task_id: str, *, content: str | None = None, path: str | None = None):
    assert _TEST_CARD_ROOT is not None
    relative = path or f"tasks/test/{task_id}.md"
    card = _TEST_CARD_ROOT / relative
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(content or f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    return {
        "task_card_path": relative,
        "task_card_hash": hashlib.sha256(card.read_bytes()).hexdigest(),
    }


class FakeService(SelfHostedTaskService):
    def __init__(self):
        self.submitted = []
        self.completed = []
        self.approved_binding = None
        self.bound_runtime_identity = None
        self.integrated_runtime_identity = None

    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self, *, include_details=False):
        return {"actionable_count": 0, "details_included": include_details, "tasks": []}

    def get_task(self, task_id) -> Any:
        return {"task_id": task_id, "status": "TERMINAL"}

    def get_task_snapshot(self, task_id, *, include_details=False) -> Any:
        return {
            "task_id": task_id,
            "status": "APPROVED" if self.approved_binding else "PENDING_HUMAN_APPROVAL",
            "promotion_status": "APPROVED" if self.approved_binding else "PENDING_HUMAN_APPROVAL",
            "attempt_id": "attempt-recovery",
            "controller_revision": "a" * 40,
            "contract_kind": "TRACKED_TASK_CARD",
            "contract_hash": "c" * 64,
            "task_card_hash": "c" * 64,
            "approved_binding": self.approved_binding,
            "contract": {"allowed_files": ["README.md"]},
            "promotion_packet": {
                "candidate_commit_sha": "a" * 40,
                "candidate_tree_sha": "a" * 40,
                "candidate_state_hash": "b" * 64,
                "verified_receipt_hash": "b" * 64,
            },
        }

    def wait_task(self, task_id, **kwargs):
        return {"task_id": task_id, "status": "PENDING_HUMAN_APPROVAL", "task_action": {"action_state": "ACTION_REQUIRED", "next_action": "owner_finish"}, "wait": kwargs}

    def complete_direct_canonical(self, request, *, expected_commit_sha=None):
        self.completed.append(dict(request))
        return {"status": "DIRECT_CANONICAL_COMPLETED", "task_id": request["task_id"], "expected_commit_sha": expected_commit_sha}

    def owner_finish(self, task_id, **kwargs):
        return {"status": "INTEGRATED", "task_id": task_id, "binding": kwargs}

    def cancel_task(self, task_id):
        return {"status": "CANCELLED", "task_id": task_id}

    def reconcile_task(self, task_id):
        return {"task_id": task_id, "attempt_id": "attempt-1", "status": "FINAL_BLOCK", "task_action": {"task_id": task_id, "task_status": "FINAL_BLOCK", "attention_required": True, "next_action": "nexus_task_reconcile", "recommended_tool": "nexus_task_reconcile"}, "reconciliation_required": True}

    def retry_task(self, task_id):
        return {"task_id": task_id, "attempt_id": "attempt-2", "status": "SUBMITTED", "task_action": {"task_id": task_id, "task_status": "SUBMITTED", "attention_required": True, "next_action": "nexus_task_wait", "recommended_tool": "nexus_task_wait"}}

    def resume_task(self, task_id):
        return self.reconcile_task(task_id)

    def approve_promotion(self, task_id, **kwargs):
        binding = {key: kwargs.get(key) for key in ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")}
        binding["approval_grant"] = {**(kwargs.get("approval_context") or {}), "consumed_at": (kwargs.get("approval_context") or {}).get("consumed_at") or datetime.now(timezone.utc).isoformat()}
        self.approved_binding = binding
        return {"task_id": task_id, "status": "APPROVED", "promotion_status": "APPROVED", "approved_binding": binding, "task_action": {"task_id": task_id, "task_status": "APPROVED", "attention_required": True, "next_action": "nexus_candidate_integrate", "recommended_tool": "nexus_candidate_integrate"}}

    def integrate_approved(self, task_id, **kwargs):
        self.integrated_runtime_identity = dict(kwargs.get("runtime_identity") or {})
        return {"task_id": task_id, "status": "INTEGRATED", "promotion_status": "INTEGRATED", "task_action": {"task_id": task_id, "task_status": "INTEGRATED", "attention_required": False, "next_action": "none", "recommended_tool": "none"}}

    def bind_candidate_integration_closure(self, task_id, **kwargs):
        self.bound_runtime_identity = dict(kwargs.get("runtime_identity") or {})
        return {
            "task_id": task_id,
            "status": "APPROVED",
            "promotion_status": "APPROVED",
            "integration_performed": False,
        }

    def dispose_candidate(self, task_id, **kwargs):
        return {"task_id": task_id, "status": kwargs["disposition"], "promotion_status": kwargs["disposition"], "task_action": {"task_id": task_id, "task_status": kwargs["disposition"], "attention_required": False, "next_action": "none", "recommended_tool": "none"}}

    def submit_task(self, request):
        self.submitted.append(request)
        return {"status": "PENDING_HUMAN_APPROVAL", "task_id": request["task_id"], "target_created": True, "state_created": True}

    def build_contract(self, request):
        return super().build_contract(request)


def _allow_owner_effect_authority(monkeypatch):
    def allow(action, effect, key):
        assert key.repository.repository_id == "James3014/Nexus-new"
        return {
            "schema": "nexus.standing_grant_effect_authorization.v1",
            "action": action.value,
            "effect": dict(effect),
            "mutation_authorized": True,
            "authorization_hash": "f" * 64,
        }

    monkeypatch.setattr(
        UnifiedMCPGateway,
        "_require_owner_effect_authority",
        staticmethod(allow),
    )


AUTHORITY_ARGS = {
    "authority_goal_id": "goal-test",
    "authority_coordination_scope_id": "thread-test",
}


def test_candidate_adopt_external_public_schema_is_closed_and_registered():
    names = {spec["name"] for spec in UnifiedMCPGateway.tool_specs()}
    spec = next(spec for spec in UnifiedMCPGateway.tool_specs() if spec["name"] == "nexus_candidate_adopt_external")
    assert "nexus_candidate_adopt_external" in names
    assert spec["inputSchema"]["additionalProperties"] is False
    assert "action" in spec["inputSchema"]["required"]


def test_durable_owner_effect_schemas_require_explicit_authority_selectors():
    specs = {spec["name"]: spec["inputSchema"] for spec in UnifiedMCPGateway.tool_specs()}
    for name in (
        "nexus_task_card_create",
        "nexus_task_card_commit",
        "nexus_candidate_adopt_external",
        "nexus_candidate_dispose",
    ):
        schema = specs[name]
        assert {"authority_goal_id", "authority_coordination_scope_id"}.issubset(
            schema["required"]
        )
        assert schema["additionalProperties"] is False

    assert "expectedCurrentThreadId" in specs["nexus_task_card_authority_switch"]["required"]
    assert "expectedCurrentGoalId" in specs["nexus_task_card_authority_restore"]["required"]
    assert "expectedCurrentThreadId" in specs["nexus_task_card_authority_restore"]["required"]


def test_candidate_adopt_external_rejects_unknown_field_without_service_call(monkeypatch):
    service = FakeService()
    calls = []
    service.adopt_external_candidate = lambda request: calls.append(request)  # type: ignore[attr-defined]
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({
        "jsonrpc": "2.0", "id": 4601, "method": "tools/call",
        "params": {"name": "nexus_candidate_adopt_external", "arguments": {
            "campaign_id": "campaign", "spec_id": "spec", "unexpected_downstream": True,
        }},
    })
    assert response["result"]["isError"] is True
    assert "CANDIDATE_ADOPTION_SCHEMA_CLOSED" in response["result"]["structuredContent"]["error"]
    assert calls == []


def test_candidate_adopt_external_rejects_runtime_server_mismatch_without_service_call():
    service = FakeService()
    calls = []
    service.adopt_external_candidate = lambda request: calls.append(request)  # type: ignore[attr-defined]
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({
        "jsonrpc": "2.0", "id": 4602, "method": "tools/call",
        "params": {"name": "nexus_candidate_adopt_external", "arguments": {
            "campaign_id": "campaign", "spec_id": "spec", "spec_sha256": "0" * 64, "server_instance_id": "wrong",
            **AUTHORITY_ARGS,
            "lifecycle_revision": LIFECYCLE_REVISION, "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
            "permission_policy_hash": PERMISSION_POLICY_HASH, "controller_repo_root": str(Path.cwd()),
            "controller_branch": "main", "controller_head": "a" * 40,
        }},
    })
    assert response["result"]["isError"] is True
    assert "CANDIDATE_ADOPTION_SERVER_INSTANCE_MISMATCH" in response["result"]["structuredContent"]["error"]
    assert calls == []


def test_candidate_adopt_external_positive_binds_runtime_and_calls_service_once(monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module
    from nexus.contracts.lifecycle_action import (
        ApprovalScope,
        ContractKind,
        ExternalCandidateAdoptionRequest,
        LifecycleActionType,
        MutationDomain,
        PermissionProfile,
        build_action_envelope,
    )

    service = FakeService()
    calls = []

    def adopt(request):
        calls.append(request)
        receipt = {
            "schema": "nexus.external_candidate_adoption_receipt.v1",
            "task_id": request.task_id, "attempt_id": request.attempt_id,
            "action_id": request.action_id, "idempotency_key": request.idempotency_key,
            "adoption_request_hash": request.semantic_hash(),
            "task_card_path": request.task_card_path, "task_card_hash": request.task_card_hash,
            "contract_hash": "2" * 64, "controller_revision": request.controller_revision,
            "target_base_revision": request.target_base_revision,
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_diff_sha256": request.candidate_diff_sha256,
            "candidate_state_hash": "3" * 64, "verified_receipt_hash": "4" * 64,
            "validation_receipt_sha256": request.validation_receipt_sha256,
            "acceptance_receipt_sha256": request.acceptance_receipt_sha256,
            "repository_contract_policy_revision_hash": "5" * 64,
            "derived_contract_projection": {}, "forbidden_repository_patterns": [],
            "reviewer_id": "independent-reviewer",
            "candidate_ref": f"refs/nexus-candidates/{request.task_id}/{request.candidate_commit_sha}",
            "promotion_packet_hash": "6" * 64, "worker_invocations": 0,
            "candidate_rewritten": False, "approval_performed": False,
            "integration_performed": False, "merge_performed": False,
            "push_performed": False, "public_claim_allowed": False,
            "production_ready": False,
            "claim_ceiling": ["CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY"],
            "issued_at": "2026-08-30T00:00:00+00:00",
        }
        receipt_hash = hashlib.sha256(json.dumps(
            receipt, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        return {
            "task_id": request.task_id, "status": "PENDING_HUMAN_APPROVAL",
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_state_hash": receipt["candidate_state_hash"],
            "verified_receipt_hash": receipt["verified_receipt_hash"],
            "candidate_ref": receipt["candidate_ref"],
            "approved_binding": None, "integration_authorization": None,
            "integration_receipt": None, "merge_performed": False,
            "push_performed": False, "public_claim_allowed": False,
            "production_ready": False, "adoption_receipt": receipt,
            "adoption_receipt_hash": receipt_hash,
        }

    service.adopt_external_candidate = adopt  # type: ignore[attr-defined]
    gateway = UnifiedMCPGateway(service=service)
    head = "a" * 40
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "main" if args[:2] == ("branch", "--show-current") else head)
    owner_effects = []

    def allow(action, effect, key):
        owner_effects.append((action, dict(effect)))
        return {"action": action.value, "mutation_authorized": True, "authorization_hash": "f" * 64}

    monkeypatch.setattr(UnifiedMCPGateway, "_require_owner_effect_authority", staticmethod(allow))
    validation = json.dumps({"schema": "validation"}).encode()
    acceptance = json.dumps({"schema": "acceptance"}).encode()
    base = {
        "schema": "nexus.external_candidate_adoption_request.v1", "repository": gateway_module.GITHUB_REPOSITORY.repository_id,
        "task_id": "adopt-positive", "attempt_id": "attempt-1", "action_id": "action-1",
        "idempotency_key": "idem-1", "task_card_path": "tasks/test/adopt-positive.md", "task_card_hash": "c" * 64,
        "controller_revision": head, "tool_manifest_hash": TOOL_MANIFEST_REVISION,
        "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH, "permission_policy_hash": PERMISSION_POLICY_HASH,
        "lifecycle_revision": LIFECYCLE_REVISION, "server_instance_id": SERVER_INSTANCE_ID,
        "target_base_revision": "b" * 40, "candidate_commit_sha": "d" * 40, "candidate_tree_sha": "e" * 40,
        "candidate_diff_sha256": "1" * 64, "validation_receipt_sha256": hashlib.sha256(validation).hexdigest(),
        "acceptance_receipt_sha256": hashlib.sha256(acceptance).hexdigest(),
        "validation_receipt_b64": __import__("base64").b64encode(validation).decode(),
        "acceptance_receipt_b64": __import__("base64").b64encode(acceptance).decode(),
        "allowed_files": ("README.md",), "verifier_commands": ("git diff --check",),
        "forbidden_files": (), "authorized_deletions": (), "protected_contracts": (),
    }
    semantic_hash = ExternalCandidateAdoptionRequest.model_construct(**base, action=None).semantic_hash()
    action = build_action_envelope(
        task_id=base["task_id"], action_type=LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL,
        request={"adoption_request_hash": semantic_hash}, tool_manifest_hash=TOOL_MANIFEST_REVISION,
        expected_head=head, allowed_paths=["README.md"], mutation=True,
        task_card_path=base["task_card_path"], task_card_hash=base["task_card_hash"],
        contract_kind=ContractKind.TRACKED_TASK_CARD, permission_profile=PermissionProfile.CANDIDATE,
        approval_scope=ApprovalScope.ALLOW_ACTION_ONCE, mutation_domain=MutationDomain.CANDIDATE_REF,
        attempt_id=base["attempt_id"], action_id=base["action_id"], idempotency_key=base["idempotency_key"],
    ).model_dump(mode="json")
    arguments = {
        **base, **AUTHORITY_ARGS, "action": action, "campaign_id": gateway_module.EPB_CAMPAIGN_ID,
        "spec_id": gateway_module.EPB_SPEC_ID, "spec_sha256": gateway_module.EPB_SPEC_SHA256,
        "controller_repo_root": str(gateway_module.CANONICAL_SOURCE_ROOT), "controller_branch": "main",
        "controller_head": head,
    }
    response = gateway.handle({"jsonrpc": "2.0", "id": 4603, "method": "tools/call", "params": {"name": "nexus_candidate_adopt_external", "arguments": arguments}})
    assert response["result"]["isError"] is False, response
    assert response["result"]["structuredContent"]["status"] == "PENDING_HUMAN_APPROVAL"
    assert len(calls) == 1 and isinstance(calls[0], ExternalCandidateAdoptionRequest)
    assert len(owner_effects) == 1
    assert owner_effects[0][0] is gateway_module.AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL
    assert owner_effects[0][1]["spec_sha256"] == gateway_module.EPB_SPEC_SHA256
    assert owner_effects[0][1]["full_tool_schema_hash"] == FULL_TOOL_SCHEMA_HASH
    assert "NO_MERGE" in response["result"]["structuredContent"]["claim_ceiling"]


@pytest.mark.parametrize("bad_result", [
    {"status": "APPROVED", "promotion_status": "APPROVED"},
    {"status": "PENDING_HUMAN_APPROVAL", "promotion_status": "PENDING_HUMAN_APPROVAL", "merge_performed": True},
    {"status": "PENDING_HUMAN_APPROVAL", "promotion_status": "PENDING_HUMAN_APPROVAL", "approved_binding": {"approval": True}},
    {
        "status": "PENDING_HUMAN_APPROVAL", "promotion_status": "PENDING_HUMAN_APPROVAL",
        "approved_binding": None, "integration_authorization": None,
        "integration_receipt": None, "merge_performed": False,
        "push_performed": False, "public_claim_allowed": False,
        "production_ready": False, "approval_performed": True,
        "integration_performed": True, "release_performed": True,
        "activation_performed": True,
    },
    {
        "status": "PENDING_HUMAN_APPROVAL", "promotion_status": "PENDING_HUMAN_APPROVAL",
        "approved_binding": None, "integration_authorization": None,
        "integration_receipt": None, "merge_performed": False,
        "push_performed": False, "public_claim_allowed": False,
        "production_ready": False, "approval": {"approved": True},
        "integrated": True, "released": True, "activated": True,
    },
])
def test_candidate_adopt_external_rejects_downstream_service_result(monkeypatch, bad_result):
    with pytest.raises(GatewayInputError, match="SERVICE_RESULT"):
        UnifiedMCPGateway._validate_external_adoption_result(bad_result)


def _ready_preflight(**overrides):
    """A positive worker mock must model verified execution, not version-only."""
    payload = {
        "status": "VERSION_VERIFIED",
        "readiness_status": "MODEL_VERIFIED",
        "execution_ready": True,
        "provider": "agy",
        "requested_model": "agy/model",
        "resolved_model": "agy/model",
        "model_reachable": True,
        "requested_model_verified": True,
        "authenticated": True,
        "authentication_evidence": "successful_exact_model_probe",
        "probe_evidence_hash": "e" * 64,
        "binary_path": "/usr/bin/true",
        "binary_sha256": "b" * 64,
        "cli_version_sha256": "c" * 64,
        "probe_expires_at": "2099-01-01T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _valid_local_dispatch():
    demands = {
        "schema": "nexus.workforce_demands.v1", "route_authority": "CapabilityPlanner",
        "demands": [{
            "schema": "nexus.workforce_demand.v1", "demand_id": "gateway-dispatch-1",
            "execution_channel": "local", "requested_role": "bounded_code_candidate",
            "minimum_autonomy": "L1", "context_class": "nexus_bounded", "mutation_intent": True,
            "external_verification_required": True, "route_authority": "CapabilityPlanner",
        }],
    }
    admission = evaluate_runtime_workforce_admission(
        demands,
        {"local": {"worker_id": "local_coder_7b", "provider": "ollama", "model": "qwen2.5-coder:7b-instruct", "controls": ["focused_tests", "compile", "parser", "small_scope", "reversible_application"]}},
        WorkforcePolicyLoader(Path(repo_root) / "nexus/config/model_workforce.yaml"),
    ).to_dict()
    return demands, admission


def _valid_online_agy_dispatch():
    demands = {
        "schema": "nexus.workforce_demands.v1", "route_authority": "CapabilityPlanner",
        "demands": [{
            "schema": "nexus.workforce_demand.v1", "demand_id": "gateway-online-agy-1",
            "execution_channel": "online", "requested_role": "fast_bounded_implementation",
            "minimum_autonomy": "L1", "context_class": "nexus_bounded", "mutation_intent": True,
            "external_verification_required": True, "route_authority": "CapabilityPlanner",
        }],
    }
    admission = evaluate_runtime_workforce_admission(
        demands,
        {"online": {"worker_id": "agy_flash_37_medium", "provider": "agy", "model": "gemini-3.7-flash-medium", "controls": ["task_card", "allowed_files", "mandatory_commands", "parser", "verifier", "independent_verification"]}},
        WorkforcePolicyLoader(Path(repo_root) / "nexus/config/model_workforce.yaml"),
    ).to_dict()
    return demands, admission


def _actual_dispatch(task_id, what, why):
    card = _task_card_evidence(task_id)
    assert _TEST_CARD_ROOT is not None
    result = build_canonical_planner_admission(
        task_id=task_id,
        task_text=what,
        allowed_files=("README.md",),
        verifier_command=("git diff --check",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id=task_id,
            task_card_path=card["task_card_path"],
            canonical_task_card_path=str((_TEST_CARD_ROOT / card["task_card_path"]).resolve()),
            task_card_hash=card["task_card_hash"],
        ),
    )
    result["task_card_evidence"] = card
    return result


def test_canonical_planner_admission_uses_policy_routing_not_worker_iteration(
    monkeypatch, tmp_path,
):
    loader = WorkforcePolicyLoader()
    snapshot = loader.load()
    decoy = replace(
        snapshot.workers["grok_review"],
        roles=(
            *snapshot.workers["grok_review"].roles,
            "fast_bounded_implementation",
        ),
        preferred_context="nexus_bounded",
    )
    reordered = replace(
        snapshot,
        workers={
            "grok_review": decoy,
            **{
                worker_id: worker
                for worker_id, worker in snapshot.workers.items()
                if worker_id != "grok_review"
            },
        },
    )
    monkeypatch.setattr(WorkforcePolicyLoader, "load", lambda _self: reordered)

    card_path = tmp_path / "canonical-policy-routing.md"
    card_bytes = b"task_id: `canonical-policy-routing`\nAUTO_CHAIN: false\n"
    card_path.write_bytes(card_bytes)
    result = build_canonical_planner_admission(
        task_id="canonical-policy-routing",
        task_text="implement one bounded change",
        allowed_files=("bounded.py",),
        verifier_command=("pytest -q tests/bounded.py",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id="canonical-policy-routing",
            task_card_path="tasks/test/canonical-policy-routing.md",
            canonical_task_card_path=str(card_path),
            task_card_hash=hashlib.sha256(card_bytes).hexdigest(),
        ),
    )

    assert reordered.routing["online"]["fast_bounded_implementation"] == "agy_flash_37_medium"
    assert result["binding"]["worker_id"] == "agy_flash_37_medium"
    assert result["workforce_admission"]["records"][0]["request"][
        "requested_worker_id"
    ] == "agy_flash_37_medium"


def test_campaign_identity_requires_canonical_bytes_and_hash(tmp_path):
    card = tmp_path / "card.md"
    card.write_text("Campaign: `CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01`\n", encoding="utf-8")
    identity = VerifiedTaskCardIdentity(
        task_id="campaign-proof",
        task_card_path="tasks/test/card.md",
        canonical_task_card_path=str(card),
        task_card_hash=hashlib.sha256(card.read_bytes()).hexdigest(),
    )
    assert _derive_campaign_id_from_task_card(identity) == "CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01"
    tampered = replace(identity, task_card_hash="0" * 64)
    with pytest.raises(ValueError, match="hash_mismatch"):
        _derive_campaign_id_from_task_card(tampered)


def test_authenticated_campaign_identity_is_bound_and_conflicts_fail(tmp_path):
    card = tmp_path / "card.md"
    card_bytes = b"Campaign: `CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01`\n"
    card.write_bytes(card_bytes)
    task_card = VerifiedTaskCardIdentity(
        task_id="campaign-bound",
        task_card_path="tasks/test/card.md",
        canonical_task_card_path=str(card),
        task_card_hash=hashlib.sha256(card_bytes).hexdigest(),
    )
    exact = VerifiedCampaignIdentity(
        campaign_id="CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01",
        task_id=task_card.task_id,
        task_card_hash=task_card.task_card_hash,
    )
    result = build_canonical_planner_admission(
        task_id=task_card.task_id, task_text="bounded change",
        allowed_files=("bounded.py",), verifier_command=("git diff --check",),
        task_card_identity=task_card, campaign_identity=exact,
    )
    assert result["binding"]["worker_id"] == "agy_flash_37_medium"
    conflict = replace(exact, campaign_id="CAMPAIGN-PLANNER-WORKFORCE-SELECTION-REPAIR-01")
    with pytest.raises(ValueError, match="campaign_identity_conflict"):
        build_canonical_planner_admission(
            task_id=task_card.task_id, task_text="bounded change",
            allowed_files=("bounded.py",), verifier_command=("git diff --check",),
            task_card_identity=task_card, campaign_identity=conflict,
        )
    with pytest.raises(ValueError, match="canonical_campaign_identity_unverified"):
        build_canonical_planner_admission(
            task_id=task_card.task_id, task_text="bounded change",
            allowed_files=("bounded.py",), verifier_command=("git diff --check",),
            task_card_identity=task_card, campaign_identity="CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01",  # type: ignore[arg-type]
        )


def test_open_swe_canary_task_card_produces_canonical_opencli_chatgpt_allow_binding() -> None:
    canary_rel_path = "tasks/open-swe-resident-five-repo-canary-20260908/00-canary.md"
    canary_path = Path(repo_root) / canary_rel_path
    assert canary_path.is_file()
    card_bytes = canary_path.read_bytes()
    card_hash = hashlib.sha256(card_bytes).hexdigest()

    task_card = VerifiedTaskCardIdentity(
        task_id="open-swe-resident-five-repo-canary-20260908",
        task_card_path=canary_rel_path,
        canonical_task_card_path=str(canary_path),
        task_card_hash=card_hash,
    )

    derived_campaign = _derive_campaign_id_from_task_card(task_card)
    assert derived_campaign == "open-swe-resident-five-repo-canary-20260908"

    result = build_canonical_planner_admission(
        task_id=task_card.task_id,
        task_text="Open SWE resident unattended canary",
        allowed_files=("tests/ops/test_open_swe_resident_five_repo_canary_20260908.py",),
        verifier_command=(
            "python3 -m pytest -q tests/ops/test_open_swe_resident_five_repo_canary_20260908.py",
            "git diff --check",
        ),
        task_card_identity=task_card,
    )

    admission = result["workforce_admission"]
    assert admission["overall_decision"] == "ALLOW"
    records = admission.get("records") or []
    assert len(records) == 1
    record = records[0]
    assert record["decision"]["decision"] == "ALLOW"
    assert record["decision"]["resolved_worker_id"] == "opencli_chatgpt_balanced_web"
    assert record["decision"]["resolved_provider"] == "opencli_chatgpt"
    assert record["decision"]["resolved_model"] == "opencli_chatgpt/balanced"
    assert record["request"]["role"] == "bounded_candidate_generation"
    assert record["request"]["autonomy"] == "L1"
    assert record["demand"]["minimum_autonomy"] == "L1"

    binding = result["binding"]
    assert binding["worker_id"] == "opencli_chatgpt_balanced_web"
    assert binding["provider"] == "opencli_chatgpt"
    assert binding["model"] == "opencli_chatgpt/balanced"


def _worker_args(
    task_id: str,
    *,
    what: str = "x",
    why: str = "y",
    worker: str = "auto",
    allowed_files: list[str] | None = None,
):
    return {
        "task_id": task_id,
        "what": what,
        "why": why,
        "worker": worker,
        "allowed_files": allowed_files or ["README.md"],
        "verifier_commands": ["git diff --check"],
        "owner_confirmation": True,
        **_task_card_evidence(task_id),
    }


def _patch_probe_version(monkeypatch):
    """Keep executable preflight shell-free and independent of FakePopen."""
    def fake_run(command, **kwargs):
        if list(command)[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n", stderr="")
        assert list(command)[-1] == "--version"
        return SimpleNamespace(returncode=0, stdout="cline 1.2.3\n", stderr="")

    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)

    def reject_shell_version_probe(*args, **kwargs):
        raise AssertionError("model probe preflight must not use os.popen")

    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.os.popen",
        reject_shell_version_probe,
    )


def _cline_probe_events(payload, *, model="cline-pass/glm-5.2", provider="cline"):
    return "\n".join((
        json.dumps({"type": "run_start", "providerId": provider, "modelId": model}),
        json.dumps({
            "type": "run_result",
            "finishReason": "stop",
            "text": json.dumps(payload),
            "model": {"id": model, "provider": provider},
        }),
    )) + "\n"


def test_canonical_request_derives_target_namespace_from_bound_source_root(monkeypatch, tmp_path):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    activation_root = tmp_path / "clean-activation"
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", activation_root)

    request = UnifiedMCPGateway._canonical_request(
        "activation-request",
        "exercise product bridge",
        "prove clean activation binding",
        ["README.md"],
        ["/usr/bin/true"],
        "a" * 40,
    )

    assert request["controller_repo_root"] == str(activation_root)
    assert request["target_worktree_root"] == str(tmp_path / "nexus-runtime-targets")
    assert request["target_repo_root"] == str(tmp_path / "nexus-runtime-targets" / "activation-request")


def test_gateway_has_one_identity_and_bounded_public_surface():
    gateway = UnifiedMCPGateway(service=FakeService())
    initialized = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    listed = gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert initialized is not None
    assert listed is not None

    assert initialized["result"]["serverInfo"]["name"] == GATEWAY_NAME
    assert initialized["result"]["serverInfo"]["toolManifestRevision"] == TOOL_MANIFEST_REVISION
    assert len(listed["result"]["tools"]) == len(UnifiedMCPGateway.tool_specs())
    assert {tool["name"] for tool in listed["result"]["tools"]} == {tool["name"] for tool in UnifiedMCPGateway.tool_specs()}


def test_worker_candidate_public_schema_is_typed_and_closed():
    spec = next(item for item in UnifiedMCPGateway.tool_specs() if item["name"] == "nexus_worker_candidate")
    schema = spec["inputSchema"]
    assert set(schema["required"]) == {
        "what", "why", "allowed_files", "verifier_commands", "owner_confirmation",
        "task_card_path", "task_card_hash",
    }
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert properties["authority_change_candidate_confirmation"] == {"type": "boolean", "default": False}
    assert "authority_change_candidate_confirmation" not in schema["required"]
    assert properties["task_card_hash"]["pattern"] == "^[0-9a-f]{64}$"
    for evidence in ("worker", "provider", "model", "planner_output", "workforce_admission"):
        assert evidence in properties
    for forbidden in ("command", "shell", "apply", "approval", "integration_branch", "push", "execution_lane", "preferred_worker"):
        assert forbidden not in properties


def test_worker_candidate_forwards_tracked_task_run_once(monkeypatch):
    from nexus.contracts.lifecycle_action import ContractKind, LifecycleActionType

    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    gateway_module = sys.modules["nexus.orchestrator.unified_mcp_gateway"]
    head = "a" * 40
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: head)
    arguments = {
        "task_id": "worker-candidate-1",
        "what": "bounded change",
        "why": "prove candidate seam",
        "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"],
        "owner_confirmation": True,
        **_task_card_evidence("worker-candidate-1"),
    }
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.7-flash-medium", resolved_model="gemini-3.7-flash-medium",
    ))
    response = gateway.handle({"jsonrpc": "2.0", "id": 44, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": arguments}})
    assert response is not None
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "PENDING_HUMAN_APPROVAL"
    assert len(service.submitted) == 1
    request = service.submitted[0]
    from nexus.orchestrator.self_hosted_task_service import _validated_action_request
    effective, envelope = _validated_action_request(request)
    assert envelope is not None
    assert envelope["request_hash"] == request["request_hash"]
    assert effective["task_card_path"] == arguments["task_card_path"]
    assert effective["task_card_hash"] == arguments["task_card_hash"]
    assert request["provider"] == "agy"
    assert request["model"] == "gemini-3.7-flash-medium"
    assert request["worker"] == "agy"
    assert request["worker_id"] == "agy_flash_37_medium"
    readiness_fields = {
        "provider_probe_evidence_hash": "e" * 64,
        "provider_binary_path": "/usr/bin/true",
        "provider_binary_sha256": "b" * 64,
        "provider_cli_version_sha256": "c" * 64,
        "provider_probe_expires_at": "2099-01-01T00:00:00+00:00",
        "provider_authentication_evidence": "successful_exact_model_probe",
    }
    for field, expected in readiness_fields.items():
        assert request[field] == expected
        assert request["bound_action_request"][field] == expected
    assert request["action"]["action_type"] == LifecycleActionType.TASK_RUN.value
    assert request["action"]["contract_kind"] == ContractKind.TRACKED_TASK_CARD.value
    assert request["action"]["permission_profile"] == "CANDIDATE"
    assert request["action"]["task_card_path"] == arguments["task_card_path"]
    assert request["action"]["task_card_hash"] == arguments["task_card_hash"]
    assert request["action"]["mutation_domain"] == "TARGET"
    assert request["owner_inline_contract"] is None
    assert request["action"]["contract_hash"] is None
    assert request["protected_contracts"] == []
    assert request.get("authority_change_candidate_confirmation", False) is False
    assert request["bound_action_request"]["protected_contracts"] == request["protected_contracts"]
    envelope = request["canonical_dispatch_envelope"]
    assert envelope["task_id"] == request["task_id"]
    assert envelope["attempt_id"] == request["attempt_id"]
    assert envelope["task_card_path"] == request["task_card_path"]
    assert envelope["task_card_hash"] == request["task_card_hash"]


def test_worker_candidate_uses_planner_admission_identity_and_rejects_override(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    gateway_module = sys.modules["nexus.orchestrator.unified_mcp_gateway"]
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    internal = _actual_dispatch("governed-dispatch-1", "bounded change", "admitted dispatch")
    demands, admission = internal["workforce_demands"], internal["workforce_admission"]
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        provider="agy", requested_model="gemini-3.7-flash-medium", resolved_model="gemini-3.7-flash-medium",
    ))
    arguments = {
        "task_id": "governed-dispatch-1", "what": "bounded change", "why": "admitted dispatch",
        "worker": "auto", "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
        "workforce_demands": demands, "workforce_admission": admission,
        "planner_output": internal["planner_output"],
        **internal["task_card_evidence"],
    }
    response = gateway.handle({"jsonrpc": "2.0", "id": 801, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": arguments}})
    assert response is not None
    assert response["result"]["isError"] is False, response["result"].get("structuredContent")
    request = service.submitted[0]
    assert request["worker_id"] == internal["binding"]["worker_id"]
    assert request["provider"] == internal["binding"]["provider"]
    assert request["model"] == internal["binding"]["model"]
    assert request["workforce_admission"]["aggregate_binding_hash"] == admission["aggregate_binding_hash"]

    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    arguments["worker"] = "different-worker"
    response = gateway.handle({"jsonrpc": "2.0", "id": 802, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": arguments}})
    assert response["result"]["isError"] is True
    assert "WORKFORCE_ADMISSION_WORKER_MISMATCH" in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


def test_worker_candidate_auto_dispatches_admitted_online_agy_end_to_end(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    gateway_module = sys.modules["nexus.orchestrator.unified_mcp_gateway"]
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    internal = _actual_dispatch("governed-online-agy-1", "bounded online change", "prove agy admission seam")
    demands, admission = internal["workforce_demands"], internal["workforce_admission"]
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        provider="agy", requested_model="gemini-3.7-flash-medium", resolved_model="gemini-3.7-flash-medium",
    ))
    arguments = {
        "task_id": "governed-online-agy-1", "what": "bounded online change", "why": "prove agy admission seam",
        "worker": "auto", "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
        "workforce_demands": demands, "workforce_admission": admission,
        "planner_output": internal["planner_output"],
        **internal["task_card_evidence"],
    }
    response = gateway.handle({"jsonrpc": "2.0", "id": 803, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": arguments}})
    assert response["result"]["isError"] is False, response["result"].get("structuredContent")
    request = service.submitted[0]
    assert request["worker"] == internal["binding"]["provider"]
    assert request["worker_id"] == internal["binding"]["worker_id"]
    assert request["provider"] == internal["binding"]["provider"]
    assert request["model"] == internal["binding"]["model"]
    assert request["workforce_admission"]["overall_decision"] == "ALLOW"
    assert request["workforce_admission"]["aggregate_binding_hash"] == admission["aggregate_binding_hash"]


def test_worker_candidate_requires_planner_decision_before_preflight(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    internal = _actual_dispatch("missing-planner", "bounded change", "planner gate")
    demands, admission = internal["workforce_demands"], internal["workforce_admission"]
    monkeypatch.setattr(
        gateway,
        "_provider_preflight",
        lambda arguments: (_ for _ in ()).throw(AssertionError("planner gate must precede preflight")),
    )
    response = gateway.handle({
        "jsonrpc": "2.0", "id": 806, "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": {
            "task_id": "missing-planner", "what": "bounded change", "why": "planner gate",
            "worker": "auto", "allowed_files": ["README.md"],
            "verifier_commands": ["git diff --check"], "owner_confirmation": True,
            "workforce_demands": demands, "workforce_admission": admission,
            "planner_output": {
                "execution_decision": {"task_id": "missing-planner", "authority": "CapabilityPlanner", "plan_hash": "b" * 64},
                "decision_hash": "a" * 64, "plan_hash": "b" * 64,
            },
            **internal["task_card_evidence"],
        }},
    })
    assert response["result"]["isError"] is True
    assert "WORKFORCE_CALLER_EVIDENCE_MISMATCH:planner_output" in response["result"]["structuredContent"]["error"] or "WORKFORCE_INTERNAL" in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("provider", "wrong-provider", "WORKER_PREFLIGHT_PROVIDER_MISMATCH"),
        ("requested_model", "wrong-requested-model", "WORKER_PREFLIGHT_REQUESTED_MODEL_MISMATCH"),
        ("resolved_model", "wrong-resolved-model", "WORKER_PREFLIGHT_RESOLVED_MODEL_MISMATCH"),
    ],
)
def test_worker_candidate_rejects_preflight_identity_mismatch_before_submit(
    monkeypatch, field, value, code,
):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    task_id = f"governed-online-agy-preflight-{field}"
    what, why = "bounded online change", "preflight identity gate"
    internal = _actual_dispatch(task_id, what, why)
    demands, admission = internal["workforce_demands"], internal["workforce_admission"]
    preflight = _ready_preflight(
        provider="agy", requested_model="gemini-3.7-flash-medium",
        resolved_model="gemini-3.7-flash-medium",
    )
    preflight[field] = value
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: preflight)
    arguments = {
        "task_id": task_id,
        "what": what, "why": why,
        "worker": "auto", "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
        "workforce_demands": demands, "workforce_admission": admission,
        "planner_output": internal["planner_output"],
        **internal["task_card_evidence"],
    }
    response = gateway.handle({
        "jsonrpc": "2.0", "id": 805, "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": arguments},
    })
    assert response["result"]["isError"] is True
    assert code in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


def test_worker_candidate_quarantines_current_block_before_preflight_or_submit(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    task_id, what, why = "governed-online-agy-blocked", "blocked change", "quarantine gate"
    internal = _actual_dispatch(task_id, what, why)
    demands, admission = internal["workforce_demands"], internal["workforce_admission"]
    blocked = json.loads(json.dumps(admission))
    blocked["overall_decision"] = "BLOCK"
    monkeypatch.setattr(
        gateway, "_provider_preflight",
        lambda arguments: (_ for _ in ()).throw(AssertionError("quarantined dispatch must not preflight")),
    )
    arguments = {
        "task_id": task_id, "what": what, "why": why,
        "worker": "auto", "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
        "workforce_demands": demands, "workforce_admission": blocked,
        "planner_output": internal["planner_output"],
        **internal["task_card_evidence"],
    }
    response = gateway.handle({"jsonrpc": "2.0", "id": 804, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": arguments}})
    assert response["result"]["isError"] is True
    assert "WORKFORCE_CALLER_EVIDENCE_MISMATCH:workforce_admission" in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


def test_worker_candidate_rejects_owner_without_submit():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    args = {"what": "x", "why": "y", "worker": "worker-a", "allowed_files": ["README.md"], "verifier_commands": ["git diff --check"], "owner_confirmation": False}
    response = gateway.handle({"jsonrpc": "2.0", "id": 45, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is True
    assert "OWNER_CONFIRMATION_REQUIRED" in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


def test_worker_candidate_preflight_failure_submits_nothing(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: {"status": "BLOCKED", "blocker": "VERSION_FAILED"})
    args = _worker_args("preflight-failure")
    response = gateway.handle({"jsonrpc": "2.0", "id": 46, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is True
    assert service.submitted == []


def test_worker_candidate_rejects_verifier_injection_before_preflight(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: (_ for _ in ()).throw(AssertionError("preflight must not run")))
    args = _worker_args("verifier-injection")
    args["verifier_commands"] = ["git diff --check; rm -rf /"]
    response = gateway.handle({"jsonrpc": "2.0", "id": 47, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is True
    assert service.submitted == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("worker", "other-worker", "WORKFORCE_ADMISSION_WORKER_MISMATCH"),
        ("provider", "other-provider", "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
        ("model", "other-model", "WORKFORCE_ADMISSION_MODEL_MISMATCH"),
    ],
)
def test_worker_candidate_rejects_caller_identity_swap_before_preflight(monkeypatch, field, value, code):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(
        gateway,
        "_provider_preflight",
        lambda arguments: (_ for _ in ()).throw(AssertionError("identity mismatch must precede preflight")),
    )
    args = _worker_args(f"identity-swap-{field}")
    args[field] = value
    response = gateway.handle({"jsonrpc": "2.0", "id": 48, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is True
    assert code in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


def test_worker_candidate_rejects_owner_inline_without_tracked_card_before_preflight(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(
        gateway,
        "_provider_preflight",
        lambda arguments: (_ for _ in ()).throw(AssertionError("missing card must precede preflight")),
    )
    args = {
        "task_id": "owner-inline-not-allowed", "what": "x", "why": "y", "worker": "auto",
        "allowed_files": ["README.md"], "verifier_commands": ["git diff --check"],
        "owner_confirmation": True,
    }
    response = gateway.handle({"jsonrpc": "2.0", "id": 49, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is True

[Showing lines 1-1052 of 4905 (50.0KB limit). Use offset=1053 to continue.]