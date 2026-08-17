import hashlib
import io
import json
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

from nexus.engine.canonical_task_seam import (  # noqa: E402
    VerifiedTaskCardIdentity,
    build_canonical_planner_admission,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService  # noqa: E402
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
)
from nexus.services.model_workforce_policy import WorkforcePolicyLoader  # noqa: E402
from nexus.services.runtime_workforce_admission import (  # noqa: E402
    evaluate_runtime_workforce_admission,
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
        {"online": {"worker_id": "agy_flash", "provider": "agy", "model": "gemini-3.6-flash-high", "controls": ["task_card", "allowed_files", "mandatory_commands", "independent_verification"]}},
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
    monkeypatch,
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

    result = build_canonical_planner_admission(
        task_id="canonical-policy-routing",
        task_text="implement one bounded change",
        allowed_files=("bounded.py",),
        verifier_command=("pytest -q tests/bounded.py",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id="canonical-policy-routing",
            task_card_path="tasks/test/canonical-policy-routing.md",
            canonical_task_card_path="/tmp/canonical-policy-routing.md",
            task_card_hash="a" * 64,
        ),
    )

    assert reordered.routing["online"]["fast_bounded_implementation"] == "agy_flash"
    assert result["binding"]["worker_id"] == "agy_flash"
    assert result["workforce_admission"]["records"][0]["request"][
        "requested_worker_id"
    ] == "agy_flash"


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
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
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
    assert request["model"] == "gemini-3.6-flash-high"
    assert request["worker"] == "agy"
    assert request["worker_id"] == "agy_flash"
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
        provider="agy", requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
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
        provider="agy", requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
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
        provider="agy", requested_model="gemini-3.6-flash-high",
        resolved_model="gemini-3.6-flash-high",
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
    assert "TRACKED_TASK_CARD_REQUIRED" in response["result"]["structuredContent"]["error"]
    assert service.submitted == []


@pytest.mark.parametrize(
    "case",
    [
        "missing_path", "missing_hash", "wrong_hash", "uppercase_hash",
        "task_id_mismatch", "path_escape", "content_drift",
    ],
)
def test_worker_candidate_rejects_untrusted_card_evidence_before_planner_or_any_dispatch(
    monkeypatch, case,
):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    task_id = f"card-evidence-{case}"
    args = _worker_args(task_id)
    card_path = _TEST_CARD_ROOT / args["task_card_path"]
    if case == "missing_path":
        args.pop("task_card_path")
    elif case == "missing_hash":
        args.pop("task_card_hash")
    elif case == "wrong_hash":
        args["task_card_hash"] = "0" * 64
    elif case == "uppercase_hash":
        args["task_card_hash"] = args["task_card_hash"].upper()
    elif case == "task_id_mismatch":
        args.update(_task_card_evidence(task_id, content="task_id: `different-task`\nAUTO_CHAIN: false\n"))
    elif case == "path_escape":
        args["task_card_path"] = "../outside.md"
    elif case == "content_drift":
        card_path.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\ndrift: true\n", encoding="utf-8")

    calls = {"planner": 0, "preflight": 0, "registry": 0}

    def reject_planner(**kwargs):
        calls["planner"] += 1
        raise AssertionError("unverified card must not reach planner")

    def reject_preflight(arguments):
        calls["preflight"] += 1
        raise AssertionError("unverified card must not reach preflight")

    def reject_registry(*args, **kwargs):
        calls["registry"] += 1
        raise AssertionError("unverified card must not reach WorkerRegistry")

    monkeypatch.setattr(
        sys.modules["nexus.orchestrator.unified_mcp_gateway"],
        "build_canonical_planner_admission",
        reject_planner,
    )
    monkeypatch.setattr(gateway, "_provider_preflight", reject_preflight)
    monkeypatch.setattr("nexus.executors.worker_registry.WorkerRegistry.invoke", reject_registry)
    response = gateway.handle({
        "jsonrpc": "2.0", "id": 490, "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": args},
    })
    assert response["result"]["isError"] is True
    assert calls == {"planner": 0, "preflight": 0, "registry": 0}
    assert service.submitted == []


def test_worker_candidate_rechecks_card_drift_after_planner_before_preflight(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    args = _worker_args("card-drift-after-planner")
    card = _TEST_CARD_ROOT / args["task_card_path"]
    gateway_module = sys.modules["nexus.orchestrator.unified_mcp_gateway"]
    real_planner = gateway_module.build_canonical_planner_admission
    calls = {"planner": 0, "preflight": 0, "registry": 0}

    def planning_then_drift(**kwargs):
        calls["planner"] += 1
        result = real_planner(**kwargs)
        card.write_text(card.read_text(encoding="utf-8") + "drift: true\n", encoding="utf-8")
        return result

    def reject_preflight(arguments):
        calls["preflight"] += 1
        raise AssertionError("card drift must precede preflight")

    def reject_registry(*args, **kwargs):
        calls["registry"] += 1
        raise AssertionError("card drift must precede WorkerRegistry")

    monkeypatch.setattr(gateway_module, "build_canonical_planner_admission", planning_then_drift)
    monkeypatch.setattr(gateway, "_provider_preflight", reject_preflight)
    monkeypatch.setattr("nexus.executors.worker_registry.WorkerRegistry.invoke", reject_registry)
    response = gateway.handle({
        "jsonrpc": "2.0", "id": 491, "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": args},
    })
    assert response["result"]["isError"] is True
    assert "TASK_CARD_DRIFT" in response["result"]["structuredContent"]["error"]
    assert calls == {"planner": 1, "preflight": 0, "registry": 0}
    assert service.submitted == []


