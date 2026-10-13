from __future__ import annotations

import json
import os
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_sidecar_test", str(SCRIPT)).load_module()

MARKER = "GREEN_CHANGE_MARKER"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD").strip()
    return root, base


SCOPE = {"allowed_change_globs": ["*.py"]}


def _receipt(repo: Path, base: str, *, changed: list[str], decision: str = "GREEN_READY") -> dict:
    _changed, _untracked, digest = guard._collect_worktree_changes(repo, base)
    return guard._green_receipt({
        "schema": guard.GREEN_RECEIPT_SCHEMA,
        "contract_hash": "sha256:" + "a" * 64,
        "contract": dict(SCOPE),
        "repository": "James3014/Nexus-new",
        "issue_number": 1617,
        "generated_at": "2026-10-09T00:00:00Z",
        "decision": decision,
        "repo_head": _git(repo, "rev-parse", "HEAD").strip(),
        "base_revision": base,
        "worktree_diff_sha256": digest,
        "changed_paths": changed,
    })


def _sidecar_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / "gate-sidecars").rglob("*") if p.is_file())


def test_red_witness_receipt_digest_has_durable_sidecar(repo, tmp_path: Path) -> None:
    # RED witness: the receipt commits to a diff digest, but the bytes are gone.
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    state = tmp_path / "state"

    path = guard.persist_green_gate_with_sidecar(state, receipt, repo=root_repo, base=base)

    assert path.is_file()
    assert any(MARKER.encode() in p.read_bytes() for p in _sidecar_files(state)), (
        "tracked patch bytes must be recoverable from the guard state"
    )
    assert (
        guard.verify_gate_sidecar(state, receipt, gate="green")["receipt_hash"]
        == (receipt["receipt_hash"])
    )


