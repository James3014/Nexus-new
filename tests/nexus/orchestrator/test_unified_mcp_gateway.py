import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.orchestrator.unified_mcp_gateway import (  # noqa: E402
    GATEWAY_NAME,
    FULL_TOOL_SCHEMA_HASH,
    LIFECYCLE_REVISION,
    PERMISSION_POLICY_HASH,
    PUBLIC_TOOL_NAMES,
    SERVER_INSTANCE_ID,
    TOOL_MANIFEST_REVISION,
    UnifiedMCPGateway,
)


class FakeService:
    def __init__(self):
        self.submitted = []
        self.completed = []
        self.approved_binding = None

    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self, *, include_details=False):
        return {"actionable_count": 0, "details_included": include_details, "tasks": []}

    def get_task(self, task_id):
        return {"task_id": task_id, "status": "TERMINAL"}

    def get_task_snapshot(self, task_id, *, include_details=False):
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
        return {"task_id": task_id, "status": "INTEGRATED", "promotion_status": "INTEGRATED", "task_action": {"task_id": task_id, "task_status": "INTEGRATED", "attention_required": False, "next_action": "none", "recommended_tool": "none"}}

    def dispose_candidate(self, task_id, **kwargs):
        return {"task_id": task_id, "status": kwargs["disposition"], "promotion_status": kwargs["disposition"], "task_action": {"task_id": task_id, "task_status": kwargs["disposition"], "attention_required": False, "next_action": "none", "recommended_tool": "none"}}

    def submit_task(self, request):
        self.submitted.append(request)
        return {"status": "DIRECT_CANONICAL_READY", "task_id": request["task_id"], "target_created": False, "state_created": False}


def test_gateway_has_one_identity_and_bounded_public_surface():
    gateway = UnifiedMCPGateway(service=FakeService())
    initialized = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    listed = gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert initialized["result"]["serverInfo"]["name"] == GATEWAY_NAME
    assert initialized["result"]["serverInfo"]["toolManifestRevision"] == TOOL_MANIFEST_REVISION
    assert len(listed["result"]["tools"]) == len(UnifiedMCPGateway.tool_specs())
    assert {tool["name"] for tool in listed["result"]["tools"]} == {tool["name"] for tool in UnifiedMCPGateway.tool_specs()}


def test_manifest_status_and_recommended_tools_share_tools_list_truth():
    gateway = UnifiedMCPGateway(service=FakeService())
    names = tuple(tool["name"] for tool in gateway.tool_specs())
    assert names == PUBLIC_TOOL_NAMES
    assert gateway.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "nexus_gateway_status", "arguments": {}}})["result"]["structuredContent"]["tool_count"] == len(names)
    assert TOOL_MANIFEST_REVISION
    assert {"nexus_provider_preflight", "nexus_task_card_create", "nexus_model_probe", "nexus_model_probe_result"}.issubset(set(names))


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
            "contract_hash": inline["contract_hash"],
            "owner_inline_contract": inline,
            "task_card_hash": None,
        })
        return state

    service.get_task_snapshot = owner_snapshot
    gateway = UnifiedMCPGateway(service=service)
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


def test_owner_inline_clean_routes_direct_without_task_card(monkeypatch):
    monkeypatch.setattr(UnifiedMCPGateway, "_dirty_paths", staticmethod(lambda: []))
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 102, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {
        "task_id": "owner-inline-clean", "what": "Fix one bounded README typo", "why": "Owner inline smoke", "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
    }}})
    payload = response["result"]["structuredContent"]
    assert payload["execution_lane"] == "DIRECT_CANONICAL"
    assert payload["contract_kind"] == "OWNER_INLINE"
    assert len(payload["contract_hash"]) == 64
    assert payload["task_card_required"] is False


def test_owner_inline_dirty_nonoverlap_uses_isolated_target_without_card(monkeypatch):
    monkeypatch.setattr(UnifiedMCPGateway, "_dirty_paths", staticmethod(lambda: ["nexus/orchestrator/unified_mcp_gateway.py"]))
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 103, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {
        "task_id": "owner-inline-disjoint", "what": "Fix one bounded README typo", "why": "Dirty disjoint smoke", "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
    }}})
    payload = response["result"]["structuredContent"]
    assert payload["execution_lane"] == "ISOLATED_TARGET"
    assert payload["contract_kind"] == "OWNER_INLINE"
    assert payload["dirty_overlap"] is False
    assert payload["target_created"] is False