def test_worker_candidate_preserves_service_status(monkeypatch):
    class StatusService(FakeService):
        def submit_task(self, request):
            self.submitted.append(request)
            return {"status": "SUBMITTED", "task_id": request["task_id"], "duplicate": False}
    service = StatusService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    args = _worker_args("preserve-service-status")
    response = gateway.handle({"jsonrpc": "2.0", "id": 49, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["structuredContent"]["status"] == "SUBMITTED"




def test_worker_candidate_rejects_bound_request_tamper():
    from nexus.contracts.lifecycle_action import (
        LifecycleActionType,
        MutationDomain,
        PermissionProfile,
        build_action_envelope,
    )
    from nexus.orchestrator.self_hosted_task_service import _validated_action_request
    bound = {"task_id": "tamper-1", "attempt_id": "attempt-1", "action_id": "action-1", "idempotency_key": "idem-1", "action_type": "TASK_RUN", "contract_kind": "OWNER_INLINE", "controller_revision": "a" * 40, "allowed_files": ["README.md"]}
    action = build_action_envelope(task_id="tamper-1", action_type=LifecycleActionType.TASK_RUN, request=bound, tool_manifest_hash="b" * 64, expected_head="a" * 40, allowed_paths=["README.md"], mutation=True, contract_kind="OWNER_INLINE", contract_hash="c" * 64, permission_profile=PermissionProfile.MUTATE_BOUNDED, mutation_domain=MutationDomain.TARGET, attempt_id="attempt-1", action_id="action-1", idempotency_key="idem-1").model_dump(mode="json")
    bound["controller_revision"] = "d" * 40
    with __import__("pytest").raises(ValueError, match="BOUND_ACTION_REQUEST_HASH_MISMATCH"):
        _validated_action_request({"action": action, "bound_action_request": bound})


def test_worker_candidate_semantic_replay_and_conflict_use_service_gate(monkeypatch, tmp_path):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    args = _worker_args("semantic-replay")
    gateway.handle({"jsonrpc": "2.0", "id": 60, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    prior = service.submitted[0]
    real = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    built_contract = real.build_contract(prior)
    assert built_contract.protected_contracts == []
    state = {"task_id": prior["task_id"], "status": "SUBMITTED", "request": prior, "action_id": prior["action_id"], "idempotency_key": prior["idempotency_key"]}
    monkeypatch.setattr(real, "_submission_task_states", lambda: {prior["task_id"]: state})
    duplicate = real.submit_task(prior)
    assert duplicate["duplicate"] is True
    prior_state = dict(prior)
    prior_state["why"] = "previous semantic request"
    monkeypatch.setattr(real, "_submission_task_states", lambda: {prior["task_id"]: {**state, "request": prior_state}})
    conflict = dict(prior)
    conflict["why"] = "changed"
    replay = real.submit_task(conflict)
    assert replay["duplicate"] is True


def test_worker_candidate_source_guard_has_no_promotion_or_direct_apply_calls():
    import inspect
    source = inspect.getsource(UnifiedMCPGateway._worker_candidate)
    for forbidden in ("approve", "integrate", "push", "_apply_assisted_patch", "complete_direct_canonical"):
        assert forbidden not in source


def test_worker_candidate_explicit_authority_confirmation_binds_marker(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    args = _worker_args(
        "authority-candidate", what="authority change", why="explicit owner review",
        allowed_files=["nexus/orchestrator/unified_mcp_gateway.py"],
    )
    args["authority_change_candidate_confirmation"] = True
    response = gateway.handle({"jsonrpc": "2.0", "id": 71, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is False
    request = service.submitted[0]
    assert request["protected_contracts"] == ["repository-authority-change.v1"]
    assert request["authority_change_candidate_confirmation"] is True
    assert request["contract_kind"] == "TRACKED_TASK_CARD"
    assert request["owner_inline_contract"] is None
    assert request["bound_action_request"]["authority_change_candidate_confirmation"] is True


def test_worker_candidate_rejects_raw_authority_fields_before_submit(monkeypatch):
    for field, value in (
        ("protected_contracts", ["repository-authority-change.v1"]),
        ("approval_context", {"approved": True}),
        ("architecture_approval", {"schema": "nexus.architecture_approval.v1"}),
        ("integration_authorization", {"approved": True}),
    ):
        service = FakeService()
        gateway = UnifiedMCPGateway(service=service)
        args = {
            "what": "x", "why": "y", "worker": "worker-a", "allowed_files": ["README.md"],
            "verifier_commands": ["git diff --check"], "owner_confirmation": True,
            field: value,
        }
        response = gateway.handle({"jsonrpc": "2.0", "id": 72, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
        assert response["result"]["isError"] is True
        assert "WORKER_CANDIDATE_UNKNOWN_FIELDS" in response["result"]["structuredContent"]["error"]
        assert service.submitted == []


def test_worker_candidate_authority_confirmation_tamper_breaks_bound_hash(monkeypatch):
    from nexus.orchestrator.self_hosted_task_service import _validated_action_request

    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    args = _worker_args(
        "authority-tamper", what="authority change", why="explicit owner review",
        allowed_files=["nexus/orchestrator/unified_mcp_gateway.py"],
    )
    args["authority_change_candidate_confirmation"] = True
    gateway.handle({"jsonrpc": "2.0", "id": 73, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    request = dict(service.submitted[0])
    bound = dict(request["bound_action_request"])
    bound["authority_change_candidate_confirmation"] = False
    request["bound_action_request"] = bound
    with __import__("pytest").raises(ValueError, match="BOUND_ACTION_REQUEST_HASH_MISMATCH"):
        _validated_action_request(request)


def test_worker_candidate_explicit_authority_binding_rejects_identity_tamper(monkeypatch):
    from nexus.orchestrator.self_hosted_task_service import _validated_action_request

    gateway = UnifiedMCPGateway(service=FakeService())
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    args = _worker_args(
        "authority-identity", what="authority change", why="explicit owner review",
        allowed_files=["nexus/orchestrator/unified_mcp_gateway.py"],
    )
    args["authority_change_candidate_confirmation"] = True
    gateway.handle({"jsonrpc": "2.0", "id": 74, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    # Generate one exact request, then prove each identity dimension is bound.
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    gateway.handle({"jsonrpc": "2.0", "id": 75, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    original = service.submitted[0]
    for field, value in (
        ("task_id", "other-task"),
        ("controller_revision", "b" * 40),
        ("allowed_files", ["README.md"]),
        ("authority_change_candidate_confirmation", False),
    ):
        tampered = dict(original)
        bound = dict(original["bound_action_request"])
        bound[field] = value
        tampered["bound_action_request"] = bound
        with __import__("pytest").raises(ValueError, match="BOUND_ACTION_REQUEST_HASH_MISMATCH"):
            _validated_action_request(tampered)


def test_worker_candidate_ordinary_to_authority_same_task_remains_tracked(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    ordinary = _worker_args("authority-replay", what="bounded change", why="ordinary request")
    gateway.handle({"jsonrpc": "2.0", "id": 76, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": ordinary}})
    prior = service.submitted[0]
    authority = dict(ordinary)
    authority["authority_change_candidate_confirmation"] = True
    gateway.handle({"jsonrpc": "2.0", "id": 77, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": authority}})
    current = service.submitted[1]
    assert prior["contract_kind"] == current["contract_kind"] == "TRACKED_TASK_CARD"
    assert prior["task_card_path"] == current["task_card_path"]
    assert prior["task_card_hash"] == current["task_card_hash"]
    assert current["owner_inline_contract"] is None


def test_worker_candidate_head_drift_fails_before_submit(monkeypatch):
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    from nexus.orchestrator.lifecycle_guards import LifecycleGuardError
    monkeypatch.setattr(sys.modules["nexus.orchestrator.unified_mcp_gateway"], "pre_action_guard", lambda *args, **kwargs: (_ for _ in ()).throw(LifecycleGuardError("HEAD_DRIFT", "head changed")))
    args = _worker_args("head-drift")
    response = gateway.handle({"jsonrpc": "2.0", "id": 61, "method": "tools/call", "params": {"name": "nexus_worker_candidate", "arguments": args}})
    assert response["result"]["isError"] is True
    assert service.submitted == []


def test_manifest_status_and_recommended_tools_share_tools_list_truth():
    gateway = UnifiedMCPGateway(service=FakeService())
    names = tuple(tool["name"] for tool in gateway.tool_specs())
    assert names == PUBLIC_TOOL_NAMES
    assert "nexus_model_calibration_evidence" in names
    assert "nexus_model_calibration_plan" in names
    assert TOOL_MANIFEST_REVISION
    recomputed_schema = hashlib.sha256(
        json.dumps(
            UnifiedMCPGateway.tool_specs(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    assert recomputed_schema == FULL_TOOL_SCHEMA_HASH
    assert TOOL_MANIFEST_REVISION == hashlib.sha256(
        json.dumps(names, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert {"nexus_provider_preflight", "nexus_task_card_create", "nexus_model_probe", "nexus_model_probe_result"}.issubset(set(names))
    assert gateway.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "nexus_gateway_status", "arguments": {}}})["result"]["structuredContent"]["tool_count"] == len(names)


def test_calibration_evidence_action_resolves_lineage_and_fails_closed():
    gateway = UnifiedMCPGateway(service=FakeService())
    by_id = gateway.handle({"jsonrpc": "2.0", "id": 900, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"lineage_id": "deepseek-v4-flash"}}})
    payload = by_id["result"]["structuredContent"]
    assert payload["schema"] == "nexus.model_calibration_evidence.v1"
    assert payload["lineage_id"] == "deepseek-v4-flash"
    assert payload["stable_floor"] == "L2"
    assert payload["frontier"] == "L3"
    assert payload["admission_authority"] == "SEPARATE_NOT_ESTABLISHED_BY_THIS_ACTION"
    by_identity = gateway.handle({"jsonrpc": "2.0", "id": 901, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"provider": "opencode", "model": "opencode-go/deepseek-v4-flash"}}})
    assert by_identity["result"]["structuredContent"]["lineage_id"] == "deepseek-v4-flash"
    unknown = gateway.handle({"jsonrpc": "2.0", "id": 902, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"provider": "opencode", "model": "opencode/deepseek-v4-flash"}}})
    assert unknown["result"]["isError"] is True
    assert "No registered lineage" in unknown["result"]["structuredContent"]["error"]
    missing = gateway.handle({"jsonrpc": "2.0", "id": 903, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {}}})
    assert missing["result"]["isError"] is True
    dual_selector = gateway.handle({"jsonrpc": "2.0", "id": 912, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"lineage_id": "deepseek-v4-flash", "provider": "opencode", "model": "opencode/deepseek-v4-flash-free"}}})
    assert dual_selector["result"]["isError"] is True
    assert "not both" in dual_selector["result"]["structuredContent"]["error"]
    partial_identity = gateway.handle({"jsonrpc": "2.0", "id": 913, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"provider": "opencode"}}})
    assert partial_identity["result"]["isError"] is True
    assert "together" in partial_identity["result"]["structuredContent"]["error"]


def test_calibration_plan_action_does_not_restart_from_l1():
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 904, "method": "tools/call", "params": {"name": "nexus_model_calibration_plan", "arguments": {"provider": "opencode", "model": "opencode-go/deepseek-v4-flash", "target_role": "compact_code_candidate", "change_kind": "alias_only"}}})
    payload = response["result"]["structuredContent"]
    assert payload["schema"] == "nexus.model_calibration_plan.v1"
    assert payload["change_class"] == "ALIAS_ONLY"
    assert payload["stable_floor"] == "L2"
    assert payload["current_frontier"] == "L3"
    assert payload["admission_authority"] == "SEPARATE_NOT_ESTABLISHED_BY_THIS_ACTION"
    kinds = [trial["kind"] for trial in payload["required_trials"]]
    assert "IDENTITY_RESOLUTION" in kinds and "TRANSPORT_PREFLIGHT" in kinds
    assert "STABLE_FLOOR_REGRESSION" in kinds and "FRONTIER_EVALUATION" in kinds
    assert [trial["tier"] for trial in payload["not_required_trials"]] == ["L0", "L0.25", "L0.5", "L1"]
    assert not any(trial["tier"] in {"L0", "L0.25", "L0.5", "L1"} for trial in payload["required_trials"])


def test_calibration_plan_action_fails_closed_on_unknown_material_change():
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 905, "method": "tools/call", "params": {"name": "nexus_model_calibration_plan", "arguments": {"provider": "opencode", "model": "opencode/deepseek-v4-flash-free", "target_role": "compact_code_candidate", "change_kind": "unknown_material_change"}}})
    payload = response["result"]["structuredContent"]
    assert payload["change_class"] == "UNKNOWN_MATERIAL_CHANGE"
    assert payload["plan_status"] == "FAIL_CLOSED"
    assert payload["required_trials"] == []


def test_calibration_actions_never_call_provider_or_submit_tasks(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("calibration actions must never spawn a provider subprocess")

    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", _fail)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", _fail)
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    gateway.handle({"jsonrpc": "2.0", "id": 906, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"lineage_id": "deepseek-v4-flash"}}})
    gateway.handle({"jsonrpc": "2.0", "id": 907, "method": "tools/call", "params": {"name": "nexus_model_calibration_plan", "arguments": {"provider": "opencode", "model": "opencode-go/deepseek-v4-flash", "target_role": "compact_code_candidate", "change_kind": "alias_only"}}})
    assert service.submitted == []
    assert service.approved_binding is None


def test_calibration_actions_do_not_mutate_gateway_state(tmp_path):
    service = FakeService()
    service.state_dir = tmp_path
    gateway = UnifiedMCPGateway(service=service)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file())
    gateway.handle({"jsonrpc": "2.0", "id": 908, "method": "tools/call", "params": {"name": "nexus_model_calibration_evidence", "arguments": {"lineage_id": "gemini-3.7-flash-medium"}}})
    gateway.handle({"jsonrpc": "2.0", "id": 909, "method": "tools/call", "params": {"name": "nexus_model_calibration_plan", "arguments": {"provider": "agy", "model": "gemini-3.7-flash-medium", "target_role": "focused_verification", "change_kind": "model_revision_or_backend_change"}}})
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file())
    assert before == after


def test_calibration_plan_action_invalidates_semantic_evidence_on_backend_change():
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 910, "method": "tools/call", "params": {"name": "nexus_model_calibration_plan", "arguments": {"provider": "agy", "model": "gemini-3.7-flash-medium", "target_role": "focused_verification", "change_kind": "model_revision_or_backend_change"}}})
    payload = response["result"]["structuredContent"]
    assert payload["change_class"] == "MODEL_REVISION_OR_BACKEND_CHANGE"
    assert payload["invalidated_evidence"]
    assert all(entry["scope"] == "SEMANTIC" for entry in payload["invalidated_evidence"])
    assert not any(entry["scope"] == "SEMANTIC" for entry in payload["reusable_evidence"])


def test_calibration_plan_action_rejects_invalid_change_kind():
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 911, "method": "tools/call", "params": {"name": "nexus_model_calibration_plan", "arguments": {"provider": "opencode", "model": "opencode/deepseek-v4-flash-free", "target_role": "compact_code_candidate", "change_kind": "made_up_kind"}}})
    assert response["result"]["isError"] is True
    assert "change_kind" in response["result"]["structuredContent"]["error"]


