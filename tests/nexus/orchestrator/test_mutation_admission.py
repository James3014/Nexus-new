from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus.orchestrator.mutation_admission import (
    MutationAdmissionError,
    MutationAdmissionStore,
    canonical_hash,
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


def _authority_reference(effect: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "nexus.standing_grant_effect_authorization.v1",
        "grant_id": "owner-test-grant",
        "grant_receipt_hash": "a" * 64,
        "context_hash": "b" * 64,
        "owner_id": "James3014",
        "coordinator_id": "test-coordinator",
        "repository": {
            "repository_id": "James3014/Nexus-new",
            "canonical_remote": "https://github.com/James3014/Nexus-new.git",
        },
        "goal_id": "issue1429",
        "action": "TASK_SUBMIT",
        "requested_at": "2026-10-05T00:00:00+00:00",
        "effect": effect,
        "effect_hash": canonical_hash(effect),
        "decision_hash": "c" * 64,
        "mutation_authorized": True,
        "claim_ceiling": "TEST_ONLY",
        "standing_grant_key": "d" * 64,
    }
    payload["authorization_hash"] = canonical_hash(payload)
    return payload


def _gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UnifiedMCPGateway:
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: BASE + "\n")
    service = SelfHostedTaskService(
        tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    gateway = UnifiedMCPGateway(
        service=service,
        mutation_repository_observer=_observer,
    )
    gateway._require_owner_effect_authority = lambda action, effect, key: _authority_reference(
        dict(effect)
    )
    return gateway


def _direct_args(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_id": "owner:issue1429:test-1",
        "repository": "James3014/Nexus-new",
        "base_sha": BASE,
        "execution_lane": "DIRECT_CANONICAL",
        "authority_kind": "OWNER_INLINE",
        "allowed_paths": ["nexus/orchestrator/**", "tests/nexus/orchestrator/**"],
        "authority_goal_id": "issue1429",
        "authority_coordination_scope_id": "chat",
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


def test_caller_cannot_self_assert_owner_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, monkeypatch)

    with pytest.raises(
        GatewayInputError,
        match="MUTATION_ADMISSION_CALLER_AUTHORITY_FORBIDDEN",
    ):
        gateway._call_tool(
            "nexus_mutation_admit",
            _direct_args(owner_confirmation=True),
        )


def test_operation_id_cannot_widen_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _gateway(tmp_path, monkeypatch)
    gateway._call_tool("nexus_mutation_admit", _direct_args())

    with pytest.raises(
        GatewayInputError,
        match="OPERATION_ID_REUSED_WITH_DIFFERENT_ADMISSION",
    ):
        gateway._call_tool(
            "nexus_mutation_admit",
            _direct_args(allowed_paths=["docs/**"]),
        )


def _task_card(
    tmp_path: Path,
    *,
    status: str = "ACTIVE",
) -> tuple[str, str]:
    relative = "tasks/test-1429/00-g1.md"
    card = tmp_path / relative
    card.parent.mkdir(parents=True, exist_ok=True)
    source = (
        "# Task Card: test\n\n"
        "artifact_authority: current\n"
        f"status: {status}\n"
        "task_id: issue-1429-test\n"
        "attempt_id: attempt-1429-test\n"
        "execution_lane: `GOVERNED`\n"
        "- GitHub Issue: `James3014/Nexus-new#1429`\n"
        "\n## Allowed files\n\n- `nexus/orchestrator/**`\n"
    )
    card.write_text(source, encoding="utf-8")
    return relative, hashlib.sha256(source.encode("utf-8")).hexdigest()


def _governed_args(task_card_path: str, task_card_hash: str) -> dict[str, object]:
    return {
        "operation_id": "owner:issue1429:governed",
        "repository": "James3014/Nexus-new",
        "base_sha": BASE,
        "execution_lane": "GOVERNED",
        "authority_kind": "TRACKED_TASK_CARD",
        "allowed_paths": ["nexus/orchestrator/**"],
        "issue_number": 1429,
        "task_id": "issue-1429-test",
        "attempt_id": "attempt-1429-test",
        "task_card_path": task_card_path,
        "task_card_hash": task_card_hash,
    }


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
                authority_goal_id=None,
                authority_coordination_scope_id=None,
            ),
        )


def test_governed_admission_binds_physical_task_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    path, card_hash = _task_card(tmp_path)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    gateway = _gateway(tmp_path, monkeypatch)

    receipt = gateway._call_tool(
        "nexus_mutation_admit",
        _governed_args(path, card_hash),
    )

    assert receipt["authority_kind"] == "TRACKED_TASK_CARD"
    assert receipt["task_card_hash"] == card_hash
    assert receipt["governance_source_head"] == BASE


