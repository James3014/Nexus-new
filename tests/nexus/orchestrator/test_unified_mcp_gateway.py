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
    FULL_TOOL_SCHEMA_HASH,
    GATEWAY_NAME,
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
    assert payload["tool_policy_enforcement"] == "cline_plan_auto_approve_false_allowlist_not_enforced"


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