def test_model_probe_tool_schema_remains_unchanged():
    spec = next(item for item in UnifiedMCPGateway.tool_specs() if item["name"] == "nexus_model_probe")
    schema = spec["inputSchema"]
    assert set(schema["required"]) == {"provider", "model", "prompt", "output_schema"}
    assert schema["properties"]["context_arm"]["enum"] == ["bare", "nexus_bounded", "nexus_full"]
    assert schema["properties"]["workspace_mode"]["default"] == "isolated"
    assert spec["description"].startswith("Run one schema-bound model probe")
    result_spec = next(item for item in UnifiedMCPGateway.tool_specs() if item["name"] == "nexus_model_probe_result")
    assert result_spec["inputSchema"]["required"] == ["task_id"]


def test_public_candidate_approve_schema_requires_versioned_approval():
    spec = next(item for item in UnifiedMCPGateway.tool_specs() if item["name"] == "nexus_candidate_approve")
    schema = spec["inputSchema"]
    assert "approval" in schema["required"]
    approval = schema["properties"]["approval"]
    assert approval["properties"]["schema"]["const"] == "nexus.approval.v2"
    assert approval["properties"]["approval_scope"]["const"] == "ALLOW_ACTION_ONCE"
    assert {"contract_kind", "contract_hash", "task_card_hash"}.issubset(set(approval["required"]))
    assert approval["properties"]["task_card_hash"]["type"] == ["string", "null"]
    assert approval["additionalProperties"] is False
    architecture = approval["properties"]["architecture_approval"]
    assert set(architecture["required"]) == {"schema", "approval_id", "approved_by", "issued_at", "expires_at", "approval_scope", "bound_task_id", "bound_attempt_id", "candidate_commit_sha", "candidate_tree_sha", "authority_findings_sha256"}
    assert architecture["additionalProperties"] is False


def test_public_candidate_closure_schema_is_typed_and_closed():
    spec = next(item for item in UnifiedMCPGateway.tool_specs() if item["name"] == "nexus_candidate_bind_integration")
    schema = spec["inputSchema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"task_id", "expected_canonical_head", "external_acceptance", "approval"}
    acceptance = schema["properties"]["external_acceptance"]
    assert acceptance["properties"]["schema"]["const"] == "nexus.external_acceptance_receipt.v1"
    assert acceptance["additionalProperties"] is False
    approval = schema["properties"]["approval"]
    assert approval["properties"]["bound_action_type"]["const"] == "CANDIDATE_INTEGRATE"
    assert approval["additionalProperties"] is False


def test_candidate_closure_dispatches_bind_only():
    gateway = UnifiedMCPGateway(service=FakeService())
    calls = []
    gateway._candidate_bind_integration = lambda arguments: calls.append("bind") or {"integration_performed": False}
    gateway._candidate_integrate = lambda arguments: calls.append("integrate") or {"status": "INTEGRATED"}
    assert gateway._call_tool("nexus_candidate_bind_integration", {"task_id": "t"})["integration_performed"] is False
    assert calls == ["bind"]


def test_candidate_approve_forwards_nested_architecture_ack_unchanged():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    now = datetime.now(timezone.utc)
    architecture = {
        "schema": "nexus.architecture_approval.v1", "approval_id": "arch", "approved_by": "owner",
        "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "approval_scope": "ALLOW_ACTION_ONCE", "bound_task_id": "recover-1", "bound_attempt_id": "attempt-recovery",
        "candidate_commit_sha": "a" * 40, "candidate_tree_sha": "a" * 40, "authority_findings_sha256": "e" * 64,
    }
    approval = _approval()
    approval["architecture_approval"] = architecture
    response = gateway.handle({"jsonrpc": "2.0", "id": 415, "method": "tools/call", "params": {"name": "nexus_candidate_approve", "arguments": {
        "task_id": "recover-1", "candidate_commit_sha": "a" * 40, "candidate_tree_sha": "a" * 40,
        "candidate_state_hash": "b" * 64, "verified_receipt_hash": "b" * 64, "approval": approval,
    }}})
    assert response["result"]["structuredContent"]["status"] == "APPROVED"
    assert service.approved_binding["approval_grant"]["architecture_approval"] == architecture


def _approval(task_id="recover-1", attempt_id="attempt-recovery", *, contract_kind="TRACKED_TASK_CARD", contract_hash="c" * 64, task_card_hash="c" * 64, owner_inline_contract=None):
    return {
        "schema": "nexus.approval.v2",
        "approval_id": "approval-recovery",
        "approved_by": "James",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "bound_task_id": task_id,
        "bound_attempt_id": attempt_id,
        "bound_action_type": "CANDIDATE_APPROVE",
        "approval_scope": "ALLOW_ACTION_ONCE",
        "contract_kind": contract_kind,
        "contract_hash": contract_hash,
        "task_card_hash": task_card_hash,
        "tool_manifest_hash": TOOL_MANIFEST_REVISION,
        "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
        "permission_policy_hash": PERMISSION_POLICY_HASH,
        "lifecycle_revision": LIFECYCLE_REVISION,
        "server_instance_id": SERVER_INSTANCE_ID,
    }


def test_owner_inline_candidate_approval_uses_generic_contract_binding(monkeypatch):
    from nexus.contracts.lifecycle_action import build_owner_inline_contract

    service = FakeService()
    inline = build_owner_inline_contract(
        task_id="recover-1",
        objective="bounded owner inline candidate",
        allowed_files=["README.md"],
        verifier_commands=["git diff --check"],
        expected_head="a" * 40,
        issued_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )
    original_snapshot = service.get_task_snapshot

    def owner_snapshot(task_id, *, include_details=False):
        state = original_snapshot(task_id, include_details=include_details)
        state.update({
            "contract_kind": "OWNER_INLINE",
            "contract_hash": "f" * 64,
            "owner_inline_contract": inline,
            "task_card_hash": None,
        })
        return state

    service.get_task_snapshot = owner_snapshot
    gateway = UnifiedMCPGateway(service=service)
    wrong_approval = _approval(
        contract_kind="OWNER_INLINE",
        contract_hash="f" * 64,
        task_card_hash=None,
        owner_inline_contract=inline,
    )
    rejected = gateway.handle({"jsonrpc": "2.0", "id": 413, "method": "tools/call", "params": {"name": "nexus_candidate_approve", "arguments": {
        "task_id": "recover-1", "candidate_commit_sha": "a" * 40, "candidate_tree_sha": "a" * 40,
        "candidate_state_hash": "b" * 64, "verified_receipt_hash": "b" * 64, "approval": wrong_approval,
    }}})
    assert rejected["result"]["isError"] is True
    assert service.approved_binding is None
    approval = _approval(
        contract_kind="OWNER_INLINE",
        contract_hash=inline["contract_hash"],
        task_card_hash=None,
        owner_inline_contract=inline,
    )
    response = gateway.handle({"jsonrpc": "2.0", "id": 414, "method": "tools/call", "params": {"name": "nexus_candidate_approve", "arguments": {
        "task_id": "recover-1", "candidate_commit_sha": "a" * 40, "candidate_tree_sha": "a" * 40,
        "candidate_state_hash": "b" * 64, "verified_receipt_hash": "b" * 64, "approval": approval,
    }}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "APPROVED"
    assert payload["approval_receipt"]["contract_kind"] == "OWNER_INLINE"
    assert payload["approval_receipt"]["contract_hash"] == inline["contract_hash"]
    assert service.approved_binding["approval_grant"]["contract_hash"] == inline["contract_hash"]


def test_owner_inline_gateway_bind_and_integrate_forward_nested_hash(monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module
    from nexus.contracts.lifecycle_action import build_owner_inline_contract

    service = FakeService()
    inline = build_owner_inline_contract(
        task_id="recover-1",
        objective="bind exact nested owner inline identity",
        allowed_files=["README.md"],
        verifier_commands=["git diff --check"],
        expected_head="a" * 40,
        issued_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )
    approval = _approval(
        contract_kind="OWNER_INLINE",
        contract_hash=inline["contract_hash"],
        task_card_hash=None,
        owner_inline_contract=inline,
    )
    approval.update({
        "bound_action_type": "CANDIDATE_INTEGRATE",
        "expected_canonical_head": "a" * 40,
        "integration_branch": "nexus/integration/main",
        "candidate_commit_sha": "a" * 40,
        "candidate_tree_sha": "a" * 40,
        "candidate_state_hash": "b" * 64,
        "verified_receipt_hash": "b" * 64,
        "acceptance_receipt_hash": "d" * 64,
    })
    service.approved_binding = {"approval_grant": approval}
    original_snapshot = service.get_task_snapshot

    def owner_snapshot(task_id, *, include_details=False):
        state = original_snapshot(task_id, include_details=include_details)
        state.update({
            "contract_kind": "OWNER_INLINE",
            "contract_hash": "f" * 64,
            "owner_inline_contract": inline,
            "task_card_hash": None,
            "integration_approval_grant": {**approval, "consumed_at": datetime.now(timezone.utc).isoformat()},
            "integration_authorization": {"expected_canonical_head": "a" * 40},
        })
        return state

    service.get_task_snapshot = owner_snapshot
    monkeypatch.setattr(
        gateway_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="a" * 40 + "\n", stderr=""),
    )
    monkeypatch.setattr(gateway_module, "pre_action_guard", lambda *args, **kwargs: {"gate_passed": True})
    gateway = UnifiedMCPGateway(service=service)
    acceptance = {
        "schema": "nexus.external_acceptance_receipt.v1",
        "task_id": "recover-1",
        "attempt_id": "attempt-recovery",
        "candidate_commit": "a" * 40,
        "receipt_hash": "d" * 64,
        "reviewer_id": "James",
        "passed": True,
        "verifier_artifact": "/tmp/not-read-by-fake-service",
    }
    bound = gateway._candidate_bind_integration({
        "task_id": "recover-1",
        "expected_canonical_head": "a" * 40,
        "external_acceptance": acceptance,
        "approval": approval,
    })
    assert bound["integration_performed"] is False
    assert service.bound_runtime_identity["contract_hash"] == inline["contract_hash"]
    assert service.bound_runtime_identity["owner_inline_contract"] == inline

    approval["contract_hash"] = "f" * 64
    with pytest.raises(Exception, match="APPROVAL_BINDING_MISMATCH"):
        gateway._candidate_integrate({"task_id": "recover-1"})
    assert service.integrated_runtime_identity is None
    approval["contract_hash"] = inline["contract_hash"]
    integrated = gateway._candidate_integrate({"task_id": "recover-1"})
    assert integrated["status"] == "INTEGRATED"
    assert service.integrated_runtime_identity["contract_hash"] == inline["contract_hash"]
    assert service.integrated_runtime_identity["owner_inline_contract"] == inline


def test_cline_parser_extracts_final_patch_from_json_event_array():
    events = json.dumps([
        {"type": "system", "content": "started"},
        {"type": "assistant", "message": {"content": "not a candidate"}},
        {"type": "assistant", "content": json.dumps({"patch": "diff --git a/README.md b/README.md", "tests": []})},
    ])
    parsed = UnifiedMCPGateway._decode_assist_payload(events, "cline", require_patch=True)
    assert parsed == {"patch": "diff --git a/README.md b/README.md", "tests": []}


def test_cline_parser_does_not_join_unrelated_json_objects():
    stdout = '{"type":"system","content":"started"}\n{"type":"assistant","message":{"content":"plain answer"}}'
    assert UnifiedMCPGateway._decode_assist_payload(stdout, "cline", require_patch=True) is None


def test_gateway_read_and_snapshot_are_bounded():
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    gateway = UnifiedMCPGateway(service=FakeService())
    snapshot = gateway.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nexus_workspace_snapshot", "arguments": {}}})
    read = gateway.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nexus_read", "arguments": {"path": "AGENTS.md", "max_lines": 2}}})
    assert snapshot["result"]["structuredContent"]["root"] == str(gateway_module.CANONICAL_SOURCE_ROOT)
    assert snapshot["result"]["structuredContent"]["registered_worktree_count"] >= 1
    assert len(read["result"]["structuredContent"]["lines"]) == 2


def test_gateway_rejects_traversal_and_arbitrary_git_revision():
    gateway = UnifiedMCPGateway(service=FakeService())
    traversal = gateway.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nexus_read", "arguments": {"path": "../AGENTS.md"}}})
    bad_diff = gateway.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nexus_git_diff", "arguments": {"base_revision": "HEAD;rm"}}})
    assert traversal["result"]["isError"] is True
    assert bad_diff["result"]["isError"] is True


def test_gateway_forwards_high_level_lifecycle_actions():
    gateway = UnifiedMCPGateway(service=FakeService())
    status = gateway.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "nexus_task_status", "arguments": {"task_id": "t1"}}})
    finish = gateway.handle({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "nexus_task_finish", "arguments": {"execution_lane": "DIRECT_CANONICAL", "request": {"task_id": "t1"}, "expected_commit_sha": "a" * 40}}})
    cancel = gateway.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "nexus_task_cancel", "arguments": {"task_id": "t1"}}})
    assert status["result"]["structuredContent"]["status"] == "PENDING_HUMAN_APPROVAL"
    assert finish["result"]["structuredContent"]["status"] == "DIRECT_CANONICAL_COMPLETED"
    assert cancel["result"]["structuredContent"]["status"] == "CANCELLED"


