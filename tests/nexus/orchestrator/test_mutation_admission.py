from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus.orchestrator.mutation_admission import (
    MutationAdmissionError,
    MutationAdmissionStore,
    pr_binding_block,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway
from scripts.ops.nexus_mutation_integration_gate import evaluate


BASE = "a" * 40


def _observer(repository: str) -> dict[str, object]:
    return {
        "ok": True,
        "repository": repository,
        "default_branch": "main",
        "head_sha": BASE,
        "observed_at": "2026-10-05T00:00:00+00:00",
    }


def _gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UnifiedMCPGateway:
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: BASE + "\n")
    service = SelfHostedTaskService(
        tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    return UnifiedMCPGateway(
        service=service,
        mutation_repository_observer=_observer,
    )


def _direct_args(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_id": "owner:issue1429:test-1",
        "repository": "James3014/Nexus-new",
        "base_sha": BASE,
        "execution_lane": "DIRECT_CANONICAL",
        "authority_kind": "OWNER_INLINE",
        "allowed_paths": ["nexus/orchestrator/**", "tests/nexus/orchestrator/**"],
        "owner_confirmation": True,
        "issue_number": 1429,
    }
    payload.update(overrides)
    return payload


def test_gateway_admission_is_durable_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, monkeypatch)

    first = gateway._call_tool("nexus_mutation_admit", _direct_args())
    duplicate = gateway._call_tool("nexus_mutation_admit", _direct_args())

    assert first["schema"] == "nexus.mutation_admission.v1"
    assert first["duplicate"] is False
    assert duplicate["duplicate"] is True
    assert duplicate["admission_id"] == first["admission_id"]
    assert duplicate["receipt_hash"] == first["receipt_hash"]
    assert first["runtime_identity"]["gateway_source_head"] == BASE
    status = gateway._call_tool(
        "nexus_mutation_admission_status",
        {
            "admission_id": first["admission_id"],
            "receipt_hash": first["receipt_hash"],
        },
    )
    assert status["status"] == "VALID"
    assert status["receipt_hash"] == first["receipt_hash"]


def test_gateway_admission_rejects_stale_default_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, monkeypatch)
    gateway._mutation_repository_observer = lambda repository: {
        **_observer(repository),
        "head_sha": "b" * 40,
    }

    with pytest.raises(GatewayInputError, match="MUTATION_ADMISSION_BASE_STALE"):
        gateway._call_tool("nexus_mutation_admit", _direct_args())


def test_operation_id_cannot_widen_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, monkeypatch)
    gateway._call_tool("nexus_mutation_admit", _direct_args())

    with pytest.raises(
        GatewayInputError,
        match="OPERATION_ID_REUSED_WITH_DIFFERENT_ADMISSION",
    ):
        gateway._call_tool(
            "nexus_mutation_admit",
            _direct_args(allowed_paths=["**"]),
        )


def test_governed_admission_requires_task_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, monkeypatch)

    with pytest.raises(GatewayInputError, match="GOVERNED_TASK_CARD_REQUIRED"):
        gateway._call_tool(
            "nexus_mutation_admit",
            _direct_args(
                operation_id="owner:issue1429:governed",
                execution_lane="GOVERNED",
                authority_kind="TRACKED_TASK_CARD",
                owner_confirmation=False,
            ),
        )


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.test")
    _git(repo, "config", "user.name", "Test User")
    (repo / "allowed.txt").write_text("base\n", encoding="utf-8")
    (repo / "outside.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "allowed.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "allowed.txt")
    _git(repo, "commit", "-m", "allowed change")
    head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head


def _admission(
    state_root: Path,
    *,
    base: str,
    operation_id: str = "owner:issue1429:gate",
    allowed_paths: list[str] | None = None,
) -> dict[str, object]:
    store = MutationAdmissionStore(
        state_root,
        now_provider=lambda: datetime(2026, 10, 5, tzinfo=timezone.utc),
    )
    return store.admit(
        operation_id=operation_id,
        repository="James3014/Nexus-new",
        base_sha=base,
        execution_lane="DIRECT_CANONICAL",
        authority_kind="OWNER_INLINE",
        allowed_paths=allowed_paths or ["allowed.txt"],
        owner_confirmation=True,
        issue_number=1429,
    )


def test_integration_gate_accepts_exact_bound_scope(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    repo, base, head = git_repo
    state_root = tmp_path / "state"
    receipt = _admission(state_root, base=base)

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "PASS"
    assert report["changed_paths"] == ["allowed.txt"]
    assert report["scope_escape_paths"] == []


def test_integration_gate_blocks_tampered_binding(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    repo, base, head = git_repo
    state_root = tmp_path / "state"
    receipt = _admission(state_root, base=base)
    body = pr_binding_block(receipt).replace(
        receipt["receipt_hash"],
        "f" * 64,
    )

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=body,
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "BLOCK"
    assert report["blockers"] == ["ADMISSION_RECEIPT_HASH_MISMATCH"]


def test_integration_gate_blocks_scope_escape(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    repo, base, _head = git_repo
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue1429:scope-escape",
    )
    (repo / "outside.txt").write_text("escaped\n", encoding="utf-8")
    _git(repo, "add", "outside.txt")
    _git(repo, "commit", "-m", "scope escape")
    head = _git(repo, "rev-parse", "HEAD")

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "BLOCK"
    assert report["scope_escape_paths"] == ["outside.txt"]
    assert "ADMISSION_SCOPE_ESCAPE" in report["blockers"]
