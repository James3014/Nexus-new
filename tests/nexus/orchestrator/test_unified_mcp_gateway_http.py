import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

import nexus.orchestrator.standing_grant_store as sg_store  # noqa: E402
from nexus.contracts.autonomy_goal import (  # noqa: E402
    AutonomyActionClass,
    StandingGrantContext,
)
from nexus.orchestrator.standing_grant_store import (  # noqa: E402
    StandingGrantReceipt,
    write_keyed_standing_grant_receipt,
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


@pytest.fixture(autouse=True)
def _health_hmac_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_GATEWAY_HEALTH_HMAC_KEY_FILE", str(tmp_path / "health-hmac.key"))


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
    assert resolve_bind_address({"NEXUS_MCP_GATEWAY_HOST": "0.0.0.0", ALLOW_REMOTE_ENV: "1"}) == (
        "0.0.0.0",
        8766,
    )


def test_health_exposes_one_gateway_identity():
    server, thread = _server()
    try:
        response = urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/health", timeout=3
        )
        payload = json.loads(response.read())
        assert payload["server"] == "nexus-mcp-gateway"
        assert payload["tool_count"] == len(UnifiedMCPGateway.tool_specs())
        assert payload["git_head"]
        assert payload["server_instance_id"]
        assert payload["full_tool_schema_hash"]
        assert payload["permission_policy_hash"]
        assert "pending_actions" in payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def test_unauthenticated_health_has_no_absolute_paths():
    """#2217: /health is unauthenticated, so it must not leak host paths."""
    server, thread = _server()
    try:
        response = urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/health", timeout=3
        )
        payload = json.loads(response.read())
        assert "repo_root" not in payload
        assert "executable_path" not in payload["github_observer"]
        assert [v for v in _walk_strings(payload) if v.startswith("/")] == []
        # Non-path identity fields the deployer and drift check rely on stay.
        assert len(payload["repo_root_hmac_sha256"]) == 64
        assert "executable_sha256" in payload["github_observer"]
        assert payload["git_head"] and payload["status"] in {"ok", "degraded"}
        assert set(payload["core_provenance"]) == {
            "status",
            "expected_revision",
            "observed_commit",
            "fail_closed",
            "identity_source",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_authenticated_health_keeps_full_path_detail():
    """Durable postflight sends the bearer token and compares root/observer path."""
    server, thread = _server()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/health",
            headers={"Authorization": "Bearer secret"},
        )
        payload = json.loads(urllib.request.urlopen(request, timeout=3).read())
        assert payload["repo_root"].startswith("/")
        assert "repo_root_hmac_sha256" not in payload
        assert "executable_path" in payload["github_observer"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize(
    "authorization",
    ["Bearer wrong", "bearer secret", "Bearer ", "Bearer secret ", "Bearer s\u00e9cret"],
)
def test_health_with_bad_bearer_gets_only_redacted_detail(authorization):
    """Only the exact bearer token unlocks paths; anything else gets the redacted view."""
    server, thread = _server()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/health")
        request.add_header("Authorization", authorization)
        payload = json.loads(urllib.request.urlopen(request, timeout=3).read())
        assert "repo_root" not in payload
        assert "repo_root_hmac_sha256" in payload
        assert "executable_path" not in payload["github_observer"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_mcp_requires_bearer_and_forwards_jsonrpc():
    server, thread = _server()
    try:
        try:
            _request(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("missing bearer token must fail")
        response = _request(
            server,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            token="secret",
        )
        payload = json.loads(response.read())
        assert len(payload["result"]["tools"]) == len(UnifiedMCPGateway.tool_specs())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_tools_list_exposes_exact_canonical_task_schema_and_rejects_route_override():
    server, thread = _server()
    try:
        listed = json.loads(
            _request(
                server,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
                token="secret",
            ).read()
        )
        spec = next(tool for tool in listed["result"]["tools"] if tool["name"] == "nexus_task_run")
        schema = spec["inputSchema"]
        assert set(schema["properties"]) == {
            "task_id",
            "what",
            "why",
            "allowed_files",
            "verifier_commands",
        }
        assert set(schema["required"]) == {"what", "why", "allowed_files"}
        assert schema["additionalProperties"] is False

        response = _request(
            server,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "nexus_task_run",
                    "arguments": {
                        "what": "bad",
                        "why": "route override",
                        "allowed_files": ["README.md"],
                        "execution_lane": "DIRECT_CANONICAL",
                    },
                },
            },
            token="secret",
        )
        payload = json.loads(response.read())
        assert payload["result"]["isError"] is True
        assert (
            payload["result"]["structuredContent"]["error"]
            == "CALLER_ROUTE_OVERRIDE_FORBIDDEN:execution_lane"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


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
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_runtime_identity_function_is_deterministic():
    first = runtime_identity()
    second = runtime_identity()
    assert first == second


def test_http_owner_standing_grant_issue_is_exposed_idempotent_and_fail_closed(
    tmp_path,
    monkeypatch,
):
    """The loopback HTTP transport cannot ask the Owner, so it never issues (#1750)."""
    receipt_path = tmp_path / "standing-grant" / "standing-grant.json"
    monkeypatch.setattr(sg_store, "DEFAULT_RECEIPT_PATH", receipt_path)
    server, thread = _server()
    issued_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    arguments = {
        "repository": "James3014/Nexus-new",
        "coordinatorId": "chatgpt-http",
        "goalId": "issue-982-wave3-http",
        "coordinationScopeId": "owner-thread-http",
        "allowedActions": ["TASK_SUBMIT"],
        "ttlMinutes": 30,
        "issuedAt": issued_at,
    }

    def call(request_id, call_arguments):
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": "nexus_owner_standing_grant_issue",
                "arguments": call_arguments,
            },
        }
        return json.loads(_request(server, payload, token="secret").read())["result"]

    try:
        initialized = json.loads(
            _request(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 9048,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"elicitation": {"form": {}}},
                        "clientInfo": {"name": "probe"},
                    },
                },
                token="secret",
            ).read()
        )
        assert initialized["result"]["protocolVersion"] == "2024-11-05"

        listed = json.loads(
            _request(
                server,
                {"jsonrpc": "2.0", "id": 9049, "method": "tools/list", "params": {}},
                token="secret",
            ).read()
        )
        spec = next(
            tool
            for tool in listed["result"]["tools"]
            if tool["name"] == "nexus_owner_standing_grant_issue"
        )
        assert spec["inputSchema"]["additionalProperties"] is False
        assert "ownerConfirmation" not in spec["inputSchema"]["properties"]

        refused = call(9050, arguments)
        assert refused["isError"] is True
        assert "OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE" in refused["structuredContent"]["error"]

        forged = call(9051, {**arguments, "ownerConfirmation": True})
        assert forged["isError"] is True
        assert "OWNER_CONFIRMATION_PARAMETER_REMOVED" in forged["structuredContent"]["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert not receipt_path.parent.exists() or not any(receipt_path.parent.rglob("*.json"))


def test_http_external_candidate_adoption_canary_is_pending_physical_idempotent_and_fail_closed(
    tmp_path,
    monkeypatch,
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
    monkeypatch.setattr(sg_store, "DEFAULT_RECEIPT_PATH", authority_path)
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
    write_keyed_standing_grant_receipt(receipt)

    arguments = {
        **request.model_dump(mode="json"),
        "controller_repo_root": str(controller),
        "controller_branch": "main",
        "controller_head": controller_head,
        "server_instance_id": gateway_module.SERVER_INSTANCE_ID,
        "lifecycle_revision": gateway_module.LIFECYCLE_REVISION,
        "full_tool_schema_hash": gateway_module.FULL_TOOL_SCHEMA_HASH,
        "permission_policy_hash": gateway_module.PERMISSION_POLICY_HASH,
        "authority_goal_id": "goal-http-canary",
        "authority_coordination_scope_id": "thread-http-canary",
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
            "NO_APPROVAL",
            "NO_INTEGRATION",
            "NO_MERGE",
            "NO_PUSH",
            "NO_RELEASE",
            "NO_PRODUCTION",
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


def test_unauthenticated_health_has_no_guessable_path_digest(monkeypatch, tmp_path):
    """#2226: no value on /health may equal sha256 of a known host path."""
    import hashlib

    import scripts.ops.nexus_mcp_gateway_http as http_module

    exe = tmp_path / "bin" / "gh"
    observer = {
        "schema": "nexus.github_observer_dependency.v1",
        "ready": True,
        "executable_path": str(exe),
        "executable_sha256": "e" * 64,
    }
    monkeypatch.setattr(http_module, "github_observer_runtime_identity", lambda: dict(observer))
    server, thread = _server()
    try:
        payload = json.loads(
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/health", timeout=3
            ).read()
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    guesses = {
        hashlib.sha256(str(candidate).encode("utf-8")).hexdigest()
        for candidate in (
            http_module.LOADED_SOURCE_ROOT,
            http_module.LOADED_SOURCE_ROOT.resolve(),
            exe,
            exe.resolve(),
        )
    }
    assert guesses.isdisjoint(set(_walk_strings(payload)))
    assert "repo_root_sha256" not in payload
    assert "executable_path_sha256" not in payload["github_observer"]
    assert len(payload["repo_root_hmac_sha256"]) == 64
    assert len(payload["github_observer"]["executable_path_hmac_sha256"]) == 64


def test_health_hmac_key_is_private_stable_and_not_overwritten(tmp_path):
    from scripts.ops.gateway_health_hmac import (
        HealthHmacKeyError,
        load_or_create_key,
        path_hmac,
    )

    key_file = tmp_path / "state" / "key"
    first = load_or_create_key(key_file)
    assert (key_file.stat().st_mode & 0o777) == 0o600
    assert load_or_create_key(key_file) == first
    assert path_hmac("repo_root", "/x", first) != path_hmac("executable_path", "/x", first)
    key_file.chmod(0o644)
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(key_file)
    key_file.chmod(0o600)
    key_file.write_text("short\n")
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(key_file)


def test_health_answers_with_null_digests_when_key_file_is_malformed(tmp_path, monkeypatch):
    key_file = tmp_path / "bad.key"
    key_file.write_text("a" * 65 + "\n")  # odd length: bytes.fromhex would raise ValueError
    key_file.chmod(0o600)
    monkeypatch.setenv("NEXUS_GATEWAY_HEALTH_HMAC_KEY_FILE", str(key_file))
    server, thread = _server()
    try:
        payload = json.loads(
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/health", timeout=3
            ).read()
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert payload["repo_root_hmac_sha256"] is None
    assert "repo_root_sha256" not in payload


def test_health_hmac_key_rejects_fifo_without_blocking_and_unsafe_parent(tmp_path):
    import os

    from scripts.ops.gateway_health_hmac import HealthHmacKeyError, load_or_create_key

    fifo = tmp_path / "fifo.key"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(fifo)
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o770)
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(shared / "key")


def test_health_hmac_key_failed_write_leaves_no_temp_file(tmp_path, monkeypatch):
    import os

    from scripts.ops import gateway_health_hmac as mod

    def boom(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(mod.os, "write", boom)
    key_dir = tmp_path / "state"
    with pytest.raises(mod.HealthHmacKeyError):
        mod.load_or_create_key(key_dir / "key")
    assert os.listdir(key_dir) == []


def test_health_hmac_key_length_rule_is_exactly_64_hex_chars(tmp_path):
    from scripts.ops.gateway_health_hmac import HealthHmacKeyError, load_or_create_key

    good = tmp_path / "good.key"
    good.write_text("ab" * 32 + "\n")
    good.chmod(0o600)
    assert len(load_or_create_key(good)) == 32
    # 66 hex chars: even length and valid hex, so bytes.fromhex would accept it;
    # only the exact `!= 64` rule rejects it (a `< 64` rule would not).
    long_key = tmp_path / "long.key"
    long_key.write_text("ab" * 33 + "\n")
    long_key.chmod(0o600)
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(long_key)


def test_health_hmac_key_is_fsynced_before_link(tmp_path, monkeypatch):
    from scripts.ops import gateway_health_hmac as mod

    events = []
    real_fsync, real_link = mod.os.fsync, mod.os.link
    monkeypatch.setattr(mod.os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(mod.os, "link", lambda a, b: (events.append("link"), real_link(a, b))[1])
    mod.load_or_create_key(tmp_path / "state" / "key")
    assert events.index("fsync") < events.index("link")


_HMAC_KEY_64 = "0123456789abcdef" * 4
_CANONICAL_KEY_FILE = (_HMAC_KEY_64 + "\n").encode("ascii")


def _private_dir(path):
    """Create ``path`` with mode 0700 regardless of the runner's umask."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _write_key_file(path, data, mode=0o600):
    path.write_bytes(data)
    path.chmod(mode)
    return path


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(_HMAC_KEY_64, id="lower64_no_newline"),
        pytest.param(_HMAC_KEY_64 + "\n", id="lower64_single_newline"),
    ],
)
def test_health_hmac_key_content_rule_accepts_exactly_64_lowercase_hex(tmp_path, content):
    from scripts.ops.gateway_health_hmac import load_or_create_key

    key_file = _write_key_file(_private_dir(tmp_path / "keys") / "key", content.encode("ascii"))
    assert load_or_create_key(key_file) == bytes.fromhex(_HMAC_KEY_64)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="empty"),
        pytest.param("\n", id="newline_only"),
        pytest.param(_HMAC_KEY_64[:62] + "\n", id="len62_even_valid_hex"),
        pytest.param(_HMAC_KEY_64[:63] + "\n", id="len63"),
        pytest.param(_HMAC_KEY_64 + "a\n", id="len65"),
        pytest.param(_HMAC_KEY_64 + "ab\n", id="len66_even_valid_hex"),
        pytest.param(_HMAC_KEY_64 * 2 + "\n", id="len128_even_valid_hex"),
        pytest.param(_HMAC_KEY_64.upper() + "\n", id="uppercase64"),
        pytest.param(_HMAC_KEY_64[:63] + "F\n", id="one_uppercase_char"),
        pytest.param(_HMAC_KEY_64[:63] + "g\n", id="nonhex_g"),
        pytest.param("0x" + _HMAC_KEY_64[:62] + "\n", id="0x_prefix_len64"),
        pytest.param(_HMAC_KEY_64[:32] + " " + _HMAC_KEY_64[33:] + "\n", id="inner_space_len64"),
        pytest.param(_HMAC_KEY_64[:32] + "\n" + _HMAC_KEY_64[33:] + "\n", id="inner_newline_len64"),
        pytest.param(_HMAC_KEY_64[:63] + "\u00e9\n", id="non_ascii_char"),
    ],
)
def test_health_hmac_key_content_rule_rejects_and_keeps_file(tmp_path, content):
    from scripts.ops.gateway_health_hmac import HealthHmacKeyError, load_or_create_key

    key_dir = _private_dir(tmp_path / "keys")
    key_file = _write_key_file(key_dir / "key", content.encode("utf-8"))
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(key_file)
    # Fail closed: a malformed key is never replaced by a fresh one.
    assert key_file.read_bytes() == content.encode("utf-8")
    assert sorted(p.name for p in key_dir.iterdir()) == ["key"]


_UNSAFE_KEY_CASES = [
    # Key file with any group or other permission bit.
    "key_mode_0644",
    "key_mode_0660",
    "key_mode_0777",
    "key_mode_0604",
    "key_mode_0606",
    # Key directory writable by group or by other (other-only too).
    "parent_mode_0770_existing_key",
    "parent_mode_0777_existing_key",
    "parent_mode_0777_no_key",
    "parent_mode_0702_existing_key",
    "parent_mode_0702_no_key",
    "parent_mode_0757_existing_key",
    "parent_mode_0757_no_key",
    # Not a regular file of our own at the key path.
    "symlink_to_valid_key",
    "directory_at_key_path",
    "fifo_holding_valid_key",
]


@pytest.mark.parametrize("case", [pytest.param(c, id=c) for c in _UNSAFE_KEY_CASES])
def test_health_hmac_key_unsafe_file_or_dir_fails_closed_and_is_untouched(tmp_path, request, case):
    """Unsafe key files/dirs are rejected and nothing in the key dir is changed."""
    import os

    from scripts.ops.gateway_health_hmac import HealthHmacKeyError, load_or_create_key

    key_dir = _private_dir(tmp_path / "keys")
    request.addfinalizer(lambda: key_dir.chmod(0o700))
    key_path = key_dir / "key"
    fifo_fd = None
    if case.startswith("key_mode_"):
        _write_key_file(key_path, _CANONICAL_KEY_FILE, mode=int(case[-4:], 8))
    elif case.startswith("parent_mode_"):
        if case.endswith("_existing_key"):
            _write_key_file(key_path, _CANONICAL_KEY_FILE)
        key_dir.chmod(int(case.split("_")[2], 8))
    elif case == "symlink_to_valid_key":
        _write_key_file(key_dir / "real.key", _CANONICAL_KEY_FILE)
        key_path.symlink_to(key_dir / "real.key")
    elif case == "directory_at_key_path":
        key_path.mkdir(mode=0o700)
    elif case == "fifo_holding_valid_key":
        # A FIFO whose buffer already holds a well-formed key: only the
        # regular-file check rejects it.
        os.mkfifo(key_path, 0o600)
        fifo_fd = os.open(key_path, os.O_RDWR | os.O_NONBLOCK)
        request.addfinalizer(lambda: os.close(fifo_fd))
        os.write(fifo_fd, _CANONICAL_KEY_FILE)
    else:
        raise AssertionError(f"unknown case {case}")
    before = {
        p.name: (os.lstat(p).st_mode, p.is_file() and p.read_bytes()) for p in key_dir.iterdir()
    }
    with pytest.raises(HealthHmacKeyError):
        load_or_create_key(key_path)
    after = {
        p.name: (os.lstat(p).st_mode, p.is_file() and p.read_bytes()) for p in key_dir.iterdir()
    }
    assert after == before  # nothing created, rewritten, re-moded or left behind
    if fifo_fd is not None:
        # The FIFO was never read: its buffered key bytes are all still there.
        assert os.read(fifo_fd, 4096) == _CANONICAL_KEY_FILE


def _record_key_creation_syscalls(mod, monkeypatch, events, fail_fsync_on_tmp=False):
    """Record fsync/link on the module's ``os``, naming each fd by its opened path.

    Other fds pass through unchanged; with ``fail_fsync_on_tmp`` only the
    fsync of the temp key file (``.<name>.*.tmp``) raises EIO.
    """
    import errno
    import os

    real_open, real_fsync, real_link = mod.os.open, mod.os.fsync, mod.os.link
    fd_paths = {}

    def recording_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        fd_paths[fd] = os.fspath(path)
        return fd

    def recording_fsync(fd):
        path = fd_paths.get(fd)
        if fail_fsync_on_tmp and path is not None and path.endswith(".tmp"):
            events.append(("fsync", path, "EIO"))
            raise OSError(errno.EIO, "injected EIO")
        result = real_fsync(fd)
        events.append(("fsync", path, "ok"))
        return result

    def recording_link(src, dst):
        events.append(("link", os.fspath(src), os.fspath(dst)))
        return real_link(src, dst)

    monkeypatch.setattr(mod.os, "open", recording_open)
    monkeypatch.setattr(mod.os, "fsync", recording_fsync)
    monkeypatch.setattr(mod.os, "link", recording_link)


def test_health_hmac_key_temp_file_fsynced_before_link_and_dir_fsynced_after(tmp_path, monkeypatch):
    import re
    import stat

    from scripts.ops import gateway_health_hmac as mod

    events = []
    _record_key_creation_syscalls(mod, monkeypatch, events)
    key_dir = _private_dir(tmp_path / "state")
    target = key_dir / "key"
    key = mod.load_or_create_key(target)

    links = [e for e in events if e[0] == "link"]
    assert len(links) == 1
    _, tmp_src, link_dst = links[0]
    assert link_dst == str(target)
    assert Path(tmp_src).parent == key_dir  # temp file lives in the same directory
    link_at = events.index(links[0])
    # The data fsync is on the temp file's own fd and succeeded before it became visible.
    assert ("fsync", tmp_src, "ok") in events[:link_at]
    # The directory fsync is issued (and succeeded) after the link, so the name survives a crash.
    assert ("fsync", str(key_dir), "ok") in events[link_at + 1 :]
    assert len(key) == 32
    on_disk = target.read_bytes()
    assert re.fullmatch(rb"[0-9a-f]{64}\n", on_disk)
    assert on_disk == key.hex().encode("ascii") + b"\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert sorted(p.name for p in key_dir.iterdir()) == ["key"]


def test_health_hmac_key_fsync_failure_fails_closed_without_linking(tmp_path, monkeypatch):
    from scripts.ops import gateway_health_hmac as mod

    events = []
    _record_key_creation_syscalls(mod, monkeypatch, events, fail_fsync_on_tmp=True)
    key_dir = _private_dir(tmp_path / "state")
    with pytest.raises(mod.HealthHmacKeyError):
        mod.load_or_create_key(key_dir / "key")
    assert [e for e in events if e[0] == "link"] == []  # never linked an un-synced key
    assert [e[2] for e in events if e[0] == "fsync"] == ["EIO"]
    # Real os.link stays in place, so a buggy link would leave a file here.
    assert list(key_dir.iterdir()) == []


def test_health_hmac_key_concurrent_creator_wins_and_temp_is_cleaned(tmp_path, monkeypatch):
    from scripts.ops import gateway_health_hmac as mod

    winner = ("fedcba9876543210" * 4 + "\n").encode("ascii")
    real_link = mod.os.link
    links = []

    def racing_link(src, dst):
        links.append(dst)
        _write_key_file(Path(dst), winner)  # another process publishes its key first
        return real_link(src, dst)  # -> FileExistsError

    monkeypatch.setattr(mod.os, "link", racing_link)
    key_dir = _private_dir(tmp_path / "state")
    key = mod.load_or_create_key(key_dir / "key")
    assert len(links) == 1
    assert key == bytes.fromhex(winner.decode("ascii").strip())  # the winner's key, not ours
    assert (key_dir / "key").read_bytes() == winner
    assert sorted(p.name for p in key_dir.iterdir()) == ["key"]  # our temp file removed


def _health_payload():
    server, thread = _server()
    try:
        response = urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/health", timeout=3
        )
        assert response.status == 200
        return json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _fresh_route_preflight_cache():
    import scripts.ops.nexus_mcp_gateway_http as http_module

    http_module._WORKER_ROUTE_PREFLIGHT_CACHE.update(at=None, value=None)
    return http_module


def _fake_agy(tmp_path, monkeypatch):
    import os

    exe = tmp_path / "bin" / "agy"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_EXECUTABLE", str(exe))
    return exe


def test_health_worker_route_preflight_blocked_without_agy_authorization(tmp_path, monkeypatch):
    _fake_agy(tmp_path, monkeypatch)
    monkeypatch.delenv("NEXUS_AGY_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    _fresh_route_preflight_cache()
    block = _health_payload()["worker_route_preflight"]
    assert block["status"] == "BLOCKED"
    route = {r["route"]: r for r in block["routes"]}["fast_bounded_implementation"]
    assert route["adapter"] == "agy_flash_38"
    assert route["preflight"] == "BLOCKED"
    assert route["reason"] == "NEXUS_AGY_RUNTIME_AUTHORIZED=1 is required"
    assert set(route) == {"route", "adapter", "preflight", "reason"}


def test_health_worker_route_preflight_ok_with_agy_authorization(tmp_path, monkeypatch):
    _fake_agy(tmp_path, monkeypatch)
    monkeypatch.setenv("NEXUS_AGY_RUNTIME_AUTHORIZED", "1")
    _fresh_route_preflight_cache()
    block = _health_payload()["worker_route_preflight"]
    assert block["status"] == "OK"
    route = {r["route"]: r for r in block["routes"]}["fast_bounded_implementation"]
    assert route == {
        "route": "fast_bounded_implementation",
        "adapter": "agy_flash_38",
        "preflight": "OK",
        "reason": "",
    }


def test_health_worker_route_preflight_exception_is_unknown_and_health_stays_200(monkeypatch):
    import nexus.executors.worker_registry as registry_module

    def boom(cls):
        raise RuntimeError("secret-value-should-not-leak")

    monkeypatch.setattr(registry_module.WorkerRegistry, "default", classmethod(boom))
    _fresh_route_preflight_cache()
    block = _health_payload()["worker_route_preflight"]
    assert block["status"] == "UNKNOWN"
    assert block["routes"] == []
    assert "secret-value-should-not-leak" not in json.dumps(block)
    _fresh_route_preflight_cache()


def test_health_worker_route_preflight_is_cached(monkeypatch):
    http_module = _fresh_route_preflight_cache()
    calls = []

    def fake():
        calls.append(1)
        return {"status": "OK", "routes": []}

    monkeypatch.setattr(http_module, "_compute_worker_route_preflight", fake)
    http_module.worker_route_preflight()
    http_module.worker_route_preflight()
    assert len(calls) == 1
    http_module._WORKER_ROUTE_PREFLIGHT_CACHE["at"] -= 61
    http_module.worker_route_preflight()
    assert len(calls) == 2
    _fresh_route_preflight_cache()


def test_health_worker_route_preflight_missing_executable_hides_path(tmp_path, monkeypatch):
    missing = tmp_path / "nowhere" / "agy-missing"
    monkeypatch.setenv("NEXUS_AGY_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_AGY_EXECUTABLE", str(missing))
    _fresh_route_preflight_cache()
    raw = json.dumps(_health_payload()["worker_route_preflight"])
    block = json.loads(raw)
    route = {r["route"]: r for r in block["routes"]}["fast_bounded_implementation"]
    assert route["preflight"] == "BLOCKED"
    assert route["reason"] == "executable not found"
    assert str(missing) not in raw
    assert str(tmp_path) not in raw
    _fresh_route_preflight_cache()


def test_public_preflight_reason_only_passes_variable_name_form():
    import scripts.ops.nexus_mcp_gateway_http as http_module

    f = http_module._public_preflight_reason
    assert f("NEXUS_AGY_RUNTIME_AUTHORIZED=1 is required") == (
        "NEXUS_AGY_RUNTIME_AUTHORIZED=1 is required"
    )
    assert f("NEXUS_AGY_EXECUTABLE=/Users/x/bin/agy is required") == "preflight not ready"
    assert f("ready") == ""


def test_health_worker_route_preflight_empty_defaults_is_unknown(monkeypatch):
    import nexus.services.model_workforce_policy as policy_module

    real = policy_module.WorkforcePolicyLoader

    class _Loader:
        def load(self):
            snap = real().load()
            routing = {**snap.routing, "online": {**snap.routing["online"], "route_defaults": {}}}
            return type("Snap", (), {"routing": routing, "workers": snap.workers})()

    monkeypatch.setattr(policy_module, "WorkforcePolicyLoader", _Loader)
    http_module = _fresh_route_preflight_cache()
    block = http_module._compute_worker_route_preflight()
    assert block == {"status": "UNKNOWN", "routes": [], "reason": "no default routes"}


def test_health_worker_route_preflight_one_adapter_raises_other_still_reported(monkeypatch):
    import nexus.executors.worker_registry as registry_module

    class _Result:
        ready = True
        reason = "ready"

    class _Registry:
        def preflight(self, provider):
            raise RuntimeError("/secret/path")

    monkeypatch.setattr(
        registry_module.WorkerRegistry, "default", classmethod(lambda cls: _Registry())
    )
    http_module = _fresh_route_preflight_cache()
    block = http_module._compute_worker_route_preflight()
    assert block["status"] == "BLOCKED"
    assert len(block["routes"]) >= 2
    assert all(r["reason"] == "preflight error: RuntimeError" for r in block["routes"])
    assert "/secret/path" not in json.dumps(block)