def test_governed_admission_blocks_missing_or_mismatched_task_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    gateway = _gateway(tmp_path, monkeypatch)

    with pytest.raises(GatewayInputError, match="MUTATION_ADMISSION_TASK_CARD_NOT_FOUND"):
        gateway._call_tool(
            "nexus_mutation_admit",
            _governed_args("tasks/test-1429/missing.md", "a" * 64),
        )

    path, card_hash = _task_card(tmp_path)
    with pytest.raises(GatewayInputError, match="MUTATION_ADMISSION_TASK_CARD_HASH_MISMATCH"):
        gateway._call_tool(
            "nexus_mutation_admit",
            _governed_args(path, "f" * 64 if card_hash != "f" * 64 else "e" * 64),
        )


def test_governed_admission_blocks_superseded_task_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    path, card_hash = _task_card(tmp_path, status="SUPERSEDED")
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    gateway = _gateway(tmp_path, monkeypatch)

    with pytest.raises(GatewayInputError, match="MUTATION_ADMISSION_TASK_CARD_NOT_ACTIVE"):
        gateway._call_tool(
            "nexus_mutation_admit",
            _governed_args(path, card_hash),
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
        # Issue at the real clock: the integration gate validates expiry against
        # wall time, so a fixed issue date becomes a time bomb once the TTL elapses.
        now_provider=lambda: datetime.now(timezone.utc),
    )
    scope = allowed_paths or ["allowed.txt"]
    effect: dict[str, object] = {
        "operation_id": operation_id,
        "target_repository": "James3014/Nexus-new",
        "base_sha": base,
        "execution_lane": "DIRECT_CANONICAL",
        "allowed_paths": scope,
        "issue_number": 1429,
    }
    return store.admit(
        operation_id=operation_id,
        repository="James3014/Nexus-new",
        base_sha=base,
        execution_lane="DIRECT_CANONICAL",
        authority_kind="OWNER_INLINE",
        allowed_paths=scope,
        authority_reference=_authority_reference(effect),
        issue_number=1429,
    )


def test_receipt_projection_does_not_change_identity_and_unknown_fields_fail_closed(
    tmp_path: Path,
) -> None:
    receipt = _admission(tmp_path / "state", base="a" * 40)

    block = pr_binding_block(receipt)
    assert receipt["receipt_hash"] in block

    forged = {**receipt, "forged_authority": "caller-controlled"}
    with pytest.raises(MutationAdmissionError, match="ADMISSION_RECEIPT_FIELDS_INVALID"):
        pr_binding_block(forged)


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


def _commit_rename(repo: Path, source: str, destination: str) -> str:
    (repo / Path(destination)).parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "mv", source, destination)
    _git(repo, "commit", "-m", f"rename {source} -> {destination}")
    return _git(repo, "rev-parse", "HEAD")


def _seed(repo: Path, *paths: str) -> str:
    for path in paths:
        target = repo / Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{path}\n", encoding="utf-8")
        _git(repo, "add", path)
    _git(repo, "commit", "-m", "seed")
    return _git(repo, "rev-parse", "HEAD")


def test_integration_gate_blocks_a_rename_from_outside_into_scope(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    # #2765: git diff --name-only reported only the destination of a rename
    repo, _base, _head = git_repo
    base = _seed(repo, "outside/x.py")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:rename-in",
        allowed_paths=["allowed/**"],
    )
    head = _commit_rename(repo, "outside/x.py", "allowed/x.py")

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "BLOCK"
    assert "ADMISSION_SCOPE_ESCAPE" in report["blockers"]
    assert report["scope_escape_paths"] == ["outside/x.py"]
    assert sorted(report["changed_paths"]) == ["allowed/x.py", "outside/x.py"]


def test_integration_gate_passes_a_rename_inside_scope(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    repo, _base, _head = git_repo
    base = _seed(repo, "allowed/a.py")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:rename-inside",
        allowed_paths=["allowed/**"],
    )
    head = _commit_rename(repo, "allowed/a.py", "allowed/b.py")

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "PASS"
    assert sorted(report["changed_paths"]) == ["allowed/a.py", "allowed/b.py"]
    assert report["scope_escape_paths"] == []


def test_integration_gate_blocks_a_rename_from_scope_to_outside(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    repo, _base, _head = git_repo
    base = _seed(repo, "allowed/a.py")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:rename-out",
        allowed_paths=["allowed/**"],
    )
    head = _commit_rename(repo, "allowed/a.py", "outside/a.py")

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "BLOCK"
    assert report["scope_escape_paths"] == ["outside/a.py"]