def test_gateway_status_and_wait_return_read_only_not_found_envelopes():
    class MissingTaskService(FakeService):
        def __init__(self):
            super().__init__()
            self.reconcile_reads = 0
            self.snapshot_reads = 0

        def get_task(self, task_id):
            self.reconcile_reads += 1
            return None

        def get_task_snapshot(self, task_id, *, include_details=False):
            self.snapshot_reads += 1
            return None

        def wait_task(self, task_id, **kwargs):
            return None

    service = MissingTaskService()
    gateway = UnifiedMCPGateway(service=service)

    status = gateway.handle({
        "jsonrpc": "2.0",
        "id": 701,
        "method": "tools/call",
        "params": {"name": "nexus_task_status", "arguments": {"task_id": "missing-task"}},
    })
    waited = gateway.handle({
        "jsonrpc": "2.0",
        "id": 702,
        "method": "tools/call",
        "params": {"name": "nexus_task_wait", "arguments": {"task_id": "missing-task"}},
    })

    for response in (status, waited):
        assert response["result"]["isError"] is False
        payload = response["result"]["structuredContent"]
        assert payload["status"] == "NOT_FOUND"
        assert payload["found"] is False
        assert payload["retry_authorized"] is False
        assert payload["task_action"]["next_action"] == "none"
    assert service.reconcile_reads == 0
    assert service.snapshot_reads == 1


