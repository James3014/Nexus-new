"""#2477: start-phase blocks before spawn when the pool provably does not serve the model."""

from __future__ import annotations

import hashlib
import json
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pc = SourceFileLoader(
    "nexus_dsh_phase_chain_helpers_for_model_served",
    str(Path(__file__).resolve().with_name("test_nexus_dsh_phase_chain.py")),
).load_module()
guard = pc.guard

UNSERVED_PATCH = """- id: agent-default-model
  config:
    provider: nexus-agy-pool
    model: gemini-3.1-pro-high
    reasoningEffort: high
"""
SERVED_PATCH = UNSERVED_PATCH.replace("gemini-3.1-pro-high", "gemini-3.8-flash-high")
SERVED = ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "claude-sonnet-4-6"]


@pytest.fixture
def tmp_path(dsh_non_temp_path: Path) -> Path:
    return dsh_non_temp_path


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
    return root


def _start(tmp_path: Path, patch_text: str):
    ctx = pc._setup(tmp_path)
    patch = tmp_path / "session.patch.yml"
    patch.write_text(patch_text, encoding="utf-8")
    proc = pc._start(ctx, [{"session": "s-1"}], "--patch", str(patch))
    return ctx, proc


def test_unserved_model_blocks_before_spawn(tmp_path: Path, ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED)
    _catalog(ops_root, "b", SERVED[:1])
    ctx, proc = _start(tmp_path, UNSERVED_PATCH)
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["reason_code"] == "SESSION_MODEL_NOT_SERVED"
    assert "gemini-3.1-pro-high" in out["detail"]
    assert "gemini-3.8-flash-high" in out["detail"]  # names the served alternatives
    assert pc._calls(ctx) == []  # DSH was never spawned


def test_served_model_passes(tmp_path: Path, ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED)
    ctx, proc = _start(tmp_path, SERVED_PATCH)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(pc._calls(ctx)) == 1


def test_no_catalog_keeps_todays_behaviour(tmp_path: Path, ops_root: Path) -> None:
    ctx, proc = _start(tmp_path, UNSERVED_PATCH)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(pc._calls(ctx)) == 1


def test_stale_catalog_keeps_todays_behaviour(tmp_path: Path, ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED, age=100000.0)
    ctx, proc = _start(tmp_path, UNSERVED_PATCH)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(pc._calls(ctx)) == 1


def test_model_listed_only_by_a_stale_catalog_is_not_blocked(
    tmp_path: Path, ops_root: Path
) -> None:
    _catalog(ops_root, "fresh", SERVED)
    _catalog(ops_root, "stale", [*SERVED, "gemini-3.1-pro-high"], age=100000.0)
    ctx, proc = _start(tmp_path, UNSERVED_PATCH)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_corrupt_catalog_is_ignored_fail_open(tmp_path: Path, ops_root: Path) -> None:
    (ops_root / "model-catalog").mkdir()
    (ops_root / "model-catalog" / "x.json").write_text("{not json", encoding="utf-8")
    ctx, proc = _start(tmp_path, UNSERVED_PATCH)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_skip_env_bypasses_the_check(tmp_path: Path, ops_root: Path, monkeypatch) -> None:
    _catalog(ops_root, "a", SERVED)
    monkeypatch.setenv("NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK", "1")
    ctx, proc = _start(tmp_path, UNSERVED_PATCH)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_non_agy_provider_is_not_checked(tmp_path: Path, ops_root: Path) -> None:
    _catalog(ops_root, "a", SERVED)
    ctx, proc = _start(tmp_path, UNSERVED_PATCH.replace("nexus-agy-pool", "other-provider"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
