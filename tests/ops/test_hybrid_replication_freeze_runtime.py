from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

import scripts.ops.hybrid_replication_freeze_runtime as freeze
from nexus.research.hybrid_replication_live import (
    _expected_agy_dispatch_sha256,
    resolve_canonical_agy_dispatch_path,
)

GENERATION = "AGY_GEMINI_3_8_FLASH_MEDIUM_V11"
DISPATCH_BODY = "#!/bin/sh\necho frozen-dispatcher\n"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.fixture
def source_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    dispatcher = repo / "scripts" / "ops" / "nexus-agy-dispatch"
    dispatcher.parent.mkdir(parents=True)
    dispatcher.write_text(DISPATCH_BODY, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo, _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def base_binding(tmp_path: Path) -> Path:
    path = tmp_path / "base_binding.json"
    path.write_text(
        json.dumps(
            {
                "schema": "nexus.hybrid_replication.live_binding.v1",
                "activation_state": "AUTOMATIC_CAPTURE_READY",
                "agy_dispatch_path": "/stale/top/nexus-agy-dispatch",
                "agy_dispatch_sha256": "0" * 64,
                "agy": {
                    "dispatch_path": "/stale/agy/nexus-agy-dispatch",
                    "dispatch_sha256": "1" * 64,
                    "keep": "me",
                },
                "strong_online": {
                    "provider": "codex",
                    "requested_model": "model-x",
                    "previous_execution_generation": "AGY_OLD_V10",
                },
                "jev": {"requested_model": "jev"},
            }
        ),
        encoding="utf-8",
    )
    return path


def _args(
    repo: Path,
    revision: str,
    live_root: Path,
    base: Path,
    output: Path,
    *,
    generation: str = GENERATION,
    extra: tuple[str, ...] = (),
) -> list[str]:
    return [
        "--source-repo",
        str(repo),
        "--revision",
        revision,
        "--live-root",
        str(live_root),
        "--generation",
        generation,
        "--base-binding",
        str(base),
        "--output-binding",
        str(output),
        *extra,
    ]


def test_freeze_creates_worktree_pin_and_binding(
    tmp_path: Path,
    source_repo: tuple[Path, str],
    base_binding: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, revision = source_repo
    live_root = tmp_path / "live"
    output = tmp_path / "out" / "binding.json"

    assert freeze.main(_args(repo, revision, live_root, base_binding, output)) == 0
    receipt = json.loads(capsys.readouterr().out)

    runtime = live_root / "runtime" / revision
    assert _git(runtime, "rev-parse", "HEAD") == revision
    pin = live_root / "runtime-pins" / GENERATION / "nexus-agy-dispatch"
    expected_sha = hashlib.sha256(DISPATCH_BODY.encode()).hexdigest()
    assert pin.read_text(encoding="utf-8") == DISPATCH_BODY
    assert stat.S_IMODE(pin.stat().st_mode) == 0o555
    assert not os.access(pin, os.W_OK) or os.geteuid() == 0

    assert receipt["schema"] == "nexus.hybrid_replication.runtime_freeze.v1"
    assert receipt["revision"] == revision
    assert receipt["generation"] == GENERATION
    assert receipt["runtime_root"] == str(runtime)
    assert receipt["dispatcher_pin_path"] == str(pin)
    assert receipt["dispatcher_sha256"] == expected_sha
    assert receipt["output_binding"] == str(output.resolve())
    assert receipt["output_binding_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["reused"] == {"worktree": False, "pin": False}

    binding: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
    online = binding["strong_online"]
    assert online["provider"] == "agy"
    assert online["agy_dispatch_path"] == str(pin)
    assert online["agy_dispatch_sha256"] == expected_sha
    assert online["execution_generation"] == GENERATION
    assert online["requested_model"] == "model-x"
    assert binding["source_revision"] == revision
    assert binding["runtime_root"] == str(runtime)
    assert binding["activation_state"] == "NOT_READY"
    assert "agy_dispatch_path" not in binding
    assert "agy_dispatch_sha256" not in binding
    assert binding["agy"] == {"keep": "me"}

    assert _expected_agy_dispatch_sha256(binding) == expected_sha
    assert resolve_canonical_agy_dispatch_path(binding) == pin


def test_rerun_reuses_worktree_and_pin(
    tmp_path: Path,
    source_repo: tuple[Path, str],
    base_binding: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, revision = source_repo
    live_root = tmp_path / "live"
    assert freeze.main(_args(repo, revision, live_root, base_binding, tmp_path / "a.json")) == 0
    capsys.readouterr()
    assert freeze.main(_args(repo, revision, live_root, base_binding, tmp_path / "b.json")) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["reused"] == {"worktree": True, "pin": True}
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_existing_output_is_refused_and_untouched(
    tmp_path: Path, source_repo: tuple[Path, str], base_binding: Path
) -> None:
    repo, revision = source_repo
    output = tmp_path / "binding.json"
    output.write_text("original", encoding="utf-8")
    code = freeze.main(_args(repo, revision, tmp_path / "live", base_binding, output))
    assert code == 2
    assert output.read_text(encoding="utf-8") == "original"
    assert not (tmp_path / "live").exists()


def test_pin_collision_with_different_content_exits_2(
    tmp_path: Path, source_repo: tuple[Path, str], base_binding: Path
) -> None:
    repo, revision = source_repo
    live_root = tmp_path / "live"
    pin = live_root / "runtime-pins" / GENERATION / "nexus-agy-dispatch"
    pin.parent.mkdir(parents=True)
    pin.write_text("different", encoding="utf-8")
    output = tmp_path / "binding.json"
    assert freeze.main(_args(repo, revision, live_root, base_binding, output)) == 2
    assert pin.read_text(encoding="utf-8") == "different"
    assert not output.exists()


def test_runtime_dir_at_other_head_exits_2(
    tmp_path: Path, source_repo: tuple[Path, str], base_binding: Path
) -> None:
    repo, revision = source_repo
    live_root = tmp_path / "live"
    runtime = live_root / "runtime" / revision
    runtime.mkdir(parents=True)
    assert (
        freeze.main(_args(repo, revision, live_root, base_binding, tmp_path / "binding.json")) == 2
    )


@pytest.mark.parametrize("generation", ["V11", "AGY_lower_V1", "AGY_X", "AGY_X_V"])
def test_bad_generation_is_rejected(
    tmp_path: Path, source_repo: tuple[Path, str], base_binding: Path, generation: str
) -> None:
    repo, revision = source_repo
    output = tmp_path / "binding.json"
    code = freeze.main(
        _args(repo, revision, tmp_path / "live", base_binding, output, generation=generation)
    )
    assert code == 1
    assert not output.exists()
    assert not (tmp_path / "live").exists()


@pytest.mark.parametrize("revision", ["HEAD", "abc123", "A" * 40, "0" * 40])
def test_bad_revision_is_rejected(
    tmp_path: Path, source_repo: tuple[Path, str], base_binding: Path, revision: str
) -> None:
    repo, _ = source_repo
    output = tmp_path / "binding.json"
    assert freeze.main(_args(repo, revision, tmp_path / "live", base_binding, output)) == 1
    assert not output.exists()
    assert not (tmp_path / "live").exists()


def test_dry_run_prints_plan_and_touches_nothing(
    tmp_path: Path,
    source_repo: tuple[Path, str],
    base_binding: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, revision = source_repo
    live_root = tmp_path / "live"
    output = tmp_path / "binding.json"
    code = freeze.main(_args(repo, revision, live_root, base_binding, output, extra=("--dry-run",)))
    assert code == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["revision"] == revision
    assert receipt["dispatcher_sha256"] == hashlib.sha256(DISPATCH_BODY.encode()).hexdigest()
    assert receipt["reused"] == {"worktree": False, "pin": False}
    assert not live_root.exists()
    assert not output.exists()
    assert _git(repo, "worktree", "list").count("\n") == 0
