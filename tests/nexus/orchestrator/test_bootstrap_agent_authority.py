"""Task Card create/commit run on agent authority in BOOTSTRAP + SEPARATE Controller (#2270).

Owner decision on #2270: Owner authorization is chat, governed tasks run with no
interactive Owner step, and the mode is BOOTSTRAP. These tests pin that:

* BOOTSTRAP + SEPARATE: create and commit succeed with no standing grant and
  append a durable authority record (actor AGENT, basis
  OWNER_CHAT_DELEGATION_BOOTSTRAP, mode, Controller binding, timestamp);
* NOT_SEPARATE, DEGRADED, a non-BOOTSTRAP or invalid mode file: the standing
  grant is still required and nothing is written;
* effects that publish or are irreversible keep the grant requirement;
* end to end over the HTTP tool surface: create -> commit ->
  ``nexus_worker_candidate`` -> real service -> fake provider -> candidate.

No test patches ``_require_owner_effect_authority``: the real gate decides.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
import nexus.orchestrator.standing_grant_store as sg_store
import nexus.orchestrator.unified_mcp_gateway as gateway_module
from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.executors.worker_contract import (
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
)
from nexus.orchestrator import bootstrap_agent_authority as baa
from nexus.orchestrator import canonical_source_root as roots
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from scripts.ops.nexus_mcp_gateway_http import build_handler

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_MODE_FILE = REPO_ROOT / "docs/governance/current_operating_mode.yaml"
AUTHORITY_ARGS = {
    "authority_goal_id": "goal-2270",
    "authority_coordination_scope_id": "thread-2270",
}
TOKEN = "bootstrap-2270-token"
_ORIGINAL_GUARD = gateway_module.pre_action_guard


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr(
        sg_store, "DEFAULT_RECEIPT_PATH", tmp_path / "authority" / "standing-grant.json"
    )
    monkeypatch.setattr(sg_store, "DEFAULT_TRANSITIONS_DIR", tmp_path / "authority" / "transitions")


def _records(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "authority" / baa.RECORD_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _make_pair(tmp_path: Path, mode_text: str | None) -> tuple[Path, Path, str]:
    """A loaded deployment (carrying the mode file) and its Controller worktree."""
    loaded = tmp_path / "deployments" / "a1-x"
    loaded.mkdir(parents=True)
    _git(loaded, "init", "-q")
    _git(loaded, "config", "user.name", "Nexus Test")
    _git(loaded, "config", "user.email", "nexus-test@example.invalid")
    (loaded / "README.md").write_text("# Repo\n", encoding="utf-8")
    (loaded / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    if mode_text is not None:
        mode = loaded / baa.OPERATING_MODE_RELATIVE_PATH
        mode.parent.mkdir(parents=True)
        mode.write_text(mode_text, encoding="utf-8")
    _git(loaded, "add", "-A")
    _git(loaded, "commit", "-qm", "base")
    head = _git(loaded, "rev-parse", "HEAD")
    _git(loaded, "checkout", "-q", "--detach", head)
    controller = tmp_path / "controllers" / "a1-x"
    controller.parent.mkdir(parents=True)
    _git(loaded, "worktree", "add", "-q", "--detach", str(controller), head)
    return loaded, controller, head


def _bind(
    monkeypatch, loaded: Path, controller: Path, *, separate: bool, problem: str | None = None
):
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller if separate else loaded)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", separate)
    monkeypatch.setattr(gateway_module, "CONTROLLER_BINDING_PROBLEM", problem)
    monkeypatch.setattr(roots, "CONTROLLER_BINDING_PROBLEM", problem)
    # The Gateway's start HEAD is the loaded deployment's HEAD (#2301).
    monkeypatch.setattr(
        gateway_module, "SERVER_REPO_HEAD_AT_START", _git(loaded, "rev-parse", "HEAD")
    )


def _call(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _create_args(campaign: str = "boot", task_id: str = "card") -> dict[str, Any]:
    return {
        **AUTHORITY_ARGS,
        "owner_confirmation": True,
        "campaign_id": campaign,
        "task_id": task_id,
        "objective": "Bounded README change under BOOTSTRAP agent authority.",
        "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"],
    }


def _commit_args(created: dict[str, Any], head: str) -> dict[str, Any]:
    return {
        **AUTHORITY_ARGS,
        "owner_confirmation": True,
        "campaign_id": created["campaign_id"],
        "task_id": created["task_id"],
        "expected_head": head,
        "card_hash": created["card_hash"],
        "index_hash": created["index_hash"],
    }


def _real_mode() -> str:
    """The real mode file's schema with ``mode: BOOTSTRAP``.

    Positive tests must not turn red when the Owner leaves BOOTSTRAP; that
    change should only switch the delegation off. The live file itself is
    checked separately below.
    """
    text = REAL_MODE_FILE.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^mode: .*$", "mode: BOOTSTRAP", text, count=1)
    assert count == 1
    return text


# --- BOOTSTRAP + SEPARATE ------------------------------------------------------


def test_real_operating_mode_file_is_bootstrap_and_admits_delegation():
    """The live source of truth today is BOOTSTRAP; the reader agrees."""
    observed = baa.observe_operating_mode(REPO_ROOT)
    assert observed["mode"] == "BOOTSTRAP", observed
    assert observed["reason"] is None
    assert observed["source_sha256"] == hashlib.sha256(REAL_MODE_FILE.read_bytes()).hexdigest()


def test_bootstrap_separate_create_and_commit_need_no_grant_and_write_records(
    tmp_path, monkeypatch
):
    loaded, controller, head = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    assert not sg_store.DEFAULT_RECEIPT_PATH.exists()  # no standing grant anywhere
    gateway = UnifiedMCPGateway(service=MagicMock())

    created = _call(gateway, "nexus_task_card_create", _create_args())
    assert created["isError"] is False, created["structuredContent"]
    created_payload = created["structuredContent"]
    assert created_payload["status"] == "CREATED_PENDING_COMMIT"
    create_authority = created_payload["owner_authority"]
    assert create_authority["schema"] == baa.AUTHORIZATION_SCHEMA
    assert create_authority["actor"] == "AGENT"
    assert create_authority["authority_basis"] == "OWNER_CHAT_DELEGATION_BOOTSTRAP"
    assert create_authority["operating_mode"] == "BOOTSTRAP"
    assert create_authority["controller_binding"] == "SEPARATE"

    committed = _call(gateway, "nexus_task_card_commit", _commit_args(created_payload, head))
    assert committed["isError"] is False, committed["structuredContent"]
    commit_payload = committed["structuredContent"]
    assert commit_payload["status"] == "COMMITTED"
    assert _git(controller, "rev-parse", "HEAD") == commit_payload["commit_sha"]
    assert _git(loaded, "rev-parse", "HEAD") == head  # loaded deployment untouched

    records = _records(tmp_path)
    assert [r["effect"] for r in records] == ["TASK_CARD_CREATE", "TASK_CARD_COMMIT"]
    for record, authority in zip(records, (create_authority, commit_payload["owner_authority"])):
        assert record["schema"] == baa.RECORD_SCHEMA
        assert record["actor"] == "AGENT"
        assert record["authority_basis"] == "OWNER_CHAT_DELEGATION_BOOTSTRAP"
        assert record["decision_reference"] == "James3014/Nexus-new#2270"
        assert record["operating_mode"]["mode"] == "BOOTSTRAP"
        assert (
            record["operating_mode"]["source_sha256"]
            == hashlib.sha256(_real_mode().encode("utf-8")).hexdigest()
        )
        assert record["controller_binding"] == {"status": "SEPARATE", "reason": None}
        assert record["standing_grant_used"] is False
        assert record["recorded_at"]
        assert record["goal_id"] == "goal-2270"
        assert record["coordination_scope_id"] == "thread-2270"
        assert (
            record["standing_grant_key"]
            == UnifiedMCPGateway._owner_effect_key(AUTHORITY_ARGS).digest
        )
        assert record["server_instance_id"] == gateway_module.SERVER_INSTANCE_ID
        assert record["loaded_source_head"] == head
        assert record["operating_mode"]["loaded_source_head"] == head
        # The returned authorization names the exact durable record and effect.
        assert authority["authority_record_hash"] == record["record_hash"]
        assert authority["effect_hash"] == record["effect_hash"]
        body = {k: v for k, v in record.items() if k != "record_hash"}
        assert record["record_hash"] == sg_store.canonical_autonomy_hash(body)
    assert records[1]["effect_payload"]["card_hash"] == created_payload["card_hash"]
    # Delegation never mints or writes a standing grant.
    assert not sg_store.DEFAULT_RECEIPT_PATH.exists()


def test_record_write_failure_refuses_the_effect(tmp_path, monkeypatch):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    authority_dir = tmp_path / "authority"
    authority_dir.mkdir(mode=0o700)
    (authority_dir / baa.RECORD_FILENAME).symlink_to(tmp_path / "elsewhere.jsonl")
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _create_args())
    assert result["isError"] is True
    assert "BOOTSTRAP_AGENT_AUTHORITY_RECORD_WRITE_FAILED" in result["structuredContent"]["error"]
    assert not (controller / "tasks").exists()
    assert not (tmp_path / "elsewhere.jsonl").exists()


# --- grant still required ------------------------------------------------------


def _assert_grant_required(result: dict[str, Any], tmp_path: Path, controller: Path) -> None:
    assert result["isError"] is True
    assert "OWNER_AUTHORITY_REQUIRED" in result["structuredContent"]["error"]
    assert _records(tmp_path) == []
    assert not (controller / "tasks").exists()


def test_not_separate_controller_still_requires_the_grant(tmp_path, monkeypatch):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=False)
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _create_args())
    _assert_grant_required(result, tmp_path, loaded)


def test_not_separate_commit_still_requires_the_grant(tmp_path, monkeypatch):
    loaded, controller, head = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=False)
    with pytest.raises(gateway_module.GatewayInputError, match="OWNER_AUTHORITY_REQUIRED"):
        UnifiedMCPGateway._require_owner_effect_authority(
            AutonomyActionClass.TASK_CARD_COMMIT,
            {"campaign_id": "boot", "task_id": "card", "expected_head": head},
            key=UnifiedMCPGateway._owner_effect_key(AUTHORITY_ARGS),
        )
    assert _records(tmp_path) == []


@pytest.mark.parametrize(
    "mode_text",
    [
        pytest.param("MISSING", id="mode-file-missing"),
        pytest.param("RELABEL", id="mode-not-bootstrap"),
        pytest.param("schema: nexus.operating_mode.v1\nmode: BOOTSTRAP\n", id="mode-file-invalid"),
        pytest.param(":\n- [", id="mode-file-unparseable"),
    ],
)
def test_non_bootstrap_or_invalid_mode_still_requires_the_grant(tmp_path, monkeypatch, mode_text):
    if mode_text == "MISSING":
        text = None
    elif mode_text == "RELABEL":
        text = _real_mode().replace("mode: BOOTSTRAP", "mode: GOVERNED_DEFAULT", 1)
        assert text != _real_mode()
    else:
        text = mode_text
    loaded, controller, _ = _make_pair(tmp_path, text)
    _bind(monkeypatch, loaded, controller, separate=True)
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _create_args())
    _assert_grant_required(result, tmp_path, controller)


def test_mode_is_read_from_the_loaded_deployment_not_the_controller(tmp_path, monkeypatch):
    """A Controller cannot carry its own mode file: only tasks/ may change there."""
    loaded, controller, head0 = _make_pair(tmp_path, None)
    target = controller / baa.OPERATING_MODE_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(_real_mode(), encoding="utf-8")
    _git(controller, "add", "-A")
    _git(controller, "commit", "-qm", "controller-only mode file")
    assert baa.observe_operating_mode(controller)["mode"] == "BOOTSTRAP"
    assert (
        baa.delegation_context(
            AutonomyActionClass.TASK_CARD_CREATE,
            source_root=loaded,
            controller_binding={"status": "SEPARATE", "reason": None},
            expected_source_head=head0,
        )
        is None
    )


def test_uncommitted_bootstrap_edit_in_the_loaded_tree_does_not_delegate(tmp_path, monkeypatch):
    """Only the committed mode of the loaded deployment counts (Codex review)."""
    governed = _real_mode().replace("mode: BOOTSTRAP", "mode: GOVERNED_DEFAULT", 1)
    loaded, controller, _ = _make_pair(tmp_path, governed)
    (loaded / baa.OPERATING_MODE_RELATIVE_PATH).write_text(_real_mode(), encoding="utf-8")
    observed = baa.observe_operating_mode(loaded)
    assert observed["mode"] is None
    assert observed["reason"] == "MODE_FILE_DIFFERS_FROM_LOADED_COMMIT"
    _bind(monkeypatch, loaded, controller, separate=True)
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _create_args())
    _assert_grant_required(result, tmp_path, controller)


def test_symlinked_mode_file_does_not_delegate(tmp_path):
    loaded, _, _ = _make_pair(tmp_path, _real_mode())
    mode = loaded / baa.OPERATING_MODE_RELATIVE_PATH
    elsewhere = tmp_path / "mode.yaml"
    elsewhere.write_text(_real_mode(), encoding="utf-8")
    mode.unlink()
    mode.symlink_to(elsewhere)
    assert baa.observe_operating_mode(loaded)["reason"] == "MODE_FILE_NOT_REGULAR"


def test_symlinked_mode_parent_directory_does_not_delegate(tmp_path):
    loaded, _, _ = _make_pair(tmp_path, _real_mode())
    outside = tmp_path / "outside-governance"
    outside.mkdir()
    (outside / baa.OPERATING_MODE_RELATIVE_PATH.name).write_text(_real_mode(), encoding="utf-8")
    governance = loaded / baa.OPERATING_MODE_RELATIVE_PATH.parent
    shutil.rmtree(governance)
    governance.symlink_to(outside, target_is_directory=True)
    assert baa.observe_operating_mode(loaded)["reason"] == "MODE_FILE_NOT_REGULAR"


def test_mode_blob_is_not_taken_from_an_enclosing_repository(tmp_path, monkeypatch):
    """An untracked copy inside another repo's subdirectory must not match its blob."""
    outer = tmp_path / "outer"
    outer.mkdir()
    _git(outer, "init", "-q")
    _git(outer, "config", "user.name", "Nexus Test")
    _git(outer, "config", "user.email", "nexus-test@example.invalid")
    nested = outer / "nested"
    mode = nested / baa.OPERATING_MODE_RELATIVE_PATH
    mode.parent.mkdir(parents=True)
    mode.write_text(_real_mode(), encoding="utf-8")
    # The enclosing repository commits the same bytes at the same relative path.
    top = outer / baa.OPERATING_MODE_RELATIVE_PATH
    top.parent.mkdir(parents=True)
    top.write_text(_real_mode(), encoding="utf-8")
    _git(outer, "add", "-A")
    _git(outer, "commit", "-qm", "outer")
    assert baa.observe_operating_mode(outer)["mode"] == "BOOTSTRAP"  # positive control
    assert baa.observe_operating_mode(nested)["reason"] == "MODE_FILE_NOT_COMMITTED"
    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
    assert baa.observe_operating_mode(nested)["reason"] == "MODE_FILE_NOT_COMMITTED"