def test_wait_forwards_bounded_timeout_and_returns_next_action():
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 16, "method": "tools/call", "params": {"name": "nexus_task_wait", "arguments": {"task_id": "t1", "timeout_seconds": 999, "poll_interval_seconds": 9}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "PENDING_HUMAN_APPROVAL"
    assert payload["task_action"]["next_action"] == "owner_finish"
    assert payload["wait"]["timeout_seconds"] == 60.0
    assert payload["wait"]["poll_interval_seconds"] == 5.0


def test_minimal_direct_finish_derives_canonical_target_fields():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    base = "a" * 40
    response = gateway.handle({"jsonrpc": "2.0", "id": 15, "method": "tools/call", "params": {"name": "nexus_task_finish", "arguments": {"execution_lane": "DIRECT_CANONICAL", "task_id": "direct-1", "controller_revision": base, "allowed_files": ["README.md"]}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "DIRECT_CANONICAL_COMPLETED"
    assert payload["task_id"] == "direct-1"


def test_minimal_direct_finish_accepts_public_base_sha_alias():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    base = "b" * 40
    response = gateway.handle({"jsonrpc": "2.0", "id": 17, "method": "tools/call", "params": {"name": "nexus_task_finish", "arguments": {"execution_lane": "DIRECT_CANONICAL", "task_id": "direct-base-sha", "base_sha": base, "allowed_files": ["README.md"]}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "DIRECT_CANONICAL_COMPLETED"
    assert service.completed[0]["controller_revision"] == base


def test_public_recovery_surface_has_one_actionable_contract():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    base40 = "a" * 40
    base64 = "b" * 64
    calls = [
        ("nexus_task_list_actionable", {}),
        ("nexus_task_reconcile", {"task_id": "recover-1"}),
        ("nexus_task_retry", {"task_id": "recover-1"}),
        ("nexus_task_resume", {"task_id": "recover-1"}),
        ("nexus_candidate_approve", {"task_id": "recover-1", "candidate_commit_sha": base40, "candidate_tree_sha": base40, "candidate_state_hash": base64, "verified_receipt_hash": base64, "approval": _approval()}),
        ("nexus_candidate_integrate", {"task_id": "recover-1"}),
        ("nexus_candidate_dispose", {"task_id": "recover-1", "disposition": "REJECTED"}),
    ]
    for index, (name, arguments) in enumerate(calls):
        response = gateway.handle({"jsonrpc": "2.0", "id": 500 + index, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        payload = response["result"]["structuredContent"]
        assert payload["schema"] == "nexus.lifecycle_recovery.v1" or payload["schema"] == "nexus.task_actionable_list.v1"
        if name != "nexus_task_list_actionable":
            assert {"task_id", "attempt_id", "last_action_id", "status", "attention_required", "next_action", "recommended_tool", "candidate_binding", "cleanup_status", "uncertain_mutation"} <= set(payload)


def test_public_recovery_surface_rejects_malformed_candidate_hash():
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 501, "method": "tools/call", "params": {"name": "nexus_candidate_approve", "arguments": {"task_id": "recover-1", "candidate_commit_sha": "not-a-sha", "candidate_tree_sha": "a" * 40, "candidate_state_hash": "b" * 64, "verified_receipt_hash": "b" * 64}}})
    assert response["result"]["isError"] is True
    assert "candidate_commit_sha" in response["result"]["structuredContent"]["error"]


def test_gateway_stdio_round_trip():
    gateway = UnifiedMCPGateway(service=FakeService())
    input_stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}}) + "\n")
    output_stream = io.StringIO()
    gateway.serve(input_stream, output_stream)
    response = json.loads(output_stream.getvalue())
    assert response["result"]["tools"][0]["name"] == "nexus_gateway_status"


def test_cline_runner_uses_provider_qualified_model_and_decodes_event_stream(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        event = {
            "type": "run_result",
            "text": json.dumps({"patch": "diff --git a/nexus/__cli_preflight__.txt b/nexus/__cli_preflight__.txt"}),
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(event) + "\n", stderr="")

    monkeypatch.setenv("NEXUS_CLINE_BIN", "/Users/jameschen/.npm-global/lib/node_modules/cline/bin/.cline")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)
    result = UnifiedMCPGateway._run_agy_plan(
        prompt="Return a patch",
        allowed_files=["nexus/__cli_preflight__.txt"],
        provider="cline",
        model="glm-5.2",
    )

    assert result["provider"] == "cline"
    assert result["patch"].startswith("diff --git")
    assert captured["command"][captured["command"].index("--model") + 1] == "cline-pass/glm-5.2"
    assert "--plan" in captured["command"]
    assert captured["command"][captured["command"].index("--auto-approve") + 1] == "false"
    assert captured["command"][captured["command"].index("--timeout") + 1] == "60"
    assert "--yolo" not in captured["command"]


def test_cline_runner_timeout_fails_closed(monkeypatch):
    def timeout_run(command, **kwargs):
        raise __import__("subprocess").TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setenv("NEXUS_CLINE_BIN", "/Users/jameschen/.npm-global/lib/node_modules/cline/bin/.cline")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", timeout_run)
    result = UnifiedMCPGateway._run_agy_plan(prompt="Return a patch", allowed_files=["README.md"], provider="cline", model="glm-5.2")
    assert result["blocker"] == "ASSIST_PROVIDER_TIMEOUT"
    assert result["tool_policy_enforcement"].startswith("cline_plan_auto_approve_false")


def test_grok_runner_uses_positional_prompt(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout=json.dumps({"patch": "diff --git a/a b/a"}), stderr="")

    monkeypatch.setenv("NEXUS_GROK_BIN", "/Users/jameschen/.grok/bin/grok")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)
    result = UnifiedMCPGateway._run_agy_plan(
        prompt="Return a patch",
        allowed_files=["a"],
        provider="grok",
        model="grok-4.5",
    )

    assert result["provider"] == "grok"
    assert captured["command"][captured["command"].index("--single") + 1] == "Return a patch"
    assert "--prompt" not in captured["command"]
    assert "--output-format" in captured["command"]


def test_assist_submit_is_durable_and_task_wait_reads_result(monkeypatch, tmp_path):
    import subprocess as real_subprocess
    real_popen = real_subprocess.Popen

    class FakePopen:
        _next_pid = 54001

        def __init__(self, command, *, stdout, stderr, **kwargs):
            if isinstance(stdout, int):
                self._delegate = real_popen(command, stdout=stdout, stderr=stderr, **kwargs)
                self.pid = self._delegate.pid
                return
            self.pid = FakePopen._next_pid
            FakePopen._next_pid += 1
            self._returncode = 0
            stdout.write(json.dumps({"type": "run_result", "text": json.dumps({"patch": "diff --git a/README.md b/README.md"})}) + "\n")
            stdout.flush()

        def poll(self):
            if hasattr(self, "_delegate"):
                return self._delegate.poll()
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    gateway = UnifiedMCPGateway(service=service)
    submitted = gateway.handle({"jsonrpc": "2.0", "id": 700, "method": "tools/call", "params": {"name": "nexus_assist_submit", "arguments": {"task_id": "async-cline-1", "what": "Suggest a README patch", "why": "Async provider smoke", "allowed_files": ["README.md"], "model": "glm-5.2", "apply": True}}})
    first = submitted["result"]["structuredContent"]
    assert first["status"] == "RUNNING"
    assert first["execution_lane"] == "ASSISTED_CANONICAL"
    assert first["candidate_only"] is True
    assert first["apply_requested"] is False
    assert first["apply_ignored"] is True
    assert first["next_action"] == "nexus_assist_result"
    job_state = json.loads((tmp_path / "assisted_provider_jobs" / "async-cline-1.json").read_text(encoding="utf-8"))
    assert job_state["action"]["mutation"] is False
    assert job_state["action"]["permission_profile"] == "VERIFY"

    waited = gateway.handle({"jsonrpc": "2.0", "id": 701, "method": "tools/call", "params": {"name": "nexus_task_wait", "arguments": {"task_id": "async-cline-1", "timeout_seconds": 1}}})
    result = waited["result"]["structuredContent"]
    assert result["status"] == "COMPLETED"
    assert result["result"]["patch"].startswith("diff --git")
    assert result["exit_code"] == 0
    assert result["stdout_sha256"]
    assert result["artifacts"]["stdout"]


def test_assist_apply_is_ignored_and_cannot_install_mutation_runners():
    import inspect

    injected_model = object()
    injected_apply = object()
    gateway = UnifiedMCPGateway(
        service=FakeService(),
        model_runner=injected_model,
        apply_runner=injected_apply,
    )

    assert gateway._model_runner is UnifiedMCPGateway._run_agy_plan
    assert gateway._ignored_model_runner is injected_model
    assert gateway._ignored_apply_runner is injected_apply
    assert not hasattr(gateway, "_apply_assisted_patch")
    assert not hasattr(gateway, "_validate_assisted_patch")

    assist_source = "\n".join(
        inspect.getsource(getattr(UnifiedMCPGateway, name))
        for name in ("_assist_submit", "_assist_response")
    )
    for forbidden in ("git apply", "git commit", "complete_direct_canonical", "approve_promotion", "integrate_approved", "push"):
        assert forbidden not in assist_source


def test_assist_manifest_preserves_worker_candidate_and_typed_approval_tools():
    names = set(PUBLIC_TOOL_NAMES)
    assert "nexus_worker_candidate" in names
    assert {"nexus_candidate_approve", "nexus_candidate_bind_integration", "nexus_candidate_integrate"} <= names


def test_assist_wait_timeout_does_not_cancel_and_explicit_cancel_cleans_workspace(monkeypatch, tmp_path):
    class HangingPopen:
        pid = 54100
        returncode = None

        def __init__(self, command, *, stdout, stderr, **kwargs):
            self.command = command
            stdout.write("partial provider output\\n")
            stdout.flush()
            stderr.write("partial provider warning\\n")
            stderr.flush()

        def poll(self):
            return None

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", HangingPopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    gateway = UnifiedMCPGateway(service=service)
    gateway.handle({"jsonrpc": "2.0", "id": 7010, "method": "tools/call", "params": {"name": "nexus_assist_submit", "arguments": {"task_id": "async-cline-timeout", "what": "Bounded probe", "why": "Poll timeout distinction", "allowed_files": ["README.md"]}}})
    waited = gateway.handle({"jsonrpc": "2.0", "id": 7011, "method": "tools/call", "params": {"name": "nexus_task_wait", "arguments": {"task_id": "async-cline-timeout", "timeout_seconds": 0}}})
    assert waited["result"]["structuredContent"]["status"] == "RUNNING"
    cancelled = gateway.handle({"jsonrpc": "2.0", "id": 7012, "method": "tools/call", "params": {"name": "nexus_assist_cancel", "arguments": {"task_id": "async-cline-timeout"}}})
    receipt = cancelled["result"]["structuredContent"]
    assert receipt["status"] == "CANCELLED"
    assert receipt["process_killed"] is True
    assert receipt["process_cleanup"] is True
    assert receipt["stream_flush_status"] == "FLUSHED"
    assert receipt["stdout_sha256"]
    assert receipt["stderr_sha256"]
    assert receipt["stdout_bytes"] > 0
    assert receipt["stderr_bytes"] > 0
    assert not Path(receipt["workspace_root"]).exists()


def test_provider_preflight_defers_model_probe_without_sync_execution(monkeypatch):
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")

    def fake_run(command, **kwargs):
        assert command[-1] == "--version"
        assert kwargs["cwd"] != Path("/Users/jameschen/Workspace/nexus")
        return SimpleNamespace(returncode=0, stdout="cline 1.2.3\n", stderr="")

    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 703, "method": "tools/call", "params": {"name": "nexus_provider_preflight", "arguments": {"provider": "cline", "model": "glm-5.2", "probe": True}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "VERSION_VERIFIED"
    assert payload["blocker"] == "MODEL_PROBE_ASYNC_REQUIRED"
    assert payload["next_action"] == "nexus_model_probe"
    assert payload["requested_model"] == "glm-5.2"
    assert payload["resolved_model"] == "cline-pass/glm-5.2"
    assert payload["binary_found"] is True
    assert payload["authenticated"] is False
    assert payload["model_reachable"] is False
    assert payload["requested_model_verified"] is False
    assert payload["binary_sha256"]
    assert payload["stdout_sha256"] is None


def test_version_verified_alone_never_authorizes_worker_execution():
    gateway = UnifiedMCPGateway(service=FakeService())
    ready, blocker = gateway._provider_execution_ready(
        {
            "status": "VERSION_VERIFIED",
            "provider": "agy",
            "model_reachable": True,
            "requested_model_verified": True,
            "authenticated": True,
        },
        provider="agy",
    )
    assert ready is False
    assert blocker == "MODEL_PROBE_REQUIRED"


def test_initial_exact_preflight_requires_probe_and_submits_nothing(monkeypatch, tmp_path):
    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")

    def fake_run(command, **kwargs):
        assert command[-1] == "--version"
        return SimpleNamespace(returncode=0, stdout="cline 1.2.3\n", stderr="")

    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({"jsonrpc": "2.0", "id": 7040, "method": "tools/call", "params": {"name": "nexus_provider_preflight", "arguments": {"provider": "cline", "model": "glm-5.2"}}})
    payload = response["result"]["structuredContent"]
    assert payload["blocker"] == "MODEL_PROBE_REQUIRED"
    assert payload["execution_ready"] is False
    assert payload["readiness_status"] != "MODEL_VERIFIED"
    assert service.submitted == []


def test_codex_probe_command_is_isolated_and_not_full_auto():
    gateway = UnifiedMCPGateway(service=FakeService())
    command = gateway._assist_command(executable="/usr/local/bin/codex", provider="codex", model="gpt-5", prompt="probe")
    assert command[:4] == ["/usr/local/bin/codex", "exec", "--json", "--ephemeral"]
    assert "--skip-git-repo-check" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--full-auto" not in command


def test_codex_jsonl_agent_message_decoder_extracts_payload():
    raw = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t-1"}),
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({"probe": "ok"})}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}),
        ]
    )
    assert UnifiedMCPGateway._decode_model_probe_payload(raw, "codex", "gpt-5") == (
        {"probe": "ok"},
        "codex_jsonl_sequence",
    )


