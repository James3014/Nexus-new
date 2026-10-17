"""#2477: start-phase blocks before spawn when the pool provably does not serve the model.

These tests call the guard functions directly (no DSH child, no non-temp workspace), so
they also run in the trusted impact executor, where the end-to-end start-phase suites skip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
guard = SourceFileLoader(
    "nexus_dsh_workflow_model_served_test", str(ROOT / "scripts" / "ops" / "nexus-dsh-workflow")
).load_module()

UNSERVED_PATCH = """- id: agent-default-model
  config:
    provider: nexus-agy-pool
    model: gemini-3.1-pro-high
    reasoningEffort: high
"""
SERVED_PATCH = UNSERVED_PATCH.replace("gemini-3.1-pro-high", "gemini-3.8-flash-high")
SERVED = ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "claude-sonnet-4-6"]
MODEL = "gemini-3.1-pro-high"


def _catalog(root: Path, name: str, ids: list[str], age: float = 10.0) -> None:
    directory = root / "model-catalog"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "ids": ids,
        "checked_at_epoch": time.time() - age,
        "catalog_sha256": hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest(),
    }
    (directory / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def ops_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "agy-ops"
    root.mkdir()
    monkeypatch.setenv("NEXUS_AGY_OPERATION_ROOT", str(root))
    monkeypatch.delenv("NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK", raising=False)
    monkeypatch.delenv("NEXUS_AGY_MODEL_CATALOG_TTL_SEC", raising=False)
    return root


def test_unserved_model_is_reported_with_served_alternatives(ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED)
    _catalog(ops_root, "b", SERVED[:1])
    result = guard.check_model_served(MODEL)
    assert result is not None
    assert result["model"] == MODEL
    assert result["served_models"] == sorted(SERVED)


def test_served_model_passes(ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED)
    assert guard.check_model_served("gemini-3.8-flash-high") is None


def test_no_catalog_keeps_todays_behaviour(ops_root: Path) -> None:
    assert guard.check_model_served(MODEL) is None


def test_stale_catalog_keeps_todays_behaviour(ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED, age=100000.0)
    assert guard.check_model_served(MODEL) is None


def test_model_listed_only_by_a_stale_catalog_is_not_blocked(ops_root: Path) -> None:
    _catalog(ops_root, "fresh", SERVED)
    _catalog(ops_root, "stale", [*SERVED, MODEL], age=100000.0)
    assert guard.check_model_served(MODEL) is None


def test_corrupt_catalog_is_ignored_fail_open(ops_root: Path) -> None:
    (ops_root / "model-catalog").mkdir()
    (ops_root / "model-catalog" / "x.json").write_text("{not json", encoding="utf-8")
    assert guard.check_model_served(MODEL) is None


def test_catalog_with_wrong_digest_is_ignored(ops_root: Path) -> None:
    _catalog(ops_root, "fresh", SERVED)
    _catalog(ops_root, "forged", [*SERVED, MODEL])
    path = ops_root / "model-catalog" / "forged.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["catalog_sha256"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    assert guard.check_model_served(MODEL) is not None


def test_skip_env_bypasses_the_check(ops_root: Path, monkeypatch) -> None:
    _catalog(ops_root, "a", SERVED)
    monkeypatch.setenv("NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK", "1")
    assert guard.check_model_served(MODEL) is None


class _Spawned(Exception):
    pass


def _turn(tmp_path: Path, monkeypatch, patch_text: str):
    patch = tmp_path / "session.patch.yml"
    patch.write_text(patch_text, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    monkeypatch.setattr(guard, "find_dirty_sibling", lambda *a, **k: None)
    monkeypatch.setattr(guard, "git_metadata_contract", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(guard, "_worktree_snapshot", lambda *a, **k: {})
    monkeypatch.setattr(
        guard,
        "run_issue_preflight",
        lambda subject, **k: {
            **subject,
            "decision": "ALLOW_RESUME",
            "generated_at": "2026-10-17T00:00:00Z",
        },
    )

    def _spawn(*a, **k):
        raise _Spawned

    monkeypatch.setattr(guard.subprocess, "run", _spawn)
    args = argparse.Namespace(
        issue=2477,
        goal_objective=None,
        patch=[str(patch)],
        dsh_bin="dsh",
        profile="p",
        doctor_bin="doctor",
    )
    return guard._run_phase_turn(
        args,
        tmp_path / "state",
        repository="James3014/Nexus-new",
        repo_root=repo,
        dsh_home=tmp_path / "home",
        phase="green",
        contract_text="CONTRACT",
        prior=[],
        parent=None,
        green_gate_command=None,
    )


def test_unserved_session_model_blocks_before_spawn(
    tmp_path: Path, ops_root: Path, monkeypatch
) -> None:
    _catalog(ops_root, "a", SERVED)
    code, payload = _turn(tmp_path, monkeypatch, UNSERVED_PATCH)  # _Spawned would escape
    assert code == guard.EXIT_BLOCKED
    assert payload["reason_code"] == "SESSION_MODEL_NOT_SERVED"
    assert MODEL in payload["detail"]
    assert "gemini-3.8-flash-high" in payload["detail"]
    assert payload["provider_invocation_allowed"] is False


def test_served_session_model_reaches_spawn(tmp_path: Path, ops_root: Path, monkeypatch) -> None:
    _catalog(ops_root, "a", SERVED)
    with pytest.raises(_Spawned):
        _turn(tmp_path, monkeypatch, SERVED_PATCH)


def test_no_catalog_reaches_spawn(tmp_path: Path, ops_root: Path, monkeypatch) -> None:
    with pytest.raises(_Spawned):
        _turn(tmp_path, monkeypatch, UNSERVED_PATCH)


def test_non_agy_provider_is_not_checked(tmp_path: Path, ops_root: Path, monkeypatch) -> None:
    _catalog(ops_root, "a", SERVED)
    with pytest.raises(_Spawned):
        _turn(tmp_path, monkeypatch, UNSERVED_PATCH.replace("nexus-agy-pool", "other-provider"))