def test_untracked_mode_file_does_not_delegate(tmp_path):
    loaded, _, _ = _make_pair(tmp_path, None)
    mode = loaded / baa.OPERATING_MODE_RELATIVE_PATH
    mode.parent.mkdir(parents=True)
    mode.write_text(_real_mode(), encoding="utf-8")
    assert baa.observe_operating_mode(loaded)["reason"] == "MODE_FILE_NOT_COMMITTED"


def test_validator_unavailable_does_not_delegate(tmp_path, monkeypatch):
    loaded, _, _ = _make_pair(tmp_path, _real_mode())
    monkeypatch.setitem(sys.modules, "scripts.ops.check_operating_mode", None)
    observed = baa.observe_operating_mode(loaded)
    assert observed["mode"] is None
    assert str(observed["reason"]).startswith("MODE_VALIDATOR_UNAVAILABLE")


def test_validator_seeing_other_bytes_does_not_delegate(tmp_path, monkeypatch):
    import scripts.ops.check_operating_mode as checker

    loaded, _, _ = _make_pair(tmp_path, _real_mode())
    real = checker.evaluate_operating_mode

    def other_bytes(path):
        verdict = dict(real(path))
        verdict["source_sha256"] = "0" * 64
        return verdict

    monkeypatch.setattr(checker, "evaluate_operating_mode", other_bytes)
    assert baa.observe_operating_mode(loaded)["reason"] == "MODE_FILE_CHANGED_DURING_READ"