def test_model_probe_transport_provenance_rejects_mismatch_and_partial_events():
    forged_cline = _cline_probe_events({"probe": "ok"}, provider="evil")
    assert UnifiedMCPGateway._decode_model_probe_payload(
        forged_cline,
        "cline",
        "cline-pass/glm-5.2",
    ) == (None, None)
    partial_codex = json.dumps({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": json.dumps({"probe": "ok"})},
    })
    assert UnifiedMCPGateway._decode_model_probe_payload(
        partial_codex,
        "codex",
        "gpt-5",
    ) == (None, None)


def test_gateway_provider_executable_uses_shared_registered_resolver(monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "resolve_registered_provider_executable", lambda provider: "/bin/echo")
    gateway = UnifiedMCPGateway(service=FakeService())

    metadata, executable = gateway._provider_executable("agy")

    assert metadata["binary_env"] == "NEXUS_AGY_BIN"
    assert executable == "/bin/echo"


def test_task_card_create_is_owner_confirmed_non_overwriting_and_hashed(monkeypatch, tmp_path):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(gateway_module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="f" * 40, stderr=""))
    gateway = UnifiedMCPGateway(service=FakeService())
    arguments = {
        "owner_confirmation": True,
        "campaign_id": "chatgpt-bootstrap",
        "task_id": "first-card",
        "objective": "Create a bounded card from the public MCP surface.",
        "allowed_files": ["nexus/example.py"],
        "verifier_commands": ["git diff --check"],
    }
    response = gateway.handle({"jsonrpc": "2.0", "id": 704, "method": "tools/call", "params": {"name": "nexus_task_card_create", "arguments": arguments}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "CREATED_PENDING_COMMIT"
    assert len(payload["card_hash"]) == 64
    assert payload["git_blob_sha"] == "f" * 40
    assert (tmp_path / "tasks/chatgpt-bootstrap/INDEX.md").exists()
    assert (tmp_path / "tasks/chatgpt-bootstrap/00-first-card.md").exists()
    second = gateway.handle({"jsonrpc": "2.0", "id": 705, "method": "tools/call", "params": {"name": "nexus_task_card_create", "arguments": arguments}})
    assert second["result"]["isError"] is True
    assert "TASK_CARD_CREATE_WOULD_OVERWRITE" in second["result"]["structuredContent"]["error"]


def test_task_card_create_hash_failure_leaves_no_campaign(monkeypatch, tmp_path):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(gateway_module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="hash failed"))
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 7051, "method": "tools/call", "params": {"name": "nexus_task_card_create", "arguments": {"owner_confirmation": True, "campaign_id": "atomic-failure", "task_id": "card", "objective": "bounded", "allowed_files": ["README.md"], "verifier_commands": ["git diff --check"]}}})
    assert response["result"]["isError"] is True
    assert not (tmp_path / "tasks/atomic-failure").exists()
    assert not list((tmp_path / "tasks").glob(".atomic-failure.create-*"))


def test_model_probe_isolated_receipt_validates_schema_and_cleans_workspace(monkeypatch, tmp_path):
    class FakePopen:
        pid = 54003

        def __init__(self, command, *, stdout, stderr, **kwargs):
            self._returncode = 0
            stdout.write(_cline_probe_events({"probe": "ok"}))
            stdout.flush()

        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    gateway = UnifiedMCPGateway(service=service)
    submitted = gateway.handle({"jsonrpc": "2.0", "id": 706, "method": "tools/call", "params": {"name": "nexus_model_probe", "arguments": {"task_id": "probe-cline-1", "provider": "cline", "model": "glm-5.2", "prompt": "Return probe JSON", "output_schema": {"type": "object", "required": ["probe"]}, "context_arm": "bare"}}})
    first = submitted["result"]["structuredContent"]
    assert first["status"] == "RUNNING"
    assert first["job_kind"] == "model_probe"
    assert first["workspace_mode"] == "isolated"
    assert first["context_arm"] == "bare"
    assert first["context_arm_applied"] is False
    assert first["context_arm_semantics"] == "record_only_not_applied"
    waited = gateway.handle({"jsonrpc": "2.0", "id": 707, "method": "nexus/noop", "params": {}})
    assert waited["error"]["code"] == -32601
    result = gateway.handle({"jsonrpc": "2.0", "id": 708, "method": "tools/call", "params": {"name": "nexus_model_probe_result", "arguments": {"task_id": "probe-cline-1"}}})
    payload = result["result"]["structuredContent"]
    assert payload["status"] == "COMPLETED"
    assert payload["result"]["probe"] == "ok"
    assert payload["process_cleanup"] is True
    assert payload["filesystem_delta"] == {"created": [], "removed": [], "changed": []}
    assert payload["schema_validation_level"] == "bounded_subset"
    assert payload["tool_policy_enforcement"] == "cline_plan_auto_approve_false_allowlist_not_enforced"


