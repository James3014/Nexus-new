"""G3: Linear Replay Runner

Minimal replay runner inspired by mini-SWE-agent:
- one candidate = one isolated subprocess
- fixed base_commit
- fixed source hash
- fixed verifier
- fixed artifact path
- no shared mutated state
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ReplayTask:
    """A replay task with fixed parameters."""
    task_id: str
    repo_dir: str
    base_commit: str
    target_file: str
    python_executable: str
    repro_script: str
    source_hash: str = ""
    anchor_text: str = ""
    replacement: str = ""


@dataclass
class ReplayResult:
    """Result of a single replay."""
    task_id: str
    base_commit: str
    source_hash_before: str
    source_hash_after: str
    verifier_passed: bool
    verifier_output: str
    patch_diff: str
    artifact_path: str
    status: str
    error: str = ""


class LinearReplayRunner:
    """Minimal replay runner with isolated execution."""

    def __init__(self, artifact_dir: str | Path):
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def run_single(
        self,
        task: ReplayTask,
        *,
        apply_fn: Callable[[str, str, str], tuple[bool, str]] | None = None,
        verify_fn: Callable[[str, str, str], tuple[bool, str]] | None = None,
    ) -> ReplayResult:
        """Run a single replay in isolation."""
        repo_dir = Path(task.repo_dir)
        artifact_path = self.artifact_dir / task.task_id
        artifact_path.mkdir(parents=True, exist_ok=True)

        # 1. Checkout to base_commit
        self._run_git(["checkout", "--", "."], repo_dir)
        self._run_git(["clean", "-fd"], repo_dir)
        self._run_git(["checkout", task.base_commit], repo_dir)

        # 2. Compute source hash
        source_text = (repo_dir / task.target_file).read_text(encoding="utf-8")
        source_hash_before = hashlib.sha256(source_text.encode()).hexdigest()[:16]

        # 3. Apply patch
        if apply_fn:
            apply_ok, apply_error = apply_fn(
                task.replacement, task.anchor_text, str(repo_dir / task.target_file)
            )
            if not apply_ok:
                return ReplayResult(
                    task_id=task.task_id,
                    base_commit=task.base_commit,
                    source_hash_before=source_hash_before,
                    source_hash_after=source_hash_before,
                    verifier_passed=False,
                    verifier_output="",
                    patch_diff="",
                    artifact_path=str(artifact_path),
                    status="REPLAY_APPLY_FAILED",
                    error=apply_error,
                )

        # 4. Compute source hash after
        source_text_after = (repo_dir / task.target_file).read_text(encoding="utf-8")
        source_hash_after = hashlib.sha256(source_text_after.encode()).hexdigest()[:16]

        # 5. Run verifier
        if verify_fn:
            verify_ok, verify_output = verify_fn(
                task.repro_script, task.python_executable, str(repo_dir)
            )
        else:
            verify_ok, verify_output = self._run_repro(
                task.repro_script, task.python_executable, repo_dir
            )

        # 6. Capture diff
        diff_result = self._run_git(
            ["diff", task.target_file], repo_dir
        )
        patch_diff = diff_result.stdout if diff_result.returncode == 0 else ""

        # 7. Save artifacts
        (artifact_path / "source_hash_before.txt").write_text(source_hash_before)
        (artifact_path / "source_hash_after.txt").write_text(source_hash_after)
        (artifact_path / "verifier_output.txt").write_text(verify_output)
        (artifact_path / "patch.diff").write_text(patch_diff)
        (artifact_path / "replay_result.json").write_text(json.dumps({
            "task_id": task.task_id,
            "base_commit": task.base_commit,
            "source_hash_before": source_hash_before,
            "source_hash_after": source_hash_after,
            "verifier_passed": verify_ok,
            "status": "REPLAY_SUCCESS" if verify_ok else "REPLAY_VERIFIER_FAILED",
        }, indent=2))

        # 8. Restore workspace
        self._run_git(["checkout", "--", "."], repo_dir)
        self._run_git(["clean", "-fd"], repo_dir)

        return ReplayResult(
            task_id=task.task_id,
            base_commit=task.base_commit,
            source_hash_before=source_hash_before,
            source_hash_after=source_hash_after,
            verifier_passed=verify_ok,
            verifier_output=verify_output,
            patch_diff=patch_diff,
            artifact_path=str(artifact_path),
            status="REPLAY_SUCCESS" if verify_ok else "REPLAY_VERIFIER_FAILED",
        )

    def run_batch(
        self,
        tasks: list[ReplayTask],
        **kwargs,
    ) -> list[ReplayResult]:
        """Run multiple replays sequentially."""
        results = []
        for task in tasks:
            result = self.run_single(task, **kwargs)
            results.append(result)
        return results

    @staticmethod
    def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _run_repro(
        repro_script: str, python_exe: str, repo_dir: Path
    ) -> tuple[bool, str]:
        """Run reproduction script."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp"
        ) as f:
            f.write(repro_script)
            script_path = f.name
        try:
            res = subprocess.run(
                [python_exe, script_path],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            return res.returncode == 0, output
        except Exception as e:
            return False, f"REPRO_ERROR: {e}"
        finally:
            Path(script_path).unlink(missing_ok=True)