@pytest.mark.parametrize(
    "binding",
    [
        {"status": "NOT_SEPARATE", "reason": None},
        {"status": "DEGRADED", "reason": "NEXUS_CANONICAL_SOURCE_ROOT_MISSING"},
        {"status": "SEPARATE", "reason": "UNEXPECTED"},
        {},
    ],
    ids=["not-separate", "degraded", "separate-with-reason", "empty"],
)
def test_delegation_requires_exactly_a_clean_separate_binding(binding):
    assert (
        baa.delegation_context(
            AutonomyActionClass.TASK_CARD_CREATE,
            source_root=REPO_ROOT,
            controller_binding=binding,
            expected_source_head="a" * 40,
        )
        is None
    )


def test_degraded_controller_is_refused_before_any_authority(tmp_path, monkeypatch):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(
        monkeypatch,
        loaded,
        controller,
        separate=False,
        problem="NEXUS_CANONICAL_SOURCE_ROOT_MISSING",
    )
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _create_args())
    assert result["isError"] is True
    assert "CONTROLLER_BINDING_INVALID:DEGRADED" in result["structuredContent"]["error"]
    assert _records(tmp_path) == []


# --- publishing / irreversible effects unchanged --------------------------------


def test_only_task_card_create_and_commit_are_delegable():
    assert baa.DELEGABLE_ACTIONS == frozenset({
        AutonomyActionClass.TASK_CARD_CREATE,
        AutonomyActionClass.TASK_CARD_COMMIT,
    })


