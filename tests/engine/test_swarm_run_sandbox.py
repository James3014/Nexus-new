"""swarm_run verifies model-written code only inside the shared OS sandbox.

Passes on every platform: without an OS barrier the tests assert that nothing is executed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nexus.engine import sandboxed_lane as lane
from nexus.engine import swarm_run
from nexus.engine.sandboxed_lane import os_sandbox_available

FIXTURE = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "wiring_fixtures" / "swarm"


def _repo(tmp_path: Path) -> Path:
    ws = tmp_path / "swarm"
    shutil.copytree(FIXTURE, ws)
    os.symlink("calc.py", ws / "link.py")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
    subprocess.run([*git, "add", "-A"], cwd=ws, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "fixture"], cwd=ws, check=True)
    return ws


@pytest.fixture
def stub_worker(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import nexus.research.sprint_service as sprint

    calls: list[str] = []

    class _StubWorker:
        """Stands in for the local-model worker: writes the known fix (no model call)."""

        def __init__(self, project_root: Path, **_kw: Any) -> None:
            self.root = Path(project_root)

        def generate(self, *, source_code: str, **_kw: Any) -> tuple[str, dict[str, Any]]:
            calls.append(str(self.root))
            return source_code.replace("a - b", "a + b"), {"model_calls": 0}

    monkeypatch.setattr(sprint, "LocalArmorCandidateGenerator", _StubWorker)
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "/nonexistent-state")
    return calls


@pytest.mark.parametrize(
    ("target_file", "verify_script", "field"),
    [
        ("-x", "repro.py", "target_file"),
        ("../y.py", "repro.py", "target_file"),
        ("/etc/hosts", "repro.py", "target_file"),
        (".git/config", "repro.py", "target_file"),
        ("calc.py", "-c", "verify_script"),
        ("calc.py", "../repro.py", "verify_script"),
    ],
)
def test_unsafe_target_or_verify_path_blocks_before_any_worktree(
    tmp_path: Path, stub_worker: list[str], target_file: str, verify_script: str, field: str
) -> None:
    ws = _repo(tmp_path)
    report = swarm_run.run_bounded_swarm(
        workspace_root=ws,
        task_id="t",
        task="fix",
        target_file=target_file,
        verify_script=verify_script,
    )
    assert (report["status"], report["reason"]) == ("BLOCKED", f"UNSAFE_PATH:{field}")
    assert not (ws / ".nexus").exists()
    assert stub_worker == []


def test_symlinked_target_file_is_never_read_or_written(
    tmp_path: Path, stub_worker: list[str]
) -> None:
    ws = _repo(tmp_path)
    report = swarm_run.run_bounded_swarm(
        workspace_root=ws, task_id="t", task="fix", target_file="link.py", verify_script="repro.py"
    )
    assert (report["status"], report["reason"]) == ("FAILED", "NO_VERIFIED_WORKER")
    assert {w["worker_status"] for w in report["workers"]} == {"unsafe_path"}
    assert stub_worker == []
    assert "a - b" in (ws / "calc.py").read_text(encoding="utf-8")


def test_no_os_barrier_never_runs_the_verify_script(
    tmp_path: Path, stub_worker: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")
    ws = _repo(tmp_path)
    seen: list[list[str]] = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append([str(part) for part in argv])
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    # Confinement.run goes through the process-group reaping runner (#3052): watched too.
    monkeypatch.setattr(lane, "run_reaping_process_group", spy)
    report = swarm_run.run_bounded_swarm(
        workspace_root=ws, task_id="t", task="fix", target_file="calc.py", verify_script="repro.py"
    )
    assert (report["status"], report["reason"]) == ("FAILED", "NO_VERIFIED_WORKER")
    assert [w["verify_result"] for w in report["workers"]] == [
        swarm_run.NOT_EXECUTED_NO_BARRIER
    ] * 2
    assert not any(argv and argv[0] in {sys.executable, "python3", "python"} for argv in seen)
    assert not any("repro.py" in " ".join(argv) for argv in seen)


def test_verify_script_runs_confined_when_a_barrier_exists(
    tmp_path: Path, stub_worker: list[str]
) -> None:
    ws = _repo(tmp_path)
    report = swarm_run.run_bounded_swarm(
        workspace_root=ws, task_id="t", task="fix", target_file="calc.py", verify_script="repro.py"
    )
    workers = report["workers"]
    if not os_sandbox_available():
        assert [w["verify_result"] for w in workers] == [swarm_run.NOT_EXECUTED_NO_BARRIER] * 2
        return
    assert [w["verify_result"] for w in workers] == ["pass", "pass"]
    assert all(w["isolation"]["barrier"] == "macos_sandbox_exec" for w in workers)
    assert all(w["verify_exit_codes"] == [0] for w in workers)
