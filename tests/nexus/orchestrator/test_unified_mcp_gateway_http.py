import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.contracts.autonomy_goal import (  # noqa: E402
    AutonomyActionClass,
    StandingGrantContext,
)
from nexus.orchestrator.standing_grant_store import (  # noqa: E402
    StandingGrantReceipt,
    _authorize_durable_standing_grant_effect_at,
    _write_standing_grant_receipt_at,
)
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway  # noqa: E402
from scripts.ops.nexus_mcp_gateway_http import (  # noqa: E402
    ALLOW_REMOTE_ENV,
    build_handler,
    resolve_bind_address,
    runtime_identity,
)


class FakeService:
    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self):
        return {"actionable_count": 0, "tasks": []}


def _server(service=None):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        build_handler(UnifiedMCPGateway(service=service or FakeService()), token="secret"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(server, payload, *, token=None):
    url = f"http://127.0.0.1:{server.server_port}/mcp"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(request, timeout=3)


def test_loopback_default_and_remote_opt_in():
    assert resolve_bind_address({}) == ("127.0.0.1", 8766)
    try:
        resolve_bind_address({"NEXUS_MCP_GATEWAY_HOST": "0.0.0.0"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("remote bind must fail closed")
    assert resolve_bind_address({"NEXUS_MCP_GATEWAY_HOST": "0.0.0.0", ALLOW_REMOTE_ENV: "1"}) == ("0.0.0.0", 8766)


def test_health_exposes_one_gateway_identity():
    server, thread = _server()
    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=3)
        payload = json.loads(response.read())
        assert payload["server"] == "nexus-mcp-gateway"
        assert payload["tool_count"] == len(UnifiedMCPGateway.tool_specs())
        assert payload["git_head"]
        assert payload["server_instance_id"]
        assert payload["full_tool_schema_hash"]
        assert payload["permission_policy_hash"]
        assert "pending_actions" in payload
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_mcp_requires_bearer_and_forwards_jsonrpc():
    server, thread = _server()
    try:
        try:
            _request(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("missing bearer token must fail")
        response = _request(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, token="secret")
        payload = json.loads(response.read())
        assert len(payload["result"]["tools"]) == len(UnifiedMCPGateway.tool_specs())
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_tools_list_exposes_exact_canonical_task_schema_and_rejects_route_override():
    server, thread = _server()
    try:
        listed = json.loads(_request(server, {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}, token="secret").read())
        spec = next(tool for tool in listed["result"]["tools"] if tool["name"] == "nexus_task_run")
        schema = spec["inputSchema"]
        assert set(schema["properties"]) == {"task_id", "what", "why", "allowed_files", "verifier_commands"}
        assert set(schema["required"]) == {"what", "why", "allowed_files"}
        assert schema["additionalProperties"] is False

        response = _request(
            server,
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "bad", "why": "route override", "allowed_files": ["README.md"], "execution_lane": "DIRECT_CANONICAL"}}},
            token="secret",
        )
        payload = json.loads(response.read())
        assert payload["result"]["isError"] is True
        assert payload["result"]["structuredContent"]["error"] == "CALLER_ROUTE_OVERRIDE_FORBIDDEN:execution_lane"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_non_post_mcp_is_rejected():
    server, thread = _server()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/mcp", method="GET")
        try:
            urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("GET /mcp must fail")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_runtime_identity_function_is_deterministic():
    first = runtime_identity()
    second = runtime_identity()
    assert first == second