def test_dirty_path_overlap_fails_closed_before_target_creation(monkeypatch):
    monkeypatch.setattr(UnifiedMCPGateway, "_dirty_paths", staticmethod(lambda: ["nexus/orchestrator/unified_mcp_gateway.py"]))
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 104, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {
        "task_id": "owner-inline-overlap", "what": "Fix one bounded gateway typo", "why": "Overlap smoke", "allowed_files": ["nexus/orchestrator/unified_mcp_gateway.py"],
        "verifier_commands": ["git diff --check"], "owner_confirmation": True,
    }}})
    payload = response["result"]["structuredContent"]
    assert payload["blocker"] == "DIRTY_PATH_OVERLAP_REQUIRES_RECONCILIATION"
    assert payload["target_created"] is False
    assert payload["overlapping_paths"] == ["nexus/orchestrator/unified_mcp_gateway.py"]


def test_delegated_worker_without_task_card_still_requires_tracked_binding(monkeypatch):
    monkeypatch.setattr(UnifiedMCPGateway, "_dirty_paths", staticmethod(lambda: []))
    gateway = UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({"jsonrpc": "2.0", "id": 105, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {
        "task_id": "delegated-no-card", "what": "Fix one bounded README typo", "why": "Delegation smoke", "allowed_files": ["README.md"],
        "preferred_worker": "agy",
    }}})
    assert response["result"]["isError"] is True
    assert "TASK_CARD_BINDING_REQUIRED" in response["result"]["structuredContent"]["error"]


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
    gateway = UnifiedMCPGateway(service=FakeService())
    snapshot = gateway.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nexus_workspace_snapshot", "arguments": {}}})
    read = gateway.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nexus_read", "arguments": {"path": "AGENTS.md", "max_lines": 2}}})
    assert snapshot["result"]["structuredContent"]["root"] == "/Users/jameschen/Workspace/nexus"
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
    assert status["result"]["structuredContent"]["status"] == "TERMINAL"
    assert finish["result"]["structuredContent"]["status"] == "DIRECT_CANONICAL_COMPLETED"
    assert cancel["result"]["structuredContent"]["status"] == "CANCELLED"


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


def test_task_run_routes_small_request_direct_without_target_fields():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Fix a bounded README typo", "why": "Small canonical edit", "allowed_files": ["README.md"]}}})
    payload = response["result"]["structuredContent"]
    assert payload["execution_lane"] == "DIRECT_CANONICAL"
    assert payload["route_authority"] == "CapabilityPlanner"
    assert payload["status"] == "DIRECT_CANONICAL_READY"
    assert service.submitted[0]["target_worktree_root"] == "/Users/jameschen/Workspace/nexus-runtime-targets"
    assert service.submitted[0]["primary_agent"] is True
    assert set((payload := response["result"]["structuredContent"])["telemetry"]) >= {
        "control_plane_ms",
        "route_decision_ms",
        "context_build_ms",
        "provider_start_ms",
        "provider_time_ms",
        "patch_validation_ms",
        "verifier_time_ms",
        "commit_time_ms",
        "worktree_time_ms",
        "cleanup_time_ms",
        "total_wall_time_ms",
    }
    assert payload["telemetry"]["provider_time_ms"] == 0
    assert payload["next_action"] == "edit_canonical_checkout"
    assert payload["completion_surface"] == "nexus_task_finish"
    assert payload["base_sha"]
    assert payload["mutation_lease"]["type"] == "canonical_mutation_lock"