def test_sidecar_keeps_receipt_body_and_hash_unchanged(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    state = tmp_path / "state"

    path = guard.persist_green_gate_with_sidecar(state, receipt, repo=root_repo, base=base)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == receipt
    assert "patch" not in stored and "worktree_patch" not in stored


def test_untracked_content_is_sidecar_bound_and_replayable(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "new_test.py").write_text(f"# {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["new_test.py"])
    state = tmp_path / "state"

    guard.write_gate_sidecar(state, receipt, gate="green", repo=root_repo, base=base)
    manifest = guard.verify_gate_sidecar(state, receipt, gate="green")

    assert [entry["path"] for entry in manifest["untracked"]] == ["new_test.py"]
    assert any(MARKER.encode() in p.read_bytes() for p in _sidecar_files(state))


def test_digest_mismatch_fails_closed_without_receipt(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    # Worktree moves after the gate computed its digest.
    (root_repo / "a.py").write_text("x = 3\n", encoding="utf-8")
    state = tmp_path / "state"

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.persist_green_gate_with_sidecar(state, receipt, repo=root_repo, base=base)

    assert exc.value.code == "GATE_SIDECAR_DIGEST_MISMATCH"
    assert not (state / "green-gates").exists()


def test_symlink_untracked_file_is_refused(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    secret = tmp_path / "outside.txt"
    secret.write_text(MARKER, encoding="utf-8")
    os.symlink(secret, root_repo / "link.py")
    receipt = _receipt(root_repo, base, changed=["link.py"])
    state = tmp_path / "state"

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.write_gate_sidecar(state, receipt, gate="green", repo=root_repo, base=base)

    assert exc.value.code == "GATE_SIDECAR_SYMLINK_REFUSED"
    assert not any(MARKER.encode() in p.read_bytes() for p in _sidecar_files(state))


def test_tampered_blob_fails_integrity_check(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    state = tmp_path / "state"
    guard.write_gate_sidecar(state, receipt, gate="green", repo=root_repo, base=base)

    blob = next(p for p in _sidecar_files(state) if p.parent.name == "blobs")
    blob.write_bytes(b"tampered\n")

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.verify_gate_sidecar(state, receipt, gate="green")
    assert exc.value.code == "GATE_SIDECAR_INTEGRITY_FAILED"


def test_sidecar_is_bound_to_exact_receipt_hash(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    state = tmp_path / "state"
    guard.write_gate_sidecar(state, receipt, gate="green", repo=root_repo, base=base)

    other = dict(receipt, generated_at="2026-10-09T00:00:01Z")
    other["receipt_hash"] = guard._sha256_bytes(
        guard._canonical_json({k: v for k, v in other.items() if k != "receipt_hash"}).encode()
    )
    with pytest.raises(guard.DshWorkflowError):
        guard.verify_gate_sidecar(state, other, gate="green")


def test_error_receipt_without_digest_persists_as_before(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    error = guard._green_receipt({
        "schema": guard.GREEN_RECEIPT_SCHEMA,
        "contract_hash": "sha256:" + "a" * 64,
        "generated_at": "2026-10-09T00:00:00Z",
        "decision": "BLOCKED",
        "reason_codes": ["GREEN_GATE_TIMEOUT"],
    })
    state = tmp_path / "state"

    path = guard.persist_green_gate_with_sidecar(state, error, repo=root_repo, base=base)

    assert path.is_file()
    assert not (state / "gate-sidecars").exists()


SECRET = "SECRET_OUT_OF_SCOPE_MARKER"


def _state_bytes(state: Path) -> bytes:
    if not state.exists():
        return b""
    return b"".join(p.read_bytes() for p in state.rglob("*") if p.is_file())


def test_revise_receipt_with_out_of_scope_secret_archives_nothing(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "secret.env").write_text(SECRET, encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["secret.env"], decision="REVISE_GREEN")
    state = tmp_path / "state"

    path = guard.persist_green_gate_with_sidecar(state, receipt, repo=root_repo, base=base)

    assert path.is_file()
    assert not (state / "gate-sidecars").exists()
    assert SECRET.encode() not in _state_bytes(state)


def test_ready_receipt_with_out_of_scope_secret_fails_closed(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "secret.env").write_text(SECRET, encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["secret.env"])
    state = tmp_path / "state"

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.persist_green_gate_with_sidecar(state, receipt, repo=root_repo, base=base)

    assert exc.value.code == "GATE_SIDECAR_SCOPE_VIOLATION"
    assert SECRET.encode() not in _state_bytes(state)
    assert not (state / "green-gates").exists()


def test_unsafe_hash_segment_is_rejected_before_any_path_is_built(repo, tmp_path: Path) -> None:
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    receipt["receipt_hash"] = "sha256:../../escape"
    state = tmp_path / "state"

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.write_gate_sidecar(state, receipt, gate="green", repo=root_repo, base=base)

    assert exc.value.code == "GATE_SIDECAR_INVALID"
    assert not state.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("gate", "red"),
        ("contract_hash", "sha256:" + "b" * 64),
        ("repo_head", "0" * 40),
        ("base_revision", "1" * 40),
    ],
)
def test_manifest_identity_tamper_fails_closed(
    repo, tmp_path: Path, field: str, tampered: str
) -> None:
    root_repo, base = repo
    (root_repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(root_repo, base, changed=["a.py"])
    state = tmp_path / "state"
    manifest_path = guard.write_gate_sidecar(
        state, receipt, gate="green", repo=root_repo, base=base
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = tampered
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.verify_gate_sidecar(state, receipt, gate="green")

    assert exc.value.code == "GATE_SIDECAR_INTEGRITY_FAILED"


def _write_ready_sidecar(repo: Path, base: str, state: Path) -> tuple[dict, Path]:
    (repo / "a.py").write_text(f"x = 2  # {MARKER}\n", encoding="utf-8")
    receipt = _receipt(repo, base, changed=["a.py"])
    manifest_path = guard.write_gate_sidecar(state, receipt, gate="green", repo=repo, base=base)
    return receipt, manifest_path


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("generated_at", "2026-10-10T00:00:00Z"),
        ("repository", "attacker/other"),
        ("issue_number", 9999),
    ],
)
def test_receipt_body_tamper_with_stale_hash_fails_closed(
    repo, tmp_path: Path, field: str, tampered
) -> None:
    root_repo, base = repo
    state = tmp_path / "state"
    receipt, _manifest = _write_ready_sidecar(root_repo, base, state)
    forged = dict(receipt)
    forged[field] = tampered  # receipt_hash deliberately left stale

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.verify_gate_sidecar(state, forged, gate="green")

    assert exc.value.code == "GATE_SIDECAR_RECEIPT_TAMPERED"


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("repository", "attacker/other"),
        ("issue_number", 9999),
        ("claim_ceiling", "CORE_ACCEPTED"),
    ],
)
def test_manifest_provenance_tamper_fails_closed(
    repo, tmp_path: Path, field: str, tampered
) -> None:
    root_repo, base = repo
    state = tmp_path / "state"
    receipt, manifest_path = _write_ready_sidecar(root_repo, base, state)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = tampered
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(guard.DshWorkflowError) as exc:
        guard.verify_gate_sidecar(state, receipt, gate="green")

    assert exc.value.code == "GATE_SIDECAR_INTEGRITY_FAILED"