def test_integration_gate_reads_non_ascii_names_unquoted(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    repo, _base, _head = git_repo
    base = _seed(repo, "allowed/seed.py")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:non-ascii",
        allowed_paths=["allowed/**"],
    )
    (repo / "allowed" / "設定.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "allowed/設定.md")
    _git(repo, "commit", "-m", "non-ascii")
    head = _git(repo, "rev-parse", "HEAD")

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo,
        state_root=state_root,
    )

    assert report["status"] == "PASS"
    assert report["changed_paths"] == ["allowed/設定.md"]


@pytest.mark.parametrize(
    "name", ["\tallowed/x.py", "\nallowed/x.py", " allowed/x.py", "allowed/x.py "]
)
def test_integration_gate_blocks_whitespace_wrapped_names(
    tmp_path: Path, git_repo: tuple[Path, str, str], name: str
) -> None:
    # -z hands names over unquoted; a name must not be stripped into scope (#2765 review)
    repo, _base, _head = git_repo
    base = _seed(repo, "allowed/seed.py")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:whitespace",
        allowed_paths=["allowed/**"],
    )
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    _git(repo, "add", "--", name)
    _git(repo, "commit", "-m", "whitespace name")
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
    assert report["scope_escape_paths"] == [name]


def test_integration_gate_ignores_diff_relative_config(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    # diff.relative only filters when git runs below the top level, so the gate is
    # pointed at a subdirectory here; --no-relative keeps outside/x.py visible.
    repo, _base, _head = git_repo
    base = _seed(repo, "outside/x.py", "allowed/a.py")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:diff-relative",
        allowed_paths=["allowed/**"],
    )
    (repo / "outside" / "x.py").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "outside/x.py")
    _git(repo, "commit", "-m", "outside change")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "config", "diff.relative", "true")

    report = evaluate(
        repository="James3014/Nexus-new",
        base_sha=base,
        head_sha=head,
        pr_body=pr_binding_block(receipt),
        repo_root=repo / "allowed",
        state_root=state_root,
    )

    assert report["status"] == "BLOCK"
    assert report["scope_escape_paths"] == ["outside/x.py"]


def test_integration_gate_sees_an_ignored_submodule_change(
    tmp_path: Path, git_repo: tuple[Path, str, str]
) -> None:
    # A submodule "ignore=all" setting must not hide an out-of-scope gitlink update.
    repo, _base, _head = git_repo
    sub = tmp_path / "sub"
    sub.mkdir()
    _git(sub, "init", "-b", "main")
    _git(sub, "config", "user.email", "test@example.test")
    _git(sub, "config", "user.name", "Test User")
    (sub / "f.txt").write_text("1\n", encoding="utf-8")
    _git(sub, "add", "f.txt")
    _git(sub, "commit", "-m", "one")
    first = _git(sub, "rev-parse", "HEAD")
    (sub / "f.txt").write_text("2\n", encoding="utf-8")
    _git(sub, "commit", "-am", "two")
    second = _git(sub, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{first},outside/sub")
    (repo / ".gitmodules").write_text(
        '[submodule "outside/sub"]\n\tpath = outside/sub\n\turl = ./sub\n\tignore = all\n',
        encoding="utf-8",
    )
    _git(repo, "add", ".gitmodules")
    _git(repo, "commit", "-m", "add ignored submodule")
    base = _git(repo, "rev-parse", "HEAD")
    state_root = tmp_path / "state"
    receipt = _admission(
        state_root,
        base=base,
        operation_id="owner:issue2765:submodule",
        allowed_paths=["allowed/**"],
    )
    _git(repo, "update-index", "--cacheinfo", f"160000,{second},outside/sub")
    _git(repo, "commit", "-m", "bump ignored submodule")
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
    assert report["scope_escape_paths"] == ["outside/sub"]


@pytest.mark.parametrize(
    "path, allowed",
    [
        ("allowed/x.py", True),
        (" allowed/x.py", False),
        ("allowed/x.py\n", False),
        ("\tallowed/x.py", False),
        ("allowed/x\x7f.py", False),
        ("allowed/設定.md", True),
    ],
)
def test_path_is_allowed_checks_the_exact_name(path: str, allowed: bool) -> None:
    from nexus.orchestrator.mutation_admission import path_is_allowed

    assert path_is_allowed(path, ["allowed/**"]) is allowed