def test_task_run_routes_single_nexus_file_direct_without_target():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({"jsonrpc": "2.0", "id": 19, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Fix one bounded source typo", "why": "Single-file canonical edit", "allowed_files": ["nexus/example.py"]}}})
    payload = response["result"]["structuredContent"]
    assert payload["execution_lane"] == "DIRECT_CANONICAL"
    assert payload["status"] == "DIRECT_CANONICAL_READY"
    assert payload["handoff"]["target_created"] is False


def test_assisted_defaults_to_proposal_only():
    service = FakeService()
    applied = []
    gateway = UnifiedMCPGateway(
        service=service,
        model_runner=lambda **_: {"provider": "agy", "patch": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@\n"},
        apply_runner=lambda **kwargs: applied.append(kwargs),
    )
    gateway._validate_assisted_patch = lambda patch, allowed: ["README.md"]
    response = gateway.handle({"jsonrpc": "2.0", "id": 20, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Suggest one bounded README fix", "why": "Proposal-only default", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL"}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "ASSISTED_CANONICAL_PROPOSAL_READY"
    assert payload["next_action"] == "apply_assisted_candidate"
    assert applied == []


def test_task_run_returns_typed_action_identity_and_forwards_it():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 18,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_run",
            "arguments": {
                "task_id": "action-envelope-1",
                "what": "Fix one bounded README typo",
                "why": "Exercise action identity",
                "allowed_files": ["README.md"],
                "idempotency_key": "action-envelope-key",
            },
        },
    })
    payload = response["result"]["structuredContent"]
    action = payload["action"]
    assert action["schema"] == "nexus.lifecycle_action.v1"
    assert action["task_id"] == "action-envelope-1"
    assert action["idempotency_key"] == "action-envelope-key"
    assert action["expected_head"] == payload["base_sha"]
    assert action["request_hash"]
    assert service.submitted[0]["action_id"] == action["action_id"]
    assert service.submitted[0]["action_request_hash"] == action["request_hash"]


def test_task_run_assisted_is_fail_closed_without_side_effect():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service, model_runner=lambda **_: {"provider": "agy", "blocker": "ASSIST_PROVIDER_UNAVAILABLE"})
    response = gateway.handle({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Suggest a bounded patch", "why": "Assist only", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL"}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "FINAL_BLOCK"
    assert payload["blocker"] == "ASSIST_PROVIDER_UNAVAILABLE"
    assert "provider_error" in payload
    assert set(payload["telemetry"]) >= {"control_plane_ms", "provider_start_ms", "total_wall_time_ms"}
    assert len(service.submitted) == 1
    assert service.submitted[0]["execution_lane"] == "DIRECT_CANONICAL"


def test_task_run_assisted_applies_injected_bounded_patch_without_target():
    service = FakeService()
    applied = []
    gateway = UnifiedMCPGateway(
        service=service,
        model_runner=lambda **_: {"provider": "agy", "patch": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@\n"},
        apply_runner=lambda **kwargs: applied.append(kwargs) or {"status": "DIRECT_CANONICAL_COMPLETED", "target_created": False, "state_created": False},
    )
    gateway._validate_assisted_patch = lambda patch, allowed: ["README.md"]
    response = gateway.handle({"jsonrpc": "2.0", "id": 14, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Suggest a bounded patch", "why": "Assist only", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL", "apply": True}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "ASSISTED_CANONICAL_COMPLETED"
    assert payload["route_authority"] == "CapabilityPlanner"
    assert len(applied) == 1
    assert len(service.submitted) == 1
    assert payload["telemetry"]["provider_time_ms"] >= 0
    assert payload["telemetry"]["patch_validation_ms"] >= 0
    assert payload["telemetry"]["total_wall_time_ms"] >= payload["telemetry"]["provider_time_ms"]


def test_task_run_isolated_requires_task_card_binding():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Implement a cross-module runtime change", "why": "Needs isolated worker", "allowed_files": ["nexus/a.py", "tests/a.py"], "execution_preference": "ISOLATED_TARGET", "preferred_worker": "agy"}}})
    payload = response["result"]["structuredContent"]
    assert payload["execution_lane"] == "ISOLATED_TARGET"
    assert payload["blocker"] == "TASK_CARD_BINDING_REQUIRED"
    assert service.submitted == []


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


def test_bounded_soak_matrix_keeps_direct_and_assisted_off_targets():
    direct_service = FakeService()
    direct_gateway = UnifiedMCPGateway(service=direct_service)
    for index in range(10):
        response = direct_gateway.handle({"jsonrpc": "2.0", "id": 100 + index, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"task_id": f"soak-direct-{index}", "what": "Fix one bounded README typo", "why": "Synthetic Direct soak", "allowed_files": ["README.md"]}}})
        payload = response["result"]["structuredContent"]
        assert payload["status"] == "DIRECT_CANONICAL_READY"
        assert payload["handoff"]["target_created"] is False
        assert payload["handoff"]["state_created"] is False

    assisted_service = FakeService()
    assisted_gateway = UnifiedMCPGateway(
        service=assisted_service,
        model_runner=lambda **_: {"provider": "agy", "patch": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@\n"},
        apply_runner=lambda **_: {"status": "DIRECT_CANONICAL_COMPLETED", "target_created": False, "state_created": False, "telemetry": {"commit_time_ms": 0}},
    )
    assisted_gateway._validate_assisted_patch = lambda patch, allowed: ["README.md"]
    for index in range(20):
        response = assisted_gateway.handle({"jsonrpc": "2.0", "id": 200 + index, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"task_id": f"soak-assisted-{index}", "what": "Propose one bounded README typo fix", "why": "Synthetic Assisted soak", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL", "apply": True}}})
        payload = response["result"]["structuredContent"]
        assert payload["status"] == "ASSISTED_CANONICAL_COMPLETED"
        assert payload["receipt"]["target_created"] is False
        assert payload["receipt"]["state_created"] is False
        assert payload["telemetry"]["total_wall_time_ms"] >= payload["telemetry"]["provider_time_ms"]
    assert len(assisted_service.submitted) == 20

    isolated_service = FakeService()
    isolated_gateway = UnifiedMCPGateway(service=isolated_service)
    for index in range(10):
        response = isolated_gateway.handle({"jsonrpc": "2.0", "id": 300 + index, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"task_id": f"soak-isolated-{index}", "what": "Implement a cross-module task", "why": "Synthetic isolated binding gate", "allowed_files": ["nexus/a.py", "tests/a.py"], "execution_preference": "ISOLATED_TARGET", "preferred_worker": "agy"}}})
        payload = response["result"]["structuredContent"]
        assert payload["status"] == "FINAL_BLOCK"
        assert payload["blocker"] == "TASK_CARD_BINDING_REQUIRED"
    assert isolated_service.submitted == []


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
    submitted = gateway.handle({"jsonrpc": "2.0", "id": 700, "method": "tools/call", "params": {"name": "nexus_assist_submit", "arguments": {"task_id": "async-cline-1", "what": "Suggest a README patch", "why": "Async provider smoke", "allowed_files": ["README.md"], "model": "glm-5.2"}}})
    first = submitted["result"]["structuredContent"]
    assert first["status"] == "RUNNING"
    assert first["execution_lane"] == "ASSISTED_CANONICAL"
    assert first["candidate_only"] is True
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


def test_cline_task_run_returns_async_assisted_action_with_verify_envelope(monkeypatch, tmp_path):
    import subprocess as real_subprocess
    real_popen = real_subprocess.Popen

    class FakePopen:
        pid = 54002

        def __init__(self, command, *, stdout, stderr, **kwargs):
            if isinstance(stdout, int):
                self._delegate = real_popen(command, stdout=stdout, stderr=stderr, **kwargs)
                self.pid = self._delegate.pid
                return
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
    response = gateway.handle({"jsonrpc": "2.0", "id": 702, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"task_id": "async-cline-run", "what": "Suggest a README patch", "why": "Async provider task", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL", "preferred_worker": "cline", "preferred_model": "glm-5.2", "apply": False}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "ASSISTED_PROVIDER_SUBMITTED"
    assert payload["execution_lane"] == "ASSISTED_CANONICAL"
    assert payload["provider"] == "cline"
    assert payload["next_action"] == "nexus_assist_result"
    assert payload["action"]["mutation"] is False
    assert payload["action"]["permission_profile"] == "VERIFY"
    assert service.submitted == []


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
            stdout.write(json.dumps({"probe": "ok"}) + "\n")
            stdout.flush()

        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
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
    assert payload["tool_policy_enforcement"] == "not_enforced"


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
            stdout.write(json.dumps({"probe": "wrong"}) + "\n")
            stdout.flush()

        def poll(self):
            return self._returncode

    service = FakeService()
    service.state_dir = tmp_path
    monkeypatch.setenv("NEXUS_CLINE_BIN", "/bin/echo")
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.Popen", FakePopen)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *args, **kwargs: "a" * 40)
    gateway = UnifiedMCPGateway(service=service)
    gateway.handle({"jsonrpc": "2.0", "id": 710, "method": "tools/call", "params": {"name": "nexus_model_probe", "arguments": {"task_id": "probe-wrong-schema", "provider": "cline", "model": "glm-5.2", "prompt": "probe", "output_schema": {"type": "object", "required": ["expected"]}}}})
    result = gateway.handle({"jsonrpc": "2.0", "id": 711, "method": "tools/call", "params": {"name": "nexus_model_probe_result", "arguments": {"task_id": "probe-wrong-schema"}}})
    payload = result["result"]["structuredContent"]
    assert payload["status"] == "FAILED"
    assert payload["blocker"] == "ASSIST_PROVIDER_MALFORMED_OUTPUT"
    assert payload["schema_error"].startswith("output_schema_missing:")
