import io
import json
import sys
from pathlib import Path

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

    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self):
        return {"actionable_count": 0, "tasks": []}

    def get_task(self, task_id):
        return {"task_id": task_id, "status": "TERMINAL"}

    def complete_direct_canonical(self, request, *, expected_commit_sha=None):
        return {"status": "DIRECT_CANONICAL_COMPLETED", "task_id": request["task_id"], "expected_commit_sha": expected_commit_sha}

    def owner_finish(self, task_id, **kwargs):
        return {"status": "INTEGRATED", "task_id": task_id, "binding": kwargs}

    def cancel_task(self, task_id):
        return {"status": "CANCELLED", "task_id": task_id}

    def submit_task(self, request):
        self.submitted.append(request)
        return {"status": "DIRECT_CANONICAL_READY", "task_id": request["task_id"]}


def test_gateway_has_one_identity_and_bounded_public_surface():
    gateway = UnifiedMCPGateway(service=FakeService())
    initialized = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    listed = gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert initialized["result"]["serverInfo"]["name"] == GATEWAY_NAME
    assert initialized["result"]["serverInfo"]["toolManifestRevision"] == TOOL_MANIFEST_REVISION
    assert len(listed["result"]["tools"]) == 9
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


def test_task_run_assisted_is_fail_closed_without_side_effect():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service, model_runner=lambda **_: {"provider": "agy", "blocker": "ASSIST_PROVIDER_UNAVAILABLE"})
    response = gateway.handle({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Suggest a bounded patch", "why": "Assist only", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL"}}})
    payload = response["result"]["structuredContent"]
    assert payload["status"] == "FINAL_BLOCK"
    assert payload["blocker"] == "ASSIST_PROVIDER_UNAVAILABLE"
    assert service.submitted == []


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
    assert service.submitted == []


def test_task_run_isolated_requires_task_card_binding():
    service = FakeService()
    gateway = UnifiedMCPGateway(service=service)
    response = gateway.handle({"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "Implement a cross-module runtime change", "why": "Needs isolated worker", "allowed_files": ["nexus/a.py", "tests/a.py"], "execution_preference": "ISOLATED_TARGET", "preferred_worker": "agy"}}})
    payload = response["result"]["structuredContent"]
    assert payload["execution_lane"] == "ISOLATED_TARGET"
    assert payload["blocker"] == "TASK_CARD_BINDING_REQUIRED"
    assert service.submitted == []


def test_gateway_stdio_round_trip():
    gateway = UnifiedMCPGateway(service=FakeService())
    input_stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}}) + "\n")
    output_stream = io.StringIO()
    gateway.serve(input_stream, output_stream)
    response = json.loads(output_stream.getvalue())
    assert response["result"]["tools"][0]["name"] == "nexus_gateway_status"
