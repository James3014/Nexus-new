"""Canonical run receipts follow NEXUS_STATE_ROOT across deploys (#2689).

A "deploy" is ``tmp_path / "a1-deployN"`` named by NEXUS_CANONICAL_SOURCE_ROOT, which
is how the live Gateway passes its per-deploy checkout to the canonical seam.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.core.state_root import CANONICAL_SOURCE_ROOT_ENV, STATE_ROOT_ENV
from nexus.engine.run_receipt_store import (
    CANONICAL_RUNTIME_SUFFIX,
    UNIFIED_RUNTIME_POINTER_SUFFIX,
    copy_run_receipts_to_state_root,
    find_run_receipt,
    run_receipt_path,
    run_reports_dir,
    safe_receipt_name,
)

RUN = Path(".nexus") / "reports" / "run"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (STATE_ROOT_ENV, CANONICAL_SOURCE_ROOT_ENV, "NEXUS_TARGET_ROOT_OVERRIDE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ROOT_ENV, str(state))
    counter = {"n": 0}

    def next_deploy() -> Path:
        counter["n"] += 1
        ws = (tmp_path / f"a1-deploy{counter['n']}").resolve()
        ws.mkdir()
        monkeypatch.setenv(CANONICAL_SOURCE_ROOT_ENV, str(ws))
        return ws

    ws = next_deploy()
    return SimpleNamespace(state=state.resolve(), ws=ws, next=next_deploy, tmp=tmp_path)


def _run_canonical(monkeypatch: pytest.MonkeyPatch, root: Path, task_id: str) -> Any:
    """Drive execute_canonical_product_task with a fake gateway that writes the receipt."""
    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    class _Gateway:
        def __init__(self, project_root):
            self.project_root = project_root

        def ask_unified(self, request, **kwargs):
            receipt = {
                "task_id": request.task_id,
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {"execution_decision_authority": "CapabilityPlanner"},
                "root_receipt": {"schema": "nexus.root_receipt.v1"},
            }
            path = Path(kwargs["receipt_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt), encoding="utf-8")
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _Gateway)
    monkeypatch.setattr("nexus.contracts.root_receipt.validate_root_receipt", lambda _r: (True, []))
    return execute_canonical_product_task(
        "audit the bounded runtime",
        root,
        execution_context={
            "task_id": task_id,
            "workspace_revision": "rev-1",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )


def _old_name(task_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", task_id)[:120] or "task"


# --- unset: unchanged -------------------------------------------------------------


@pytest.mark.parametrize("task_id", ["t-1", "a b/c", "", "x" * 300, "../../etc/passwd", "é中"])
def test_unset_receipt_path_is_the_old_path(tmp_path: Path, task_id: str) -> None:
    expected = tmp_path / RUN / f"{_old_name(task_id)}.canonical_runtime.json"
    assert run_receipt_path(tmp_path, task_id) == expected
    assert run_reports_dir(tmp_path) == tmp_path / RUN
    pointer = run_receipt_path(tmp_path, task_id, UNIFIED_RUNTIME_POINTER_SUFFIX)
    assert pointer == tmp_path / RUN / f"{_old_name(task_id)}.unified_runtime_pointer.json"


def test_unset_canonical_seam_writes_under_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run_canonical(monkeypatch, tmp_path, "seam-unset-1")
    expected = tmp_path.resolve() / RUN / "seam-unset-1.canonical_runtime.json"
    assert Path(result.receipt_path) == expected
    assert expected.is_file()
    assert bool(result) is True


def test_unset_find_and_copy_use_only_root(tmp_path: Path) -> None:
    path = tmp_path / RUN / "t-old.canonical_runtime.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"task_id": "t-old"}', encoding="utf-8")
    assert find_run_receipt("t-old", tmp_path) == path
    assert find_run_receipt("t-old") is None
    assert copy_run_receipts_to_state_root(tmp_path) == []


# --- set: written under the state root ----------------------------------------------


def test_set_canonical_seam_writes_under_state_root(
    monkeypatch: pytest.MonkeyPatch, deploy: SimpleNamespace
) -> None:
    result = _run_canonical(monkeypatch, deploy.ws, "seam-set-1")
    expected = deploy.state / RUN / "seam-set-1.canonical_runtime.json"
    assert Path(result.receipt_path) == expected
    assert expected.is_file()
    assert not (deploy.ws / RUN).exists()
    assert result.root_receipt_valid is True  # disk readback found the moved file


def test_set_isolated_root_stays_in_place(
    monkeypatch: pytest.MonkeyPatch, deploy: SimpleNamespace
) -> None:
    canary = deploy.tmp / "canary-root"
    canary.mkdir()
    result = _run_canonical(monkeypatch, canary, "seam-canary-1")
    assert (
        Path(result.receipt_path) == canary.resolve() / RUN / "seam-canary-1.canonical_runtime.json"
    )
    assert not (deploy.state / RUN).exists()


def test_receipt_written_in_deploy_a_is_found_in_deploy_b(
    monkeypatch: pytest.MonkeyPatch, deploy: SimpleNamespace
) -> None:
    deploy_a = deploy.ws
    result = _run_canonical(monkeypatch, deploy_a, "cross-deploy-1")
    written = json.loads(Path(result.receipt_path).read_text(encoding="utf-8"))

    deploy_b = deploy.next()
    assert deploy_b != deploy_a
    found = find_run_receipt("cross-deploy-1", deploy_b)
    assert found is not None
    assert found.parent == deploy.state / RUN
    assert json.loads(found.read_text(encoding="utf-8")) == written
    # The writer for deploy B points at the same file.
    assert run_receipt_path(deploy_b, "cross-deploy-1") == found


# --- read helper ---------------------------------------------------------------------


def test_find_prefers_state_root_then_falls_back_to_root(deploy: SimpleNamespace) -> None:
    legacy = deploy.ws / RUN / "t-both.canonical_runtime.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"task_id": "t-both", "where": "root"}', encoding="utf-8")
    assert find_run_receipt("t-both", deploy.ws) == legacy  # only the old location exists

    moved = deploy.state / RUN / "t-both.canonical_runtime.json"
    moved.parent.mkdir(parents=True)
    moved.write_text('{"task_id": "t-both", "where": "state"}', encoding="utf-8")
    assert find_run_receipt("t-both", deploy.ws) == moved
    assert find_run_receipt("t-both") == moved
    assert find_run_receipt("t-missing", deploy.ws) is None


@pytest.mark.parametrize(
    "task_id",
    [
        "../../outside",
        "../outside",
        "/abs/outside",
        "a/../../outside",
        "..\\..\\outside",
        "x\x00y",
        "..",
    ],
)
def test_task_id_cannot_escape_run_dir(deploy: SimpleNamespace, task_id: str) -> None:
    run_dir = deploy.state / RUN
    path = run_receipt_path(deploy.ws, task_id)
    assert path.parent == run_dir
    assert os.sep not in safe_receipt_name(task_id)
    assert "/" not in path.name and "\\" not in path.name
    # A file at the traversal target is never returned.
    outside = deploy.tmp / "outside.canonical_runtime.json"
    outside.write_text(json.dumps({"task_id": task_id}), encoding="utf-8")
    found = find_run_receipt(task_id, deploy.ws)
    assert found is None or found.parent in (run_dir, deploy.ws / RUN)


def test_find_does_not_follow_symlinks(deploy: SimpleNamespace) -> None:
    secret = deploy.tmp / "secret.json"
    secret.write_text('{"task_id": "t-link"}', encoding="utf-8")
    run_dir = deploy.state / RUN
    run_dir.mkdir(parents=True)
    (run_dir / "t-link.canonical_runtime.json").symlink_to(secret)
    assert find_run_receipt("t-link", deploy.ws) is None


def test_invalid_suffix_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_receipt_path(tmp_path, "t", "/../x.json")
    with pytest.raises(ValueError):
        find_run_receipt("t", tmp_path, suffix=".json")


# --- one-time copy -------------------------------------------------------------------


def test_copy_is_idempotent_keeps_originals_and_skips_symlinks(deploy: SimpleNamespace) -> None:
    old_root = deploy.tmp / "a1-old"
    old_dir = old_root / RUN
    old_dir.mkdir(parents=True)
    (old_dir / "t-a.canonical_runtime.json").write_text('{"a": 1}', encoding="utf-8")
    (old_dir / "t-b.unified_runtime_pointer.json").write_text(
        '{"unified_runtime_task_id": "t-b"}', encoding="utf-8"
    )
    (old_dir / "notes.txt").write_text("not a receipt", encoding="utf-8")
    secret = deploy.tmp / "secret.json"
    secret.write_text('{"secret": 1}', encoding="utf-8")
    (old_dir / "t-link.canonical_runtime.json").symlink_to(secret)
    (old_dir / "t-dir.canonical_runtime.json").mkdir()
    existing = deploy.state / RUN / "t-a.canonical_runtime.json"
    existing.parent.mkdir(parents=True)
    existing.write_text('{"a": "newer"}', encoding="utf-8")

    created = copy_run_receipts_to_state_root(old_root)

    assert created == [deploy.state / RUN / "t-b.unified_runtime_pointer.json"]
    assert json.loads(existing.read_text(encoding="utf-8")) == {"a": "newer"}  # never overwritten
    assert not (deploy.state / RUN / "t-link.canonical_runtime.json").exists()
    assert not (deploy.state / RUN / "t-link.canonical_runtime.json").is_symlink()
    assert not (deploy.state / RUN / "notes.txt").exists()
    assert sorted(p.name for p in old_dir.iterdir()) == sorted([
        "notes.txt",
        "t-a.canonical_runtime.json",
        "t-b.unified_runtime_pointer.json",
        "t-dir.canonical_runtime.json",
        "t-link.canonical_runtime.json",
    ])
    assert copy_run_receipts_to_state_root(old_root) == []  # second run is a no-op
    assert sorted(p.name for p in (deploy.state / RUN).iterdir()) == [
        "t-a.canonical_runtime.json",
        "t-b.unified_runtime_pointer.json",
    ]
    found = find_run_receipt("t-b", deploy.next(), suffix=UNIFIED_RUNTIME_POINTER_SUFFIX)
    assert found == deploy.state / RUN / "t-b.unified_runtime_pointer.json"


def test_copy_from_state_root_or_missing_dir_is_noop(deploy: SimpleNamespace) -> None:
    assert copy_run_receipts_to_state_root(deploy.state) == []
    assert copy_run_receipts_to_state_root(deploy.tmp / "does-not-exist") == []
    assert CANONICAL_RUNTIME_SUFFIX == ".canonical_runtime.json"


# --- review round 1 (#2703): writer-order search, identity, binding, fresh state root ---


def _receipt(task_id: str, root_hash: str = "h-1", **extra: Any) -> str:
    return json.dumps({
        "task_id": task_id,
        "root_receipt": {"root_receipt_hash": root_hash},
        **extra,
    })


def test_isolated_root_finds_its_own_receipt_before_state_root(deploy: SimpleNamespace) -> None:
    canary = deploy.tmp / "canary-root"
    own = canary / RUN / "t-same.canonical_runtime.json"
    own.parent.mkdir(parents=True)
    own.write_text(_receipt("t-same", where="canary"), encoding="utf-8")
    shared = deploy.state / RUN / "t-same.canonical_runtime.json"
    shared.parent.mkdir(parents=True)
    shared.write_text(_receipt("t-same", where="state"), encoding="utf-8")
    assert run_receipt_path(canary, "t-same") == own  # the writer keeps the canary path
    assert find_run_receipt("t-same", canary) == own
    assert find_run_receipt("t-same", deploy.ws) == shared


@pytest.mark.parametrize(
    ("stored", "requested"),
    [("a_b", "a b"), ("task/1", "task:1"), ("x" * 120 + "A", "x" * 120 + "B")],
)
def test_name_collision_returns_only_the_matching_task(
    deploy: SimpleNamespace, stored: str, requested: str
) -> None:
    assert safe_receipt_name(stored) == safe_receipt_name(requested)
    path = run_receipt_path(deploy.ws, stored)
    path.parent.mkdir(parents=True)
    path.write_text(_receipt(stored), encoding="utf-8")
    assert find_run_receipt(stored, deploy.ws) == path
    assert find_run_receipt(requested, deploy.ws) is None


def test_mismatch_in_state_root_falls_through_to_matching_legacy_receipt(
    deploy: SimpleNamespace,
) -> None:
    shared = run_receipt_path(deploy.ws, "a b")
    shared.parent.mkdir(parents=True)
    shared.write_text(_receipt("a_b"), encoding="utf-8")  # collides, other task
    legacy = deploy.ws / RUN / "a_b.canonical_runtime.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(_receipt("a b"), encoding="utf-8")
    assert find_run_receipt("a b", deploy.ws) == legacy


@pytest.mark.parametrize("content", ["", "not json", "[1, 2]", '{"task_id": 7}', "{}"])
def test_unreadable_or_untagged_receipt_is_not_returned(
    deploy: SimpleNamespace, content: str
) -> None:
    path = run_receipt_path(deploy.ws, "7")
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    assert find_run_receipt("7", deploy.ws) is None


def test_binding_rejects_stale_receipt_of_same_task_id(deploy: SimpleNamespace) -> None:
    path = run_receipt_path(deploy.ws, "t-rerun")
    path.parent.mkdir(parents=True)
    path.write_text(_receipt("t-rerun", root_hash="hash-of-earlier-run"), encoding="utf-8")
    assert find_run_receipt("t-rerun", deploy.ws) == path
    assert (
        find_run_receipt("t-rerun", deploy.ws, expected_root_receipt_hash="hash-of-earlier-run")
        == path
    )
    assert (
        find_run_receipt("t-rerun", deploy.ws, expected_root_receipt_hash="hash-of-this-run")
        is None
    )
    assert find_run_receipt("t-rerun", deploy.ws, expected_root_receipt_hash="") is None
    path.write_text(json.dumps({"task_id": "t-rerun"}), encoding="utf-8")  # no root receipt
    assert (
        find_run_receipt("t-rerun", deploy.ws, expected_root_receipt_hash="hash-of-this-run")
        is None
    )
    assert find_run_receipt("t-rerun", deploy.ws, expected_root_receipt_hash="") is None


def test_fresh_state_root_written_by_real_runtime_writer(
    monkeypatch: pytest.MonkeyPatch, deploy: SimpleNamespace
) -> None:
    """No pre-created run dir; the fake gateway uses nexus-runtime's real receipt writer
    (``_write_receipt_atomic``) and does not mkdir itself."""
    from nexus_runtime.kernel.receipts import _write_receipt_atomic

    from nexus.engine.canonical_task_seam import execute_canonical_product_task

    assert not deploy.state.exists()

    class _Gateway:
        def __init__(self, project_root):
            self.project_root = project_root

        def ask_unified(self, request, **kwargs):
            receipt = {
                "task_id": request.task_id,
                "terminal_status": "SUCCEEDED",
                "receipt_complete": True,
                "canonical_execution": {"execution_decision_authority": "CapabilityPlanner"},
                "root_receipt": {
                    "schema": "nexus.root_receipt.v1",
                    "root_receipt_hash": "rh-fresh",
                },
            }
            _write_receipt_atomic(Path(kwargs["receipt_path"]), receipt)
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", _Gateway)
    monkeypatch.setattr("nexus.contracts.root_receipt.validate_root_receipt", lambda _r: (True, []))
    result = execute_canonical_product_task(
        "audit the bounded runtime",
        deploy.ws,
        execution_context={
            "task_id": "fresh-1",
            "workspace_revision": "rev-1",
            "local_assist_mode": "disabled",
            "online_policy": "auto",
        },
    )
    expected = deploy.state / RUN / "fresh-1.canonical_runtime.json"
    assert Path(result.receipt_path) == expected
    assert result.root_receipt_valid is True
    assert sorted(p.name for p in expected.parent.iterdir()) == [expected.name]  # no temp left
    deploy.next()
    assert find_run_receipt("fresh-1", deploy.ws, expected_root_receipt_hash="rh-fresh") == expected


def test_copy_temp_name_is_unique_per_call(
    deploy: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil as _shutil

    old_dir = deploy.tmp / "a1-old" / RUN
    old_dir.mkdir(parents=True)
    (old_dir / "t-u.canonical_runtime.json").write_text(_receipt("t-u"), encoding="utf-8")
    seen: list[str] = []
    real_copy = _shutil.copyfile

    def _spy(src, dst, *, follow_symlinks=True):
        seen.append(Path(dst).name)
        return real_copy(src, dst, follow_symlinks=follow_symlinks)

    monkeypatch.setattr("nexus.engine.run_receipt_store.shutil.copyfile", _spy)
    monkeypatch.setattr("nexus.engine.run_receipt_store.os.getpid", lambda: 1)
    copy_run_receipts_to_state_root(deploy.tmp / "a1-old")
    (deploy.state / RUN / "t-u.canonical_runtime.json").unlink()
    copy_run_receipts_to_state_root(deploy.tmp / "a1-old")
    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(re.fullmatch(r"\.t-u\.canonical_runtime\.json\.copy-[0-9a-f]{32}", n) for n in seen)
