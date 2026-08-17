from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.services.external_intelligence_closure import (
    ACCEPTANCE_PACKET_SCHEMA,
    CLAIM_CEILING,
    CLOSURE_CAPSULE_SCHEMA,
    COMPOSITION_REPAIR_DELTA_SCHEMA,
    TASK_CANDIDATE_SCHEMA,
    UNIT_REPAIR_DELTA_SCHEMA,
    UNIT_VERIFICATION_SCHEMA,
    WHOLE_VERIFICATION_SCHEMA,
    ClosureError,
    ClosureStore,
    CompositionWorkspaceAllocator,
    ExternalIntelligenceClosureRuntime,
    build_composition_repair_delta,
    build_unit_repair_delta,
    compose_task_candidate,
    parse_task_card_authority,
    validate_worker_receipt,
    verify_unit_candidate,
    verify_whole_task_candidate,
)
from nexus.services.external_intelligence_fanout import MODEL, PROVIDER, WORKER_RECEIPT_SCHEMA


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "nexus-test@example.invalid")
    _git(root, "config", "user.name", "Nexus Test")
    (root / "a.py").write_text("A = 0\n", encoding="utf-8")
    (root / "b.py").write_text("B = 0\n", encoding="utf-8")
    (root / "c.py").write_text("C = 0\n", encoding="utf-8")
    _git(root, "add", "a.py", "b.py", "c.py")
    _git(root, "commit", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD")


def make_task_card(repo: Path, commands: list[str] | None = None) -> tuple[str, str, str]:
    ref = "tasks/test-closure/00-test.md"
    path = repo / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    default_cmds = [
        f'{sys.executable} -c "raise SystemExit(0)"',
        f'{sys.executable} -c "raise SystemExit(1)"',
        f'{sys.executable} -c "raise SystemExit(2)"',
        f'{sys.executable} -c "raise SystemExit(3)"',
        f'{sys.executable} -c "raise SystemExit(7)"',
        f"{sys.executable} -c \"from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()\"",
        f"{sys.executable} -c \"from pathlib import Path; assert 'B = 1' in Path('b.py').read_text()\"",
        f"{sys.executable} -c \"from pathlib import Path; assert 'A = 2' in Path('a.py').read_text()\"",
        f"{sys.executable} -c \"from pathlib import Path; Path('a.py').write_text('A = 7\\n')\"",
        f"{sys.executable} -c \"from pathlib import Path; assert 'A = ' in Path('a.py').read_text()\"",
        f"{sys.executable} -c \"from pathlib import Path; assert Path('a.py').read_text() == 'A = 2\\n' and Path('b.py').read_text() == 'B = 1\\n'\"",
        f"{sys.executable} -c \"from pathlib import Path; assert 'A = 1' in Path('a.py').read_text() and 'B = 1' in Path('b.py').read_text()\"",
    ]
    if commands:
        default_cmds.extend(commands)
    lines = [
        "# Task Card: test-closure",
        "",
        "- task_id: `test-closure`",
        "- status: ACTIVE",
        "",
        "## Allowed files",
        "- `a.py`",
        "- `b.py`",
        "- `c.py`",
        "",
        "## Verification commands",
        "```bash",
        *default_cmds,
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    _git(repo, "add", ref)
    _git(repo, "commit", "-m", "test task card")
    head_sha = _git(repo, "rev-parse", "HEAD")
    return ref, _sha256(path.read_bytes()), head_sha


def _worktree(repo: Path, root: Path, name: str, base: str) -> Path:
    path = root / name
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(path), base],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    _git(path, "config", "user.email", "nexus-test@example.invalid")
    _git(path, "config", "user.name", "Nexus Test")
    return path


def _receipt_identity(receipt: dict) -> str:
    material = dict(receipt)
    material.pop("receipt_id", None)
    return _sha256(_canonical_json(material))


def _advance_receipt(
    *,
    repo: Path,
    base: str,
    workspace: Path,
    unit_id: str,
    target: str,
    content: str | None,
    mutation_paths: list[str] | None = None,
    allow_deletions: bool = False,
    parent: dict | None = None,
) -> dict:
    parent_commit = _git(workspace, "rev-parse", "HEAD")
    path = workspace / target
    if content is None:
        path.unlink()
    else:
        path.write_text(content, encoding="utf-8")
    _git(workspace, "add", "-A", "--", target)
    _git(workspace, "commit", "-m", f"unit {unit_id}")
    candidate_commit = _git(workspace, "rev-parse", "HEAD")
    candidate_tree = _git(workspace, "rev-parse", "HEAD^{tree}")
    diff = _git(workspace, "diff", "--binary", parent_commit, candidate_commit)
    changed = [
        line
        for line in _git(
            workspace, "diff", "--name-only", parent_commit, candidate_commit, "--"
        ).splitlines()
        if line
    ]
    deleted: list[str] = []
    for line in _git(
        workspace, "diff", "--name-status", parent_commit, candidate_commit, "--"
    ).splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("D") and len(parts) >= 2:
            deleted.append(parts[-1])
    session = parent["session_id"] if parent else f"ses_test_{unit_id}_00000000"
    workspace_id = parent["workspace_id"] if parent else f"ws-{unit_id}"
    receipt = {
        "schema": WORKER_RECEIPT_SCHEMA,
        "status": "CANDIDATE_READY_FOR_VERIFICATION",
        "task_id": "task-1",
        "unit_id": unit_id,
        "attempt_id": f"attempt-{unit_id}-{candidate_commit[:8]}",
        "mode": "REPAIR_CONTINUE" if parent else "INITIAL",
        "provider": PROVIDER,
        "model": MODEL,
        "provider_id": "opencode-go",
        "model_id": "deepseek-v4-flash",
        "session_id": session,
        "workspace_id": workspace_id,
        "workspace_path": str(workspace),
        "base_sha": base,
        "envelope_ref": str(repo / "envelope.json"),
        "envelope_sha256": "a" * 64,
        "mutation_paths": mutation_paths or [target],
        "allow_deletions": allow_deletions,
        "worker_summary": "bounded implementation complete",
        "argv_sha256": "1" * 64,
        "stdout_sha256": "2" * 64,
        "export_sha256": "3" * 64,
        "opencode_version": "1.18.18",
        "parent_receipt_id": parent["receipt_id"] if parent else "",
        "repair_id": "d001" if parent else "",
        "claim_ceiling": "CANDIDATE_READY_FOR_VERIFICATION",
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": _sha256(diff),
        "changed_paths": changed,
        "deleted_paths": deleted,
        "parent_commit": parent_commit,
    }
    receipt["receipt_id"] = _receipt_identity(receipt)
    return receipt


def make_receipt(
    repo: Path,
    tmp_path: Path,
    base: str,
    unit_id: str,
    target: str,
    content: str | None,
    *,
    mutation_paths: list[str] | None = None,
    allow_deletions: bool = False,
) -> dict:
    workspace = _worktree(repo, tmp_path / "units", unit_id, base)
    return _advance_receipt(
        repo=repo,
        base=base,
        workspace=workspace,
        unit_id=unit_id,
        target=target,
        content=content,
        mutation_paths=mutation_paths,
        allow_deletions=allow_deletions,
    )


def verifier(verifier_id: str, expression: str, *, owner_unit: str = "") -> dict:
    value = {"id": verifier_id, "argv": [sys.executable, "-c", expression]}
    if owner_unit:
        value["owner_unit"] = owner_unit
    return value


def runtime(
    repo: Path, tmp_path: Path, *, c_runtime=None, max_repairs: int = 1
) -> ExternalIntelligenceClosureRuntime:
    return ExternalIntelligenceClosureRuntime(
        repository_root=repo,
        allocator=CompositionWorkspaceAllocator(repo, tmp_path / "assembly"),
        store=ClosureStore(tmp_path / "state"),
        c_runtime=c_runtime,
        max_repairs_per_unit=max_repairs,
    )


class RepairingCRuntime:
    def __init__(self, repo: Path, base: str, replacements: dict[str, tuple[str, str]]):
        self.repo = repo
        self.base = base
        self.replacements = replacements
        self.calls: list[dict] = []

    def continue_repair(self, receipt, *, repair_id, repair_ref, repair_sha256):
        raw = Path(repair_ref).read_bytes()
        assert _sha256(raw) == repair_sha256
        delta = json.loads(raw)
        assert delta["unit_id"] == receipt["unit_id"]
        assert delta["session_id"] == receipt["session_id"]
        assert delta["workspace_id"] == receipt["workspace_id"]
        target, content = self.replacements[receipt["unit_id"]]
        self.calls.append({
            "unit_id": receipt["unit_id"],
            "repair_id": repair_id,
            "schema": delta["schema"],
        })
        return _advance_receipt(
            repo=self.repo,
            base=self.base,
            workspace=Path(receipt["workspace_path"]),
            unit_id=receipt["unit_id"],
            target=target,
            content=content,
            mutation_paths=list(receipt["mutation_paths"]),
            allow_deletions=bool(receipt.get("allow_deletions", False)),
            parent=dict(receipt),
        )


def test_unit_verification_binds_physical_receipt_and_hashes(tmp_path):
    repo, base = make_repo(tmp_path)
    receipt = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    bound = validate_worker_receipt(receipt)
    assert bound["candidate_commit"] == receipt["candidate_commit"]
    verification = verify_unit_candidate(
        receipt,
        [
            verifier(
                "unit-a", "from pathlib import Path; assert Path('a.py').read_text() == 'A = 1\\n'"
            )
        ],
    )
    assert verification["schema"] == UNIT_VERIFICATION_SCHEMA
    assert verification["status"] == "PASS"
    assert verification["worker_receipt_id"] == receipt["receipt_id"]
    assert len(verification["results"][0]["stdout_sha256"]) == 64
    assert len(verification["results"][0]["argv_sha256"]) == 64


def test_worker_receipt_hash_tamper_is_rejected(tmp_path):
    repo, base = make_repo(tmp_path)
    receipt = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    receipt["worker_summary"] = "tampered"
    with pytest.raises(ClosureError, match="WORKER_RECEIPT_IDENTITY_MISMATCH"):
        validate_worker_receipt(receipt)


def test_dirty_or_head_drift_unit_workspace_is_rejected(tmp_path):
    repo, base = make_repo(tmp_path)
    receipt = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    Path(receipt["workspace_path"], "a.py").write_text("A = 9\n", encoding="utf-8")
    with pytest.raises(ClosureError, match="UNIT_WORKSPACE_DIRTY"):
        validate_worker_receipt(receipt)


def test_verifier_cannot_mutate_workspace_even_when_exit_zero(tmp_path):
    repo, base = make_repo(tmp_path)
    receipt = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    mutating = verifier("mutates", "from pathlib import Path; Path('a.py').write_text('A = 7\\n')")
    with pytest.raises(ClosureError, match="VERIFIER_MUTATED_WORKSPACE"):
        verify_unit_candidate(receipt, [mutating])


def test_unit_failure_builds_exact_same_session_repair_delta(tmp_path):
    repo, base = make_repo(tmp_path)
    receipt = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    verification = verify_unit_candidate(receipt, [verifier("fail-a", "raise SystemExit(7)")])
    assert verification["status"] == "FAIL"
    delta = build_unit_repair_delta(receipt, verification, repair_index=1)
    assert delta["schema"] == UNIT_REPAIR_DELTA_SCHEMA
    assert delta["parent_receipt_id"] == receipt["receipt_id"]
    assert delta["session_id"] == receipt["session_id"]
    assert delta["workspace_id"] == receipt["workspace_id"]
    assert delta["allowed_mutation_paths"] == receipt["mutation_paths"]


def test_close_task_rejects_physical_task_card_hash_mismatch(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, _card_hash, head_sha = make_task_card(repo)
    receipt = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    with pytest.raises(ClosureError, match="TASK_CARD_HASH_MISMATCH"):
        runtime(repo, tmp_path).close_task(
            main_sha=head_sha,
            unit_receipts=[receipt],
            unit_verifiers={"ua": [verifier("unit", "raise SystemExit(0)")]},
            whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
            task_card_ref=card_ref,
            task_card_hash="f" * 64,
        )


def test_unit_failure_without_c_runtime_returns_bounded_repair_required(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    receipt = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    result = runtime(repo, tmp_path).close_task(
        main_sha=head_sha,
        unit_receipts=[receipt],
        unit_verifiers={
            "ua": [
                verifier(
                    "needs-two",
                    "from pathlib import Path; assert 'A = 2' in Path('a.py').read_text()",
                )
            ]
        },
        whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
    )
    assert result["status"] == "UNIT_REPAIR_REQUIRED"
    assert result["repair_deltas"][0]["schema"] == UNIT_REPAIR_DELTA_SCHEMA
    assert result["acceptance_packet"] == {}
    assert result["claim_ceiling"] == "NO_ACCEPTANCE_CLAIM"


def test_repair_budget_zero_fails_closed_without_dispatch(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    receipt = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    result = runtime(repo, tmp_path, max_repairs=0).close_task(
        main_sha=head_sha,
        unit_receipts=[receipt],
        unit_verifiers={"ua": [verifier("fail", "raise SystemExit(1)")]},
        whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
    )
    assert result["status"] == "REPAIR_BUDGET_EXHAUSTED"
    assert result["repair_deltas"] == []


def test_repair_budget_is_durable_across_runtime_restart(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    receipt = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    first = runtime(repo, tmp_path, max_repairs=1).close_task(
        main_sha=head_sha,
        unit_receipts=[receipt],
        unit_verifiers={"ua": [verifier("fail", "raise SystemExit(1)")]},
        whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
    )
    assert first["status"] == "UNIT_REPAIR_REQUIRED"
    assert len(first["repair_deltas"]) == 1
    second = runtime(repo, tmp_path, max_repairs=1).close_task(
        main_sha=head_sha,
        unit_receipts=[receipt],
        unit_verifiers={"ua": [verifier("fail", "raise SystemExit(1)")]},
        whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
    )
    assert second["status"] == "REPAIR_BUDGET_EXHAUSTED"
    assert second["repair_deltas"] == []


def test_repair_result_cannot_substitute_session_identity(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    receipt = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")

    class BadSessionRuntime(RepairingCRuntime):
        def continue_repair(self, receipt, *, repair_id, repair_ref, repair_sha256):
            repaired = super().continue_repair(
                receipt,
                repair_id=repair_id,
                repair_ref=repair_ref,
                repair_sha256=repair_sha256,
            )
            repaired["session_id"] = "ses_substituted_00000000"
            repaired["receipt_id"] = _receipt_identity(repaired)
            return repaired

    bad = BadSessionRuntime(repo, head_sha, {"ua": ("a.py", "A = 2\n")})
    with pytest.raises(ClosureError, match="REPAIR_SESSION_ID_MISMATCH"):
        runtime(repo, tmp_path, c_runtime=bad, max_repairs=1).close_task(
            main_sha=head_sha,
            unit_receipts=[receipt],
            unit_verifiers={
                "ua": [
                    verifier(
                        "needs-two",
                        "from pathlib import Path; assert 'A = 2' in Path('a.py').read_text()",
                    )
                ]
            },
            whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
            task_card_ref=card_ref,
            task_card_hash=card_hash,
        )


def test_multi_unit_composition_is_deterministic_and_clean(tmp_path):
    repo, base = make_repo(tmp_path)
    ua = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    ub = make_receipt(repo, tmp_path, base, "ub", "b.py", "B = 1\n")
    va = verify_unit_candidate(
        ua, [verifier("a", "from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()")]
    )
    vb = verify_unit_candidate(
        ub, [verifier("b", "from pathlib import Path; assert 'B = 1' in Path('b.py').read_text()")]
    )
    candidate, lease = compose_task_candidate(
        repository_root=repo,
        allocator=CompositionWorkspaceAllocator(repo, tmp_path / "assembly"),
        receipts=[ub, ua],
        verifications=[vb, va],
    )
    assert candidate["schema"] == TASK_CANDIDATE_SCHEMA
    assert candidate["composition_order"] == ["ua", "ub"]
    assert candidate["changed_paths"] == ["a.py", "b.py"]
    assert _git(Path(lease.path), "status", "--porcelain=v1") == ""
    assert _git(Path(lease.path), "rev-parse", "HEAD") == candidate["candidate_commit"]


def test_composition_requires_one_common_base(tmp_path):
    repo, base = make_repo(tmp_path)
    ua = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    (repo / "c.py").write_text("C = 9\n", encoding="utf-8")
    _git(repo, "add", "c.py")
    _git(repo, "commit", "-m", "second-base")
    base2 = _git(repo, "rev-parse", "HEAD")
    ub = make_receipt(repo, tmp_path, base2, "ub", "b.py", "B = 1\n")
    va = verify_unit_candidate(ua, [verifier("a", "raise SystemExit(0)")])
    vb = verify_unit_candidate(ub, [verifier("b", "raise SystemExit(0)")])
    with pytest.raises(ClosureError, match="COMMON_BASE_REQUIRED"):
        compose_task_candidate(
            repository_root=repo,
            allocator=CompositionWorkspaceAllocator(repo, tmp_path / "assembly"),
            receipts=[ua, ub],
            verifications=[va, vb],
        )


def test_composition_path_overlap_fails_closed(tmp_path):
    repo, base = make_repo(tmp_path)
    ua = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n", mutation_paths=["a.py"])
    ub = make_receipt(repo, tmp_path, base, "ub", "a.py", "A = 2\n", mutation_paths=["a.py"])
    va = verify_unit_candidate(ua, [verifier("a", "raise SystemExit(0)")])
    vb = verify_unit_candidate(ub, [verifier("b", "raise SystemExit(0)")])
    with pytest.raises(ClosureError, match="COMPOSITION_PATH_OVERLAP"):
        compose_task_candidate(
            repository_root=repo,
            allocator=CompositionWorkspaceAllocator(repo, tmp_path / "assembly"),
            receipts=[ua, ub],
            verifications=[va, vb],
        )


def test_unauthorized_unit_deletion_is_rejected_before_composition(tmp_path):
    repo, base = make_repo(tmp_path)
    receipt = make_receipt(repo, tmp_path, base, "ua", "a.py", None, allow_deletions=False)
    with pytest.raises(ClosureError, match="UNIT_DELETION_NOT_AUTHORIZED"):
        validate_worker_receipt(receipt)


def test_whole_task_verification_records_explicit_owner(tmp_path):
    repo, base = make_repo(tmp_path)
    ua = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    va = verify_unit_candidate(ua, [verifier("unit", "raise SystemExit(0)")])
    candidate, _ = compose_task_candidate(
        repository_root=repo,
        allocator=CompositionWorkspaceAllocator(repo, tmp_path / "assembly"),
        receipts=[ua],
        verifications=[va],
    )
    whole = verify_whole_task_candidate(
        candidate, [verifier("whole-a", "raise SystemExit(3)", owner_unit="ua")]
    )
    assert whole["schema"] == WHOLE_VERIFICATION_SCHEMA
    assert whole["status"] == "FAIL"
    delta = build_composition_repair_delta(ua, whole, repair_index=1)
    assert delta["schema"] == COMPOSITION_REPAIR_DELTA_SCHEMA
    assert delta["unit_id"] == "ua"
    assert delta["session_id"] == ua["session_id"]


def test_ambiguous_whole_failure_requires_scope_delta_and_no_acceptance(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    ua = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    ub = make_receipt(repo, tmp_path, head_sha, "ub", "b.py", "B = 1\n")
    result = runtime(repo, tmp_path).close_task(
        main_sha=head_sha,
        unit_receipts=[ua, ub],
        unit_verifiers={
            "ua": [verifier("a", "raise SystemExit(0)")],
            "ub": [verifier("b", "raise SystemExit(0)")],
        },
        whole_verifiers=[verifier("ambiguous", "raise SystemExit(2)")],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
    )
    assert result["status"] == "SCOPE_DELTA_REQUIRED"
    assert result["reason"] == "WHOLE_FAILURE_OWNER_AMBIGUOUS"
    assert result["acceptance_packet"] == {}
    assert result["control_capsule"] == {}


def test_unique_owner_whole_failure_repairs_same_unit_then_closes(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    ua = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    ub = make_receipt(repo, tmp_path, head_sha, "ub", "b.py", "B = 1\n")
    repairing = RepairingCRuntime(repo, head_sha, {"ua": ("a.py", "A = 2\n")})
    result = runtime(repo, tmp_path, c_runtime=repairing, max_repairs=1).close_task(
        main_sha=head_sha,
        unit_receipts=[ua, ub],
        unit_verifiers={
            "ua": [
                verifier(
                    "a-valid", "from pathlib import Path; assert 'A = ' in Path('a.py').read_text()"
                )
            ],
            "ub": [
                verifier(
                    "b-valid",
                    "from pathlib import Path; assert 'B = 1' in Path('b.py').read_text()",
                )
            ],
        },
        whole_verifiers=[
            verifier(
                "whole-a-owner",
                "from pathlib import Path; assert Path('a.py').read_text() == 'A = 2\\n' and Path('b.py').read_text() == 'B = 1\\n'",
                owner_unit="ua",
            )
        ],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
        external_intelligence_refs=["receipt://external/task-1"],
    )
    assert result["status"] == CLAIM_CEILING
    assert repairing.calls == [
        {"unit_id": "ua", "repair_id": "d001", "schema": COMPOSITION_REPAIR_DELTA_SCHEMA}
    ]
    assert result["telemetry"]["repair_count"] == 1
    assert result["telemetry"]["policy_tuned"] is False
    assert result["task_candidate"]["changed_paths"] == ["a.py", "b.py"]
    assert result["whole_verification"]["status"] == "PASS"


def test_success_emits_acceptance_packet_and_compact_capsule_without_approval_claim(tmp_path):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    ua = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    ub = make_receipt(repo, tmp_path, head_sha, "ub", "b.py", "B = 1\n")
    result = runtime(repo, tmp_path).close_task(
        main_sha=head_sha,
        unit_receipts=[ub, ua],
        unit_verifiers={
            "ua": [
                verifier(
                    "a", "from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()"
                )
            ],
            "ub": [
                verifier(
                    "b", "from pathlib import Path; assert 'B = 1' in Path('b.py').read_text()"
                )
            ],
        },
        whole_verifiers=[
            verifier(
                "whole",
                "from pathlib import Path; assert 'A = 1' in Path('a.py').read_text() and 'B = 1' in Path('b.py').read_text()",
            )
        ],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
        external_intelligence_refs=["receipt://a", "receipt://b"],
    )
    packet = result["acceptance_packet"]
    capsule = result["control_capsule"]
    assert result["status"] == CLAIM_CEILING
    assert packet["schema"] == ACCEPTANCE_PACKET_SCHEMA
    assert packet["current_gate"] == "PENDING_INDEPENDENT_ACCEPTANCE"
    assert packet["claim_ceiling"] == CLAIM_CEILING
    assert packet["task_candidate"]["composition_order"] == ["ua", "ub"]
    assert capsule["schema"] == CLOSURE_CAPSULE_SCHEMA
    assert capsule["current_gate"] == "PENDING_INDEPENDENT_ACCEPTANCE"
    assert capsule["next_action"] == "run_independent_candidate_acceptance_audit"
    assert Path(packet["artifact_ref"]).is_file()
    assert _sha256(Path(packet["artifact_ref"]).read_bytes()) == packet["artifact_sha256"]
    assert Path(capsule["artifact_ref"]).is_file()
    assert _sha256(Path(capsule["artifact_ref"]).read_bytes()) == capsule["artifact_sha256"]
    forbidden = {"approved", "accepted", "integrated", "merged", "pushed", "production_ready"}
    blob = json.dumps(result, sort_keys=True).lower()
    assert not any(f'"{word}": true' in blob for word in forbidden)


def test_mixed_whole_failure_owners_cannot_build_composition_repair_delta(tmp_path):
    repo, base = make_repo(tmp_path)
    ua = make_receipt(repo, tmp_path, base, "ua", "a.py", "A = 1\n")
    va = verify_unit_candidate(ua, [verifier("unit", "raise SystemExit(0)")])
    candidate, _ = compose_task_candidate(
        repository_root=repo,
        allocator=CompositionWorkspaceAllocator(repo, tmp_path / "assembly"),
        receipts=[ua],
        verifications=[va],
    )
    whole = verify_whole_task_candidate(
        candidate,
        [
            verifier("owned", "raise SystemExit(1)", owner_unit="ua"),
            verifier("unowned", "raise SystemExit(1)"),
        ],
    )
    with pytest.raises(ClosureError, match="WHOLE_FAILURE_NOT_UNIQUELY_OWNED"):
        build_composition_repair_delta(ua, whole, repair_index=1)


def test_closure_rejects_unauthorized_verifier_before_subprocess(tmp_path, monkeypatch):
    repo, base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    ua = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    called = []
    real_run = subprocess.run

    def spy_run(args, **kwargs):
        called.append(args)
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    with pytest.raises(ClosureError, match="VERIFIER_NOT_AUTHORIZED"):
        runtime(repo, tmp_path).close_task(
            main_sha=head_sha,
            unit_receipts=[ua],
            unit_verifiers={
                "ua": [
                    {"id": "evil", "argv": ["python3", "-c", "import os; os.system('malicious')"]}
                ]
            },
            whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
            task_card_ref=card_ref,
            task_card_hash=card_hash,
        )

    # Verify the unauthorized verifier command was NEVER executed in subprocess
    assert not any("malicious" in str(cmd) for cmd in called)


def test_real_closure_a_to_b_unattended_freshness_regression(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "nexus-test@example.invalid")
    _git(repo, "config", "user.name", "Nexus Test")
    (repo / "a.py").write_text("A = 0\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-m", "init")

    # Commit A with Task Card A (authorizes only verifier A)
    card_ref = "tasks/test-closure/00-test.md"
    card_path = repo / card_ref
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_a_text = (
        "# Task Card: test-closure\n\n"
        "- task_id: `test-closure`\n"
        "- status: ACTIVE\n\n"
        "## Allowed files\n"
        "- `a.py`\n\n"
        "## Verification commands\n"
        "```bash\n"
        f"{sys.executable} -c \"assert False, 'A verifier'\"\n"
        "```\n"
    )
    card_path.write_text(card_a_text, encoding="utf-8")
    _git(repo, "add", card_ref)
    _git(repo, "commit", "-m", "commit A - task card A")
    sha_A = _git(repo, "rev-parse", "HEAD")
    hash_A = _sha256(card_a_text)

    # Commit B with Task Card B (authorizes verifier B)
    cmd_b = f"{sys.executable} -c \"from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()\""
    card_b_text = (
        "# Task Card: test-closure\n\n"
        "- task_id: `test-closure`\n"
        "- status: ACTIVE\n\n"
        "## Allowed files\n"
        "- `a.py`\n\n"
        "## Verification commands\n"
        "```bash\n"
        f"{cmd_b}\n"
        f'{sys.executable} -c "raise SystemExit(0)"\n'
        "```\n"
    )
    card_path.write_text(card_b_text, encoding="utf-8")
    _git(repo, "add", card_ref)
    _git(repo, "commit", "-m", "commit B - task card B")
    sha_B = _git(repo, "rev-parse", "HEAD")
    hash_B = _sha256(card_b_text)

    # Reset physical checkout back to Commit A (simulating daemon runtime where HEAD=A while remote main=B)
    _git(repo, "checkout", sha_A)
    assert _git(repo, "rev-parse", "HEAD") == sha_A
    assert card_path.read_text(encoding="utf-8") == card_a_text

    # Worker receipt is produced against base commit B
    receipt_b = make_receipt(repo, tmp_path, sha_B, "ua", "a.py", "A = 1\n")

    # Invoke REAL closure runtime
    c_runtime = runtime(repo, tmp_path)
    result = c_runtime.close_task(
        main_sha=sha_B,
        unit_receipts=[receipt_b],
        unit_verifiers={
            "ua": [
                {
                    "id": "b-check",
                    "argv": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()",
                    ],
                }
            ]
        },
        whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
        task_card_ref=card_ref,
        task_card_hash=hash_B,
    )

    # Assert closure succeeded using Task Card B authority
    assert result["status"] == CLAIM_CEILING
    assert result["whole_verification"]["status"] == "PASS"

    # Assert runtime HEAD remained at Commit A and worktree is completely clean
    assert _git(repo, "rev-parse", "HEAD") == sha_A
    assert _git(repo, "status", "--porcelain=v1") == ""
    assert card_path.read_text(encoding="utf-8") == card_a_text

    # Negative Paired Case A: main_sha=B with hash_A => TASK_CARD_HASH_MISMATCH
    with pytest.raises(ClosureError, match="TASK_CARD_HASH_MISMATCH"):
        c_runtime.close_task(
            main_sha=sha_B,
            unit_receipts=[receipt_b],
            unit_verifiers={
                "ua": [
                    {
                        "id": "b-check",
                        "argv": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()",
                        ],
                    }
                ]
            },
            whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
            task_card_ref=card_ref,
            task_card_hash=hash_A,
        )

    # Negative Paired Case B: Stale physical card A commands should NOT authorize execution when main_sha=B
    with pytest.raises(ClosureError, match="VERIFIER_NOT_AUTHORIZED"):
        c_runtime.close_task(
            main_sha=sha_B,
            unit_receipts=[receipt_b],
            unit_verifiers={
                "ua": [
                    {
                        "id": "a-fail",
                        "argv": [sys.executable, "-c", "assert False, 'A verifier'"],
                    }
                ]
            },
            whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
            task_card_ref=card_ref,
            task_card_hash=hash_B,
        )

    # Negative Paired Case C: receipt.base_sha (sha_A) != main_sha (sha_B) => CLOSURE_BASE_SHA_MISMATCH
    receipt_a = make_receipt(repo, tmp_path, sha_A, "ua_stale", "a.py", "A = 1\n")
    with pytest.raises(ClosureError, match="CLOSURE_BASE_SHA_MISMATCH"):
        c_runtime.close_task(
            main_sha=sha_B,
            unit_receipts=[receipt_a],
            unit_verifiers={
                "ua_stale": [
                    {
                        "id": "b-check",
                        "argv": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; assert 'A = 1' in Path('a.py').read_text()",
                        ],
                    }
                ]
            },
            whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
            task_card_ref=card_ref,
            task_card_hash=hash_B,
        )


def test_task_card_verification_command_parser_rejects_prose():
    card_text = (
        "# Task Card: test-grammar\n\n"
        "- task_id: `test-grammar`\n"
        "- status: ACTIVE\n\n"
        "## Allowed files\n"
        "- `a.py`\n\n"
        "## Verification commands\n"
        "Please run the test suite carefully.\n"
        "Make sure to check git status.\n"
        "- Note: this is an explanation bullet, not a command.\n"
        "- python3 -m pytest tests/test_unquoted.py is an unquoted prose mention.\n"
        "1. First run the tests.\n\n"
        "```bash\n"
        "python3 -m pytest -q tests/test_a.py\n"
        "# this is a comment inside code block\n"
        "git diff --check\n"
        "```\n\n"
        "- `pytest tests/test_b.py`\n"
    )
    auth = parse_task_card_authority(card_text)
    # The authorized commands must ONLY be the exact fenced or backticked commands
    assert set(auth.verification_commands) == {
        ("python3", "-m", "pytest", "-q", "tests/test_a.py"),
        ("git", "diff", "--check"),
        ("pytest", "tests/test_b.py"),
    }
    # Explanations and prose lines must NOT be parsed as commands
    for cmd in auth.verification_commands:
        assert "Please" not in cmd
        assert "Note:" not in cmd
        assert "explanation" not in cmd
        assert "First" not in cmd