def test_model_probe_feedback_loop_preflight_then_worker_candidate_once(monkeypatch, tmp_path):
    """Exercise the exact four-step readiness feedback loop without a real provider."""
    class FakePopen:
        launches = 0
        pid = 54123

        def __init__(self, command, *, stdout, stderr, **kwargs):
            type(self).launches += 1
            self._returncode = 0
            stdout.write(_cline_probe_events({"probe": "ok"}))
            stdout.flush()

        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    gateway = UnifiedMCPGateway(service=service)
    initial = gateway._provider_preflight({"provider": "cline", "model": "glm-5.2"})
    assert initial["blocker"] == "MODEL_PROBE_REQUIRED"
    assert initial["execution_ready"] is False

    probe_args = {"task_id": "feedback-loop", "provider": "cline", "model": "glm-5.2", "prompt": "Return probe JSON", "output_schema": {"type": "object", "required": ["probe"]}}
    submitted = gateway._model_probe_submit(probe_args)
    assert submitted["status"] == "RUNNING"
    result = gateway._assist_refresh("feedback-loop")
    assert result["status"] == "COMPLETED"
    assert result["probe_evidence_hash"]
    assert list((tmp_path / "assisted_provider_jobs" / "probe_evidence").glob("*.json"))

    verified = gateway._provider_preflight({"provider": "cline", "model": "glm-5.2"})
    assert verified["readiness_status"] == "MODEL_VERIFIED"
    assert verified["execution_ready"] is True
    assert verified["model_reachable"] is True
    assert verified["requested_model_verified"] is True
    evidence_path = next((tmp_path / "assisted_provider_jobs" / "probe_evidence").glob("*.json"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["authentication_evidence"] == "successful_exact_model_probe"
    for raw_field in ("prompt", "command", "result", "output_schema"):
        assert raw_field not in evidence

    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight(
        requested_model="gemini-3.6-flash-high", resolved_model="gemini-3.6-flash-high",
    ))
    args = _worker_args("feedback-worker")
    response = gateway._worker_candidate(args)
    assert response["status"] == "PENDING_HUMAN_APPROVAL"
    assert len(service.submitted) == 1

    replay = gateway._model_probe_submit(probe_args)
    assert replay["status"] == "COMPLETED"
    assert FakePopen.launches == 1
    conflict = dict(probe_args, prompt="changed semantics")
    with __import__("pytest").raises(Exception, match="MODEL_PROBE_TASK_ID_CONFLICT"):
        gateway._model_probe_submit(conflict)


def test_probe_receipt_tamper_and_expiry_matrix_fails_closed(monkeypatch, tmp_path):
    class FakePopen:
        launches = 0
        pid = 54124
        def __init__(self, command, *, stdout, stderr, **kwargs):
            type(self).launches += 1
            self._returncode = 0
            stdout.write(_cline_probe_events({"probe": "ok"}))
            stdout.flush()
        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    gateway = UnifiedMCPGateway(service=service)
    args = {"task_id": "tamper-probe", "provider": "cline", "model": "glm-5.2", "prompt": "probe", "output_schema": {"type": "object", "required": ["probe"]}}
    gateway._model_probe_submit(args)
    gateway._assist_refresh("tamper-probe")
    evidence_path = next((tmp_path / "assisted_provider_jobs" / "probe_evidence").glob("*.json"))
    original = json.loads(evidence_path.read_text(encoding="utf-8"))
    for field, value in (
        ("provider", "other"),
        ("requested_model", "other/model"),
        ("resolved_model", "other/model"),
        ("binary_path", "/bin/false"),
        ("binary_sha256", "0" * 64),
        ("cli_version", "changed"),
        ("command_hash", "0" * 64),
        ("action_id", "action-tampered"),
        ("attempt_id", "attempt-tampered"),
        ("result_hash", "0" * 64),
        ("output_schema_hash", "0" * 64),
        ("filesystem_delta", {"created": ["x"], "removed": [], "changed": []}),
        ("process_cleanup", False),
        ("expires_at", "2000-01-01T00:00:00+00:00"),
        ("finished_at", "2099-01-01T00:00:00+00:00"),
        ("evidence_hash", "0" * 64),
    ):
        tampered = dict(original)
        tampered[field] = value
        evidence_path.write_text(json.dumps(tampered), encoding="utf-8")
        preflight = gateway._provider_preflight({"provider": "cline", "model": "glm-5.2"})
        assert preflight["execution_ready"] is False, field
        assert preflight.get("readiness_status") != "MODEL_VERIFIED", field
        assert service.submitted == [], field
        assert FakePopen.launches == 1, field
        evidence_path.write_text(json.dumps(original), encoding="utf-8")

    job_path = tmp_path / "assisted_provider_jobs" / "tamper-probe.json"
    original_job = json.loads(job_path.read_text(encoding="utf-8"))
    changed_command = list(original_job["command"])
    changed_command[-1] = "tampered prompt"
    for field, value in (
        ("command", changed_command),
        ("action_id", "action-tampered"),
        ("attempt_id", "attempt-tampered"),
        ("result", {"probe": "tampered"}),
        ("output_schema", {"type": "object", "required": ["other"]}),
        ("filesystem_delta", {"created": ["x"], "removed": [], "changed": []}),
        ("process_cleanup", False),
        ("model_response_provenance", None),
    ):
        tampered_job = dict(original_job)
        tampered_job[field] = value
        job_path.write_text(json.dumps(tampered_job), encoding="utf-8")
        preflight = gateway._provider_preflight({"provider": "cline", "model": "glm-5.2"})
        assert preflight["execution_ready"] is False, field
        assert service.submitted == [], field
        assert FakePopen.launches == 1, field
        job_path.write_text(json.dumps(original_job), encoding="utf-8")


def test_model_probe_transport_metadata_never_establishes_model_or_auth(monkeypatch, tmp_path):
    class MetadataPopen:
        pid = 54125
        def __init__(self, command, *, stdout, stderr, **kwargs):
            self._returncode = 0
            stdout.write(json.dumps({"type": "run_start", "providerId": "cline"}) + "\n")
            stdout.flush()
        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", MetadataPopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    gateway = UnifiedMCPGateway(service=service)
    args = {
        "task_id": "metadata-only-probe",
        "provider": "cline",
        "model": "glm-5.2",
        "prompt": "probe",
        "output_schema": {"type": "object", "required": ["probe"]},
    }
    gateway._model_probe_submit(args)
    result = gateway._assist_refresh("metadata-only-probe")
    assert result["status"] == "FAILED"
    assert result["model_response_verified"] is False
    assert result.get("probe_evidence_hash") is None
    assert not list((tmp_path / "assisted_provider_jobs" / "probe_evidence").glob("*.json"))


def test_noncompleted_probe_states_never_write_readiness_evidence(tmp_path):
    service = FakeService()
    service.state_dir = tmp_path
    gateway = UnifiedMCPGateway(service=service)
    for status in ("RUNNING", "CANCELLED", "FAILED", "UNKNOWN_REQUIRES_RECONCILE"):
        assert gateway._write_probe_evidence({"job_kind": "model_probe", "status": status}) is None
    assert not (tmp_path / "assisted_provider_jobs" / "probe_evidence").exists()


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED"])
def test_settled_assisted_failure_is_not_currently_actionable(status):
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway._assist_response({
        "task_id": "settled-assist",
        "status": status,
        "process_cleanup": True,
        "durable_exit_marker": True,
        "uncertain_mutation": False,
        "provider_error": "retained evidence",
        "stdout_sha256": "a" * 64,
    })

    assert response["attention_required"] is False
    assert response["next_action"] == "nexus_task_retry"
    assert response["recommended_tool"] == "nexus_task_retry"
    assert response["provider_error"] == "retained evidence"
    assert response["stdout_sha256"] == "a" * 64
    assert response["durable_exit_marker"] is True


@pytest.mark.parametrize(("status", "unresolved"), [
    ("FAILED", {"durable_exit_marker": False}),
    ("CANCELLED", {"durable_exit_marker": False}),
    ("FAILED", {"durable_exit_marker": True, "uncertain_mutation": True}),
    ("CANCELLED", {"durable_exit_marker": True, "uncertain_mutation": True}),
])
def test_assisted_terminal_failure_fails_closed_on_exit_or_mutation_uncertainty(status, unresolved):
    gateway = UnifiedMCPGateway(service=FakeService())
    job = {
        "task_id": "uncertain-assist",
        "status": status,
        "process_cleanup": True,
        "provider_error": "retained evidence",
        **unresolved,
    }

    response = gateway._assist_response(job)

    assert response["attention_required"] is True
    assert response["next_action"] == "nexus_task_retry"
    assert response["provider_error"] == "retained evidence"
    assert response["durable_exit_marker"] is unresolved["durable_exit_marker"]
    assert response["uncertain_mutation"] is bool(unresolved.get("uncertain_mutation"))


@pytest.mark.parametrize("job", [
    {"status": "FAILED", "process_cleanup": False},
    {"status": "FAILED", "process_cleanup": True, "cleanup_error": "busy"},
    {"status": "CANCELLED", "process_cleanup": True, "reconciliation_required": True},
])
def test_unsettled_assisted_failure_remains_actionable(job):
    gateway = UnifiedMCPGateway(service=FakeService())

    response = gateway._assist_response({"task_id": "unsettled-assist", **job})

    assert response["attention_required"] is True
    assert response["next_action"] == "nexus_task_retry"


def test_unknown_assisted_state_requires_reconciliation():
    gateway = UnifiedMCPGateway(service=FakeService())

    response = gateway._assist_response({
        "task_id": "unknown-assist",
        "status": "UNKNOWN_REQUIRES_RECONCILE",
        "reconciliation_required": True,
    })

    assert response["attention_required"] is True
    assert response["next_action"] == "nexus_task_reconcile"


def test_assisted_public_list_and_gateway_count_share_classification(monkeypatch, tmp_path):
    service = FakeService()
    service.state_dir = tmp_path
    gateway = UnifiedMCPGateway(service=service)
    jobs = [
        {"task_id": "settled", "status": "FAILED", "process_cleanup": True, "durable_exit_marker": True},
        {"task_id": "settled-cancelled", "status": "CANCELLED", "process_cleanup": True, "durable_exit_marker": True},
        {"task_id": "failed-cleanup", "status": "FAILED", "process_cleanup": False, "durable_exit_marker": True},
        {"task_id": "unknown", "status": "UNKNOWN_REQUIRES_RECONCILE", "reconciliation_required": True, "pid": 999999},
        {"task_id": "running", "status": "RUNNING"},
    ]
    for job in jobs:
        gateway._assist_write(job)

    listed = gateway._task_list_actionable({})
    listed_ids = {item["task_id"] for item in listed["tasks"]}
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    status = gateway._gateway_status()

    assert listed_ids == {"failed-cleanup", "unknown"}
    assert listed["actionable_count"] == 2
    assert status["pending_actions"] == 3


def test_model_probe_failure_redacts_stderr_and_exposes_digest(monkeypatch, tmp_path):
    secret = "Authorization: Bearer SUPERSECRET"
    class FailedPopen:
        pid = 54126
        def __init__(self, command, *, stdout, stderr, **kwargs):
            self._returncode = 1
            stderr.write(secret)
            stderr.flush()
        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FailedPopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    gateway = UnifiedMCPGateway(service=service)
    gateway._model_probe_submit({
        "task_id": "stderr-redaction",
        "provider": "cline",
        "model": "glm-5.2",
        "prompt": "probe",
        "output_schema": {"type": "object", "required": ["probe"]},
    })
    result = gateway._assist_response(gateway._assist_refresh("stderr-redaction"))
    assert result["status"] == "FAILED"
    assert result["provider_error"] == "provider process failed"
    assert result["provider_error_sha256"] == __import__("hashlib").sha256(secret.encode()).hexdigest()
    assert "SUPERSECRET" not in json.dumps(result)


def test_model_probe_rechecks_executable_identity_immediately_before_launch(monkeypatch, tmp_path):
    service = FakeService()
    service.state_dir = tmp_path
    gateway = UnifiedMCPGateway(service=service)
    resolutions = iter([({"default_model": "glm-5.2"}, "/bin/echo"), ({"default_model": "glm-5.2"}, "/bin/false")])
    monkeypatch.setattr(gateway, "_provider_executable", lambda provider: next(resolutions))
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not launch")),
    )
    result = gateway._model_probe_submit({
        "task_id": "identity-drift",
        "provider": "cline",
        "model": "glm-5.2",
        "prompt": "probe",
        "output_schema": {"type": "object", "required": ["probe"]},
    })
    assert result["status"] == "FAILED"
    assert result["blocker"] == "ASSIST_PROVIDER_IDENTITY_DRIFT"
    assert result["provider_started"] is False