def test_http_external_candidate_adoption_canary_is_pending_physical_idempotent_and_fail_closed(
    tmp_path, monkeypatch,
):
    """Exercise the public adoption action through the real loopback HTTP seam."""
    import nexus.orchestrator.self_hosted_task_service as service_module
    import nexus.orchestrator.unified_mcp_gateway as gateway_module
    from nexus.contracts.autonomy_goal import RepositoryIdentity
    from tests.nexus.orchestrator.test_self_hosted_task_service import _external_adoption_fixture

    repository = gateway_module.GITHUB_REPOSITORY
    service, request, candidate, tree = _external_adoption_fixture(
        tmp_path,
        monkeypatch,
        repository=repository.repository_id,
        tool_manifest_hash=gateway_module.TOOL_MANIFEST_REVISION,
        full_tool_schema_hash=gateway_module.FULL_TOOL_SCHEMA_HASH,
        permission_policy_hash=gateway_module.PERMISSION_POLICY_HASH,
        lifecycle_revision=gateway_module.LIFECYCLE_REVISION,
        server_instance_id=gateway_module.SERVER_INSTANCE_ID,
    )
    # The shared semantic fixture intentionally uses LOCAL_TEST and placeholder
    # runtime identities. Rebind its signed evidence and action envelope to the
    # live gateway contract before sending the HTTP request.
    import base64
    import hashlib

    from nexus.contracts.lifecycle_action import (
        ContractKind,
        ExternalCandidateAdoptionRequest,
        LifecycleActionType,
        MutationDomain,
        PermissionProfile,
        build_action_envelope,
    )

    values = request.model_dump(mode="json", exclude={"action"})
    validation = json.loads(base64.b64decode(values["validation_receipt_b64"]))
    validation["repository"] = repository.repository_id
    validation_bytes = json.dumps(validation, sort_keys=True, separators=(",", ":")).encode()
    values["validation_receipt_b64"] = base64.b64encode(validation_bytes).decode()
    values["validation_receipt_sha256"] = hashlib.sha256(validation_bytes).hexdigest()
    acceptance = json.loads(base64.b64decode(values["acceptance_receipt_b64"]))
    acceptance["validation_receipt_sha256"] = values["validation_receipt_sha256"]
    acceptance_bytes = json.dumps(acceptance, sort_keys=True, separators=(",", ":")).encode()
    values["acceptance_receipt_b64"] = base64.b64encode(acceptance_bytes).decode()
    values["acceptance_receipt_sha256"] = hashlib.sha256(acceptance_bytes).hexdigest()
    semantic_hash = ExternalCandidateAdoptionRequest.semantic_hash_for(values)
    values["action"] = build_action_envelope(
        task_id=values["task_id"],
        action_type=LifecycleActionType.CANDIDATE_ADOPT_EXTERNAL,
        request={"adoption_request_hash": semantic_hash},
        tool_manifest_hash=values["tool_manifest_hash"],
        expected_head=values["controller_revision"],
        allowed_paths=values["allowed_files"],
        mutation=True,
        mutation_domain=MutationDomain.CANDIDATE_REF,
        permission_profile=PermissionProfile.CANDIDATE,
        task_card_path=values["task_card_path"],
        task_card_hash=values["task_card_hash"],
        contract_kind=ContractKind.TRACKED_TASK_CARD,
        attempt_id=values["attempt_id"],
        action_id=values["action_id"],
        idempotency_key=values["idempotency_key"],
    ).model_dump(mode="json")
    request = ExternalCandidateAdoptionRequest.model_validate(values)
    controller = Path(service_module.CANONICAL_SOURCE_ROOT)
    controller_head = request.controller_revision
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller)

    authority_path = tmp_path / "standing-grant" / "standing-grant.json"
    now = datetime.now(timezone.utc)
    context = StandingGrantContext.issue(
        owner_id="owner-http-canary",
        coordinator_id="coordinator-http-canary",
        repository=RepositoryIdentity.model_validate(repository.model_dump(mode="json")),
        thread_id="thread-http-canary",
        goal_id="goal-http-canary",
        allowed_actions=(AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL,),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
    )
    receipt = StandingGrantReceipt.issue(grant_id="grant-http-canary", context=context)
    _write_standing_grant_receipt_at(receipt, authority_path)

    def authorize(action, effect):
        return _authorize_durable_standing_grant_effect_at(
            authority_path,
            repository=repository,
            action=action,
            effect=effect,
            requested_at=now,
        )

    monkeypatch.setattr(
        UnifiedMCPGateway,
        "_require_owner_effect_authority",
        staticmethod(authorize),
    )

    arguments = {
        **request.model_dump(mode="json"),
        "controller_repo_root": str(controller),
        "controller_branch": "main",
        "controller_head": controller_head,
        "campaign_id": gateway_module.EPB_CAMPAIGN_ID,
        "spec_id": gateway_module.EPB_SPEC_ID,
        "spec_sha256": gateway_module.EPB_SPEC_SHA256,
        "server_instance_id": gateway_module.SERVER_INSTANCE_ID,
        "lifecycle_revision": gateway_module.LIFECYCLE_REVISION,
        "full_tool_schema_hash": gateway_module.FULL_TOOL_SCHEMA_HASH,
        "permission_policy_hash": gateway_module.PERMISSION_POLICY_HASH,
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 9001,
        "method": "tools/call",
        "params": {"name": "nexus_candidate_adopt_external", "arguments": arguments},
    }

    server, thread = _server(service)
    try:
        first = json.loads(_request(server, payload, token="secret").read())
        result = first["result"]
        assert result["isError"] is False, first
        adopted = result["structuredContent"]
        assert adopted["status"] == "PENDING_HUMAN_APPROVAL"
        assert adopted["promotion_status"] == "PENDING_HUMAN_APPROVAL"
        assert adopted["candidate_commit_sha"] == candidate
        assert adopted["candidate_tree_sha"] == tree
        assert adopted["owner_authority"]["mutation_authorized"] is True
        receipt_payload = adopted["adoption_receipt"]
        assert adopted["adoption_receipt_hash"]
        assert receipt_payload["worker_invocations"] == 0
        assert receipt_payload["candidate_rewritten"] is False
        assert receipt_payload["approval_performed"] is False
        assert receipt_payload["integration_performed"] is False
        assert receipt_payload["merge_performed"] is False
        assert receipt_payload["push_performed"] is False
        assert receipt_payload["public_claim_allowed"] is False
        assert receipt_payload["production_ready"] is False
        assert adopted["claim_ceiling"] == [
            "CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY",
            "NO_APPROVAL", "NO_INTEGRATION", "NO_MERGE", "NO_PUSH",
            "NO_RELEASE", "NO_PRODUCTION",
        ]
        state_before = service._read_state(request.task_id)
        assert state_before["status"] == "PENDING_HUMAN_APPROVAL"
        assert state_before["candidate_commit_sha"] == candidate
        assert state_before["candidate_tree_sha"] == tree
        assert state_before["verified_receipt"]["verified"] is True
        assert state_before["candidate_ref"] == adopted["candidate_ref"]
        candidate_ref_before = state_before["candidate_ref"]

        replay = json.loads(_request(server, payload, token="secret").read())["result"]
        assert replay["isError"] is False
        replay_adopted = replay["structuredContent"]
        assert replay_adopted["adoption_receipt_hash"] == adopted["adoption_receipt_hash"]
        assert replay_adopted["candidate_ref"] == candidate_ref_before
        assert service._read_state(request.task_id) == state_before

        tampered_arguments = {**arguments, "candidate_tree_sha": "f" * 40}
        tampered_payload = {
            **payload,
            "id": 9002,
            "params": {**payload["params"], "arguments": tampered_arguments},
        }
        tampered = json.loads(_request(server, tampered_payload, token="secret").read())
        assert tampered["result"]["isError"] is True
        assert service._read_state(request.task_id) == state_before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
