import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.orchestrator.unified_mcp_gateway import (  # noqa: E402
    GATEWAY_NAME,
    TOOL_MANIFEST_REVISION,
    UnifiedMCPGateway,
)


class FakeService:
    def __init__(self):
        self.submitted = []
        self.completed = []

    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self):
        return {"actionable_count": 0, "tasks": []}

    def get_task(self, task_id):
        return {"task_id": task_id, "status": "TERMINAL"}

    def wait_task(self, task_id, **kwargs):
        return {"task_id": task_id, "status": "PENDING_HUMAN_APPROVAL", "task_action": {"action_state": "ACTION_REQUIRED", "next_action": "owner_finish"}, "wait": kwargs}

    def complete_direct_canonical(self, request, *, expected_commit_sha=None):
        self.completed.append(dict(request))
        return {"status": "DIRECT_CANONICAL_COMPLETED", "task_id": request["task_id"], "expected_commit_sha": expected_commit_sha}

    def owner_finish(self, task_id, **kwargs):
        return {"status": "INTEGRATED", "task_id": task_id, "binding": kwargs}

    def cancel_task(self, task_id):
        return {"status": "CANCELLED", "task_id": task_id}

    def submit_task(self, request):
        self.submitted.append(request)
        return {"status": "DIRECT_CANONICAL_READY", "task_id": request["task_id"], "target_created": False, "state_created": False}


def test_gateway_has_one_identity_and_bounded_public_surface():
    gateway = UnifiedMCPGateway(service=FakeService())
    initialized = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    listed = gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert initialized["result"]["serverInfo"]["name"] == GATEWAY_NAME
    assert initialized["result"]["serverInfo"]["toolManifestRevision"] == TOOL_MANIFEST_REVISION
    assert len(listed["result"]["tools"]) == 10
    assert {tool["name"] for tool in listed["result"]["tools"]} == {tool["name"] for tool in UnifiedMCPGateway.tool_specs()}


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
    response = gateway.handle({"jsonrpc": "2.0", "id": 14, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Suggest a bounded patch", "why": "Assist only", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL"}}})
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
        response = assisted_gateway.handle({"jsonrpc": "2.0", "id": 200 + index, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"task_id": f"soak-assisted-{index}", "what": "Propose one bounded README typo fix", "why": "Synthetic Assisted soak", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL"}}})
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
    assert captured["command"][-1] == "Return a patch"
    assert "--prompt" not in captured["command"]