def test_model_probe_post_launch_identity_drift_reaps_process(monkeypatch, tmp_path):
    class StartedPopen:
        pid = 954127
        def __init__(self, command, **kwargs):
            self.returncode = None
        def wait(self, timeout=None):
            self.returncode = -15
            return self.returncode

    service = FakeService()
    service.state_dir = tmp_path
    gateway = UnifiedMCPGateway(service=service)
    resolutions = iter([
        ({"default_model": "glm-5.2"}, "/bin/echo"),
        ({"default_model": "glm-5.2"}, "/bin/echo"),
        ({"default_model": "glm-5.2"}, "/bin/false"),
    ])
    monkeypatch.setattr(gateway, "_provider_executable", lambda provider: next(resolutions))
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", StartedPopen)
    _patch_probe_version(monkeypatch)
    result = gateway._model_probe_submit({
        "task_id": "post-launch-identity-drift",
        "provider": "cline",
        "model": "glm-5.2",
        "prompt": "probe",
        "output_schema": {"type": "object", "required": ["probe"]},
    })
    assert result["status"] == "FAILED"
    assert result["blocker"] == "ASSIST_PROVIDER_IDENTITY_DRIFT"
    job = json.loads((tmp_path / "assisted_provider_jobs" / "post-launch-identity-drift.json").read_text())
    assert job["process_cleanup"] is True
    assert not Path(job["workspace_root"]).exists()


def test_codex_advisor_command_uses_read_only_ephemeral_flags(monkeypatch):
    captured = {}
    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"patch": "diff --git a/README.md b/README.md"}), stderr="")

    monkeypatch.setenv("NEXUS_CODEX_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)
    result = UnifiedMCPGateway._run_agy_plan(
        prompt="Return patch JSON",
        allowed_files=["README.md"],
        provider="codex",
        model="gpt-5.6-luna",
    )
    assert result["patch"].startswith("diff --git")
    assert "--ephemeral" in captured["command"]
    assert "--skip-git-repo-check" in captured["command"]
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "read-only"
    assert "--full-auto" not in captured["command"]


def test_cline_real_stdout_fixture_preserves_error_event_and_fails_closed():
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "cline" / "glm_52_real_stdout.ndjson"
    raw = fixture.read_text(encoding="utf-8")
    assert '"type":"run_start"' in raw
    assert '"type":"run_result"' in raw
    assert '"model":{"id":"cline-pass/glm-5.2"' in raw
    assert UnifiedMCPGateway._decode_assist_payload(raw, "cline", require_patch=True) is None


def test_restart_with_lost_process_and_no_exit_marker_fails_closed(tmp_path):
    service = FakeService()
    service.state_dir = tmp_path
    gateway = UnifiedMCPGateway(service=service)
    workspace = tmp_path / "missing-workspace"
    workspace.mkdir()
    (workspace / "partial.txt").write_text("partial", encoding="utf-8")
    job = {
        "task_id": "lost-provider-1",
        "job_id": "assist-lost",
        "job_kind": "model_probe",
        "status": "RUNNING",
        "provider": "cline",
        "model": "cline-pass/glm-5.2",
        "pid": 999999,
        "pgid": 999999,
        "exit_code": None,
        "workspace_mode": "isolated",
        "workspace_root": str(workspace),
        "filesystem_before": {},
        "attempt_history": [],
    }
    gateway._assist_write(job)
    result = gateway.handle({"jsonrpc": "2.0", "id": 709, "method": "tools/call", "params": {"name": "nexus_model_probe_result", "arguments": {"task_id": "lost-provider-1"}}})
    payload = result["result"]["structuredContent"]
    assert payload["status"] == "UNKNOWN_REQUIRES_RECONCILE"
    assert payload["blocker"] == "ASSIST_PROVIDER_PROCESS_LOST"
    assert payload["next_action"] == "nexus_task_reconcile"
    reconciled = gateway.handle({"jsonrpc": "2.0", "id": 712, "method": "tools/call", "params": {"name": "nexus_task_reconcile", "arguments": {"task_id": "lost-provider-1"}}})
    reconciled_payload = reconciled["result"]["structuredContent"]
    assert reconciled_payload["status"] == "FAILED"
    assert reconciled_payload["blocker"] == "ASSIST_PROVIDER_PROCESS_LOST"
    assert reconciled_payload["next_action"] == "nexus_task_retry"
    assert reconciled_payload["process_cleanup"] is True
    assert not workspace.exists()


def test_model_probe_wrong_payload_fails_schema_gate(monkeypatch, tmp_path):
    class FakePopen:
        pid = 54004

        def __init__(self, command, *, stdout, stderr, **kwargs):
            self._returncode = 0
            stdout.write(_cline_probe_events({"probe": "wrong"}))
            stdout.flush()

        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    _patch_probe_version(monkeypatch)
    gateway = UnifiedMCPGateway(service=service)
    gateway.handle({"jsonrpc": "2.0", "id": 710, "method": "tools/call", "params": {"name": "nexus_model_probe", "arguments": {"task_id": "probe-wrong-schema", "provider": "cline", "model": "glm-5.2", "prompt": "probe", "output_schema": {"type": "object", "required": ["expected"]}}}})
    result = gateway.handle({"jsonrpc": "2.0", "id": 711, "method": "tools/call", "params": {"name": "nexus_model_probe_result", "arguments": {"task_id": "probe-wrong-schema"}}})
    payload = result["result"]["structuredContent"]
    assert payload["status"] == "FAILED"
    assert payload["blocker"] == "ASSIST_PROVIDER_MALFORMED_OUTPUT"
    assert payload["schema_error"].startswith("output_schema_missing:")


def test_agy_high_model_assist_command_omits_contradictory_effort_low():
    gateway = UnifiedMCPGateway(service=FakeService())
    command = gateway._assist_command(executable="/usr/local/bin/agy", provider="agy", model="gemini-3.6-flash-high", prompt="probe")
    assert command[0] == "/usr/local/bin/agy"
    assert "--mode" in command and command[command.index("--mode") + 1] == "plan"
    assert command[command.index("--model") + 1] == "gemini-3.6-flash-high"
    assert "--effort" not in command
    assert "--print-timeout" in command


def test_agy_medium_model_not_overridden_by_hardcoded_low():
    gateway = UnifiedMCPGateway(service=FakeService())
    command = gateway._assist_command(executable="/usr/local/bin/agy", provider="agy", model="gemini-3.6-flash-medium", prompt="probe")
    assert "--effort" not in command
    assert "--print-timeout" in command


def test_agy_compiler_flash_low_consistent_effort_is_canonical():
    command = _compile_agy_command(executable="/usr/local/bin/agy", model="gemini-3.6-flash-low", prompt="p", explicit_effort="low")
    assert command[command.index("--effort") + 1] == "low"
    assert "--model" in command


def test_agy_compiler_conflicting_effort_fails_closed():
    with pytest.raises(GatewayInputError):
        _compile_agy_command(executable="/usr/local/bin/agy", model="gemini-3.6-flash-high", prompt="p", explicit_effort="low")


def test_agy_assist_command_uses_shared_compiler_contract():
    gateway = UnifiedMCPGateway(service=FakeService())
    assist = gateway._assist_command(executable="/usr/local/bin/agy", provider="agy", model="gemini-3.6-flash-high", prompt="probe")
    compiled = _compile_agy_command(executable="/usr/local/bin/agy", model="gemini-3.6-flash-high", prompt="probe")
    assert assist == compiled


def test_agy_plan_path_uses_shared_compiler_with_json_schema(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"patch": "diff --git a/a b/a"}), stderr="")

    monkeypatch.setenv("NEXUS_AGY_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", fake_run)
    result = UnifiedMCPGateway._run_agy_plan(
        prompt="Return a patch",
        allowed_files=["a"],
        provider="agy",
        model="gemini-3.6-flash-high",
    )
    assert result["patch"].startswith("diff --git")
    assert "--effort" not in captured["command"]
    assert captured["command"][captured["command"].index("--model") + 1] == "gemini-3.6-flash-high"
    assert "--json-schema" in captured["command"]


def test_agy_plan_path_effort_conflict_returns_blocker(monkeypatch):
    monkeypatch.setenv("NEXUS_AGY_BIN", "/bin/echo")
    result = UnifiedMCPGateway._run_agy_plan(
        prompt="Return a patch",
        allowed_files=["a"],
        provider="agy",
        model="gemini-3.6-flash-high",
        explicit_effort="low",
    )
    assert result["blocker"] == "AGY_ARGUMENT_COMPILATION_CONFLICT"
    assert result["error"]


def test_unrelated_providers_keep_existing_command_contracts(monkeypatch):
    gateway = UnifiedMCPGateway(service=FakeService())
    codex = gateway._assist_command(executable="/usr/local/bin/codex", provider="codex", model="gpt-5", prompt="probe")
    assert codex[:4] == ["/usr/local/bin/codex", "exec", "--json", "--ephemeral"]
    cline = gateway._assist_command(executable="/usr/local/bin/cline", provider="cline", model="glm-5.2", prompt="probe")
    assert cline[cline.index("--model") + 1] == "cline-pass/glm-5.2"
    with pytest.raises(GatewayInputError):
        gateway._assist_command(executable="/usr/local/bin/unknown", provider="unknown", model="any", prompt="probe")