_NON_DELEGABLE: list[AutonomyActionClass] = sorted(
    (a for a in AutonomyActionClass if a not in baa.DELEGABLE_ACTIONS),
    key=lambda a: str(a.value),
)


@pytest.mark.parametrize(
    "action",
    _NON_DELEGABLE,
    ids=[str(a.value) for a in _NON_DELEGABLE],
)
def test_every_other_effect_still_requires_the_grant_in_bootstrap_separate(
    tmp_path, monkeypatch, action
):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    with pytest.raises(gateway_module.GatewayInputError, match="OWNER_AUTHORITY_REQUIRED"):
        UnifiedMCPGateway._require_owner_effect_authority(
            action,
            {"operation_id": "op-2270"},
            key=UnifiedMCPGateway._owner_effect_key(AUTHORITY_ARGS),
        )
    with pytest.raises(baa.BootstrapAgentAuthorityError, match="NOT_DELEGABLE"):
        baa.authorize_bootstrap_agent_effect(
            repository=gateway_module.GITHUB_REPOSITORY,
            action=action,
            effect={},
            key=None,
            context={},
            record_directory=tmp_path / "authority",
        )
    assert _records(tmp_path) == []


def test_grant_issuance_over_http_still_refuses(tmp_path, monkeypatch):
    """The fix changes what create/commit require; it does not open grant issuance."""
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    result = _call(
        UnifiedMCPGateway(service=MagicMock()),
        "nexus_owner_standing_grant_issue",
        {
            "repository": "James3014/Nexus-new",
            "coordinatorId": "agent",
            "goalId": "goal-2270",
            "coordinationScopeId": "thread-2270",
            "allowedActions": ["TASK_CARD_CREATE"],
            "ttlMinutes": 60,
            "issuedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert result["isError"] is True
    assert "OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE" in result["structuredContent"]["error"]
    assert not sg_store.DEFAULT_RECEIPT_PATH.exists()


# --- end to end over HTTP --------------------------------------------------------


class _RecordingService(SelfHostedTaskService):
    def submit_task(self, request):  # type: ignore[override]
        self.submitted = [*getattr(self, "submitted", []), json.loads(json.dumps(request))]
        return {"status": "RECORDED", "task_id": request["task_id"]}


def _ready_preflight(arguments: Any) -> dict[str, Any]:
    return {
        "status": "VERSION_VERIFIED",
        "readiness_status": "MODEL_VERIFIED",
        "execution_ready": True,
        "provider": "agy",
        "requested_model": "gemini-3.8-flash-medium",
        "resolved_model": "gemini-3.8-flash-medium",
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


def _http_call(port: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }).encode("utf-8"),
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {TOKEN}")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["result"]


def _fake_registry(provider: str) -> MagicMock:
    registry = MagicMock()
    registry.preflight.return_value = WorkerPreflight(
        provider=provider,
        executable="witness-provider",
        executable_available=True,
        authorized=True,
        implementation_status="ready",
        ready=True,
        reason="",
    )

    def invoke(provider_name, contract, lease, **kwargs):
        target = Path(lease.target_worktree)
        (target / "README.md").write_text("# Repo\n\nbounded change\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider_name,
            task_id=contract.task_id,
            target_worktree=str(target),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity="witness-provider",
            argv=("witness-provider",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=10,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    registry.invoke = invoke
    return registry


def test_http_create_commit_worker_candidate_end_to_end_with_no_owner_step(tmp_path, monkeypatch):
    work = tmp_path.resolve()
    loaded, controller, head = _make_pair(work, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", controller)
    # Same target namespace the Gateway derives from its source root.
    targets = controller.parent / "nexus-runtime-targets"
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(targets))
    monkeypatch.setattr(
        gateway_module,
        "pre_action_guard",
        lambda action, **kwargs: _ORIGINAL_GUARD(action, canonical_root=controller, **kwargs),
    )
    recorder = _RecordingService(
        state_dir=work / "gateway-state", auto_reconcile=False, ephemeral=True
    )
    gateway = UnifiedMCPGateway(service=recorder)
    monkeypatch.setattr(gateway, "_provider_preflight", _ready_preflight)
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(gateway, token=TOKEN))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        created = _http_call(port, "nexus_task_card_create", _create_args("e2e", "e2e-card"))
        assert created["isError"] is False, created["structuredContent"]
        created_payload = created["structuredContent"]
        committed = _http_call(port, "nexus_task_card_commit", _commit_args(created_payload, head))
        assert committed["isError"] is False, committed["structuredContent"]
        commit_payload = committed["structuredContent"]
        assert commit_payload["successor_execution"] == "READY_FOR_GOVERNED_START"
        card_rel = commit_payload["card_path"]
        candidate = _http_call(
            port,
            "nexus_worker_candidate",
            {
                "task_id": "e2e-card",
                "what": "bounded README change",
                "why": "exercise the BOOTSTRAP agent authority path end to end",
                "allowed_files": ["README.md"],
                "verifier_commands": ["git diff --check"],
                "owner_confirmation": True,
                "task_card_path": card_rel,
                "task_card_hash": hashlib.sha256((controller / card_rel).read_bytes()).hexdigest(),
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert candidate["isError"] is False, candidate["structuredContent"]
    assert [r["effect"] for r in _records(work)] == ["TASK_CARD_CREATE", "TASK_CARD_COMMIT"]
    assert not sg_store.DEFAULT_RECEIPT_PATH.exists()
    request = recorder.submitted[0]
    assert request["task_id"] == "e2e-card"

    # The exact submitted request runs on the real service with a fake provider.
    state_dir = work / "state"
    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    service.worker_registry = _fake_registry(request["provider"])

    def launch_inline(task_id_arg, attempt_id):
        service._run_owned_task(task_id_arg, attempt_id)
        return service._read_state(task_id_arg)

    monkeypatch.setattr(service, "_launch_worker", launch_inline)
    service.submit_task(request)
    state = service._read_state("e2e-card") or {}
    receipt = state.get("verified_receipt") or {}
    # The worker ran on the bound card and its candidate verified cleanly.
    assert receipt.get("verified") is True, receipt.get("failure_reasons")
    assert receipt.get("candidate_commit_allowed") is True
    assert receipt.get("failure_reasons") == []
    assert receipt.get("changed_file_count") == 1
    assert receipt.get("scope_gate_passed") is True
    assert receipt.get("merge_performed") is False
    # A temp state root is a rehearsal surface by design (#2181 driver too):
    # that guard, not any Owner authority, is the only thing left in the way.
    assert state.get("status") == "RETAINED_FOR_REVIEW"
    assert str(state.get("error") or "").startswith("EPHEMERAL_PROMOTION_FORBIDDEN")
    # Nothing was published: the loaded deployment and the Controller are as bound.
    assert _git(loaded, "rev-parse", "HEAD") == head
    assert _git(controller, "rev-parse", "HEAD") == commit_payload["commit_sha"]
    shutil.rmtree(targets, ignore_errors=True)


# --- #2301 hardening: start HEAD, hash chain, authority basis ------------------------

SEPARATE = {"status": "SEPARATE", "reason": None}


def _ctx(loaded: Path, head: Any):
    return baa.delegation_context(
        AutonomyActionClass.TASK_CARD_CREATE,
        source_root=loaded,
        controller_binding=SEPARATE,
        expected_source_head=head,
    )


def test_delegation_requires_loaded_head_to_equal_the_start_head(tmp_path):
    loaded, _, head = _make_pair(tmp_path, _real_mode())
    assert _ctx(loaded, head) is not None
    assert _ctx(loaded, "b" * 40) is None
    for bad in (None, "", "unknown", head.upper(), head[:12]):
        assert _ctx(loaded, bad) is None


def test_head_moved_since_start_keeps_the_grant_path_over_the_gateway(tmp_path, monkeypatch):
    loaded, controller, head = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    # Loaded tree still says BOOTSTRAP at its own HEAD, but the process started elsewhere.
    monkeypatch.setattr(gateway_module, "SERVER_REPO_HEAD_AT_START", "c" * 40)
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _create_args())
    _assert_grant_required(result, tmp_path, controller)


def test_unresolvable_source_root_falls_back_instead_of_raising(tmp_path, monkeypatch):
    loaded, _, head = _make_pair(tmp_path, _real_mode())

    def boom(self, *args, **kwargs):
        raise OSError("resolve failed")

    monkeypatch.setattr(Path, "resolve", boom)
    assert baa._committed_blob(loaded, baa.OPERATING_MODE_RELATIVE_PATH.as_posix()) is None
    assert _ctx(loaded, head) is None


def _authorize(tmp_path: Path, n: int, goal: str = "g"):
    key = UnifiedMCPGateway._owner_effect_key(AUTHORITY_ARGS)
    loaded = tmp_path / "chain" / "deployments" / "a1-x"
    if not loaded.exists():
        _make_pair(tmp_path / "chain", _real_mode())
    head = _git(loaded, "rev-parse", "HEAD")
    context = _ctx(loaded, head)
    assert context is not None
    return baa.authorize_bootstrap_agent_effect(
        repository=gateway_module.GITHUB_REPOSITORY,
        action=AutonomyActionClass.TASK_CARD_CREATE,
        effect={"campaign_id": f"c{n}", "task_id": "t", "allowed_files": ["README.md"]},
        key=key,
        context=context,
        record_directory=tmp_path / "authority",
    )


def test_records_form_a_hash_chain_from_genesis(tmp_path):
    for n in range(3):
        _authorize(tmp_path, n)
    records = _records(tmp_path)
    assert records[0]["prev_record_hash"] == baa.GENESIS_PREV_RECORD_HASH
    assert records[1]["prev_record_hash"] == records[0]["record_hash"]
    assert records[2]["prev_record_hash"] == records[1]["record_hash"]
    for record in records:
        body = {k: v for k, v in record.items() if k != "record_hash"}
        assert record["record_hash"] == sg_store.canonical_autonomy_hash(body)


def _rewrite(tmp_path: Path, records: list[dict[str, Any]]) -> None:
    path = tmp_path / "authority" / baa.RECORD_FILENAME
    path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8"
    )


def test_tampered_record_refuses_further_agent_authority(tmp_path):
    for n in range(2):
        _authorize(tmp_path, n)
    records = _records(tmp_path)
    records[0]["actor"] = "OWNER"  # edit without re-hashing
    _rewrite(tmp_path, records)
    with pytest.raises(baa.BootstrapAgentAuthorityError, match="CHAIN_BROKEN"):
        _authorize(tmp_path, 9)
    assert len(_records(tmp_path)) == 2


def test_removed_middle_record_breaks_the_chain(tmp_path):
    for n in range(3):
        _authorize(tmp_path, n)
    records = _records(tmp_path)
    _rewrite(tmp_path, [records[0], records[2]])
    with pytest.raises(baa.BootstrapAgentAuthorityError, match="LINK_MISMATCH"):
        _authorize(tmp_path, 9)


def test_garbage_line_breaks_the_chain(tmp_path):
    _authorize(tmp_path, 0)
    path = tmp_path / "authority" / baa.RECORD_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    with pytest.raises(baa.BootstrapAgentAuthorityError, match="UNPARSEABLE_RECORD"):
        _authorize(tmp_path, 1)


def _legacy(record: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in record.items() if k not in {"record_hash", "prev_record_hash"}}
    return {**body, "record_hash": sg_store.canonical_autonomy_hash(body)}


def test_legacy_unchained_records_stay_readable_and_link_into_the_chain(tmp_path):
    _authorize(tmp_path, 0)
    _authorize(tmp_path, 1)
    legacy = [_legacy(r) for r in _records(tmp_path)]
    _rewrite(tmp_path, legacy)
    _authorize(tmp_path, 2)
    records = _records(tmp_path)
    assert "prev_record_hash" not in records[0] and "prev_record_hash" not in records[1]
    assert records[2]["prev_record_hash"] == legacy[1]["record_hash"]
    _authorize(tmp_path, 3)  # the mixed file verifies end to end
    assert len(_records(tmp_path)) == 4


def test_unchained_record_after_chained_one_is_refused(tmp_path):
    _authorize(tmp_path, 0)
    _authorize(tmp_path, 1)
    records = _records(tmp_path)
    _rewrite(tmp_path, [records[0], _legacy(records[1])])
    with pytest.raises(baa.BootstrapAgentAuthorityError, match="UNCHAINED_AFTER_CHAINED"):
        _authorize(tmp_path, 2)


def test_broken_chain_refuses_create_over_the_gateway(tmp_path, monkeypatch):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    gateway = UnifiedMCPGateway(service=MagicMock())
    first = _call(gateway, "nexus_task_card_create", _create_args("one", "card"))
    assert first["isError"] is False, first["structuredContent"]
    records = _records(tmp_path)
    records[0]["actor"] = "OWNER"
    _rewrite(tmp_path, records)
    second = _call(gateway, "nexus_task_card_create", _create_args("two", "card"))
    assert second["isError"] is True
    assert "CHAIN_BROKEN" in second["structuredContent"]["error"]
    assert not (controller / "tasks" / "two").exists()


def test_result_reports_authority_basis_and_owner_confirmation_only_for_grants(
    tmp_path, monkeypatch
):
    loaded, controller, head = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    gateway = UnifiedMCPGateway(service=MagicMock())
    created = _call(gateway, "nexus_task_card_create", _create_args())["structuredContent"]
    assert created["authority_basis"] == "bootstrap_agent"
    assert created["owner_confirmation"] is False
    committed = _call(gateway, "nexus_task_card_commit", _commit_args(created, head))
    assert committed["structuredContent"]["authority_basis"] == "bootstrap_agent"
    assert committed["structuredContent"]["owner_confirmation"] is False


def test_authority_basis_helper_distinguishes_grant_from_agent():
    assert baa.authority_basis({"schema": baa.AUTHORIZATION_SCHEMA}) == "bootstrap_agent"
    assert (
        baa.authority_basis({"schema": "nexus.standing_grant_effect_authorization.v1"})
        == "owner_grant"
    )
    assert baa.authority_basis(None) == "owner_grant"
