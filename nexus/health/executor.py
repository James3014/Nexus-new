from __future__ import annotations

import os
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import yaml

from .models import RepairExecutionResult, RepairPlan
from .sandbox import SpeculativeSandbox


class RepairExecutor:
    def __init__(
        self,
        repo_root: Path,
        task_runner: Optional[Callable[[Path], int]] = None,
        safe_action_timeout_sec: int = 120,
        task_runner_timeout_sec: int = 180,
        sandbox_timeout_sec: int = 180,
        sandbox_enabled: bool = True,
        total_timeout_sec: Optional[int] = None,
    ):
        self.repo_root = Path(repo_root)
        self._custom_task_runner = task_runner
        self.task_runner = task_runner or self._default_task_runner
        self.safe_action_timeout_sec = max(10, int(safe_action_timeout_sec))
        self.task_runner_timeout_sec = max(30, int(task_runner_timeout_sec))
        self.sandbox_timeout_sec = min(180, max(30, int(sandbox_timeout_sec)))
        self.sandbox_enabled = bool(sandbox_enabled)
        self.total_timeout_sec = (
            max(30, int(total_timeout_sec))
            if total_timeout_sec is not None
            else None
        )
        self._last_sandbox_report: dict[str, object] = {}

    def execute(self, plan: RepairPlan) -> RepairExecutionResult:
        if not plan.actions:
            return RepairExecutionResult(disposition="noop", success=True, notes=["no_actions"])

        safe_actions = [action for action in plan.actions if action.disposition == "safe_execute"]
        manual_actions = [action for action in plan.actions if action.disposition == "inject_only"]

        executed_actions: list[str] = []
        notes: list[str] = []
        manifest_path: Path | None = None
        task_runner_invoked = False
        return_codes: dict[str, int] = {}
        telemetry: dict[str, object] = {"sandbox_attempted": False, "sandbox_passed": None, "sandbox_report": self._last_sandbox_report}
        success = True
        started_at = time.monotonic()

        def remaining_budget() -> Optional[int]:
            if self.total_timeout_sec is None:
                return None
            elapsed = int(time.monotonic() - started_at)
            return max(0, self.total_timeout_sec - elapsed)

        for action in safe_actions:
            budget = remaining_budget()
            if budget is not None and budget <= 0:
                notes.append("execution_budget_exhausted_before_safe_actions")
                success = False
                break
            try:
                proc = subprocess.run(
                    action.run,
                    shell=True,
                    cwd=self.repo_root,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.safe_action_timeout_sec,
                )
            except subprocess.TimeoutExpired:
                executed_actions.append(action.id)
                return_codes[action.id] = 124
                notes.append(f"executed:{action.id}:rc=124:timeout={self.safe_action_timeout_sec}s")
                success = False
                continue
            executed_actions.append(action.id)
            return_codes[action.id] = proc.returncode
            notes.append(f"executed:{action.id}:rc={proc.returncode}")
            if proc.returncode != 0:
                success = False

        if manual_actions:
            budget = remaining_budget()
            if budget is not None and budget <= 0:
                notes.append("execution_budget_exhausted_before_task_runner")
                success = False
                return RepairExecutionResult(
                    disposition="inject_only",
                    executed_actions=executed_actions,
                    injected_tasks=[action.id for action in manual_actions],
                    manifest_path=manifest_path,
                    task_runner_invoked=False,
                    success=success,
                    return_codes=return_codes,
                    notes=notes,
                    telemetry=telemetry,
                )

            if self.sandbox_enabled:
                telemetry["sandbox_attempted"] = True
                sandbox_rc, sandbox_note = self._validate_in_sandbox(manual_actions, timeout_sec=budget)
                return_codes["sandbox_task_runner"] = sandbox_rc
                notes.append(sandbox_note)
                if sandbox_rc != 0:
                    telemetry["sandbox_passed"] = False
                    telemetry["sandbox_hit_rate"] = 0.0
                    success = False
                    notes.append("sandbox_validation_failed")
                    return RepairExecutionResult(
                        disposition="inject_only",
                        executed_actions=executed_actions,
                        injected_tasks=[action.id for action in manual_actions],
                        manifest_path=None,
                        task_runner_invoked=False,
                        success=False,
                        return_codes=return_codes,
                        notes=notes,
                        telemetry=telemetry,
                    )
                telemetry["sandbox_passed"] = True
                telemetry["sandbox_hit_rate"] = 1.0

            manifest_path = self._write_manifest(manual_actions)
            rc = self._run_task_runner(manifest_path, timeout_sec=budget)
            task_runner_invoked = True
            return_codes["task_runner"] = rc
            success = success and rc == 0
            notes.append(f"task_runner_rc:{rc}")
            evidence_path = self._write_evidence_json(return_codes, notes, telemetry)
            notes.append(f"evidence:{evidence_path}")
            return RepairExecutionResult(
                disposition="inject_only",
                executed_actions=executed_actions,
                injected_tasks=[action.id for action in manual_actions],
                manifest_path=manifest_path,
                task_runner_invoked=task_runner_invoked,
                success=success,
                return_codes=return_codes,
                notes=notes,
                telemetry=telemetry,
            )

        return RepairExecutionResult(
            disposition="safe_execute",
            executed_actions=executed_actions,
            manifest_path=manifest_path,
            task_runner_invoked=task_runner_invoked,
            success=success,
            return_codes=return_codes,
            notes=notes,
            telemetry=telemetry,
        )

    def _write_manifest(self, actions, root: Optional[Path] = None) -> Path:
        manifest_root = Path(root) if root is not None else self.repo_root / ".nexus" / "records" / "auto-repair"
        manifest_root.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="nexus-auto-repair-", suffix=".yaml", dir=str(manifest_root))
        os.close(fd)
        manifest_path = Path(temp_path)
        tasks = []
        prev_id = None
        for action in actions:
            task = {
                "id": action.id,
                "description": f"AUTO-REPAIR: {action.reason}",
                "run": action.run,
                "priority": action.priority,
                "depends_on": [prev_id] if prev_id else [],
                "completion_gate": {
                    "task_level": "small_fix",
                    "verify_commands": action.verify_commands,
                    "artifact_paths": action.artifact_paths,
                    "output_dir": str(manifest_root / "logs" / "delivery"),
                },
            }
            tasks.append(task)
            prev_id = action.id

        manifest = {
            "defaults": {
                "require_completion_gate": True,
                "max_parallel": 1,
            },
            "tasks": tasks,
        }
        manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return manifest_path

    def _run_task_runner(self, manifest_path: Path, timeout_sec: Optional[int] = None) -> int:
        return self._run_task_runner_with_cwd(manifest_path, cwd=self.repo_root, timeout_sec=timeout_sec)

    def _run_task_runner_with_cwd(
        self,
        manifest_path: Path,
        cwd: Path,
        timeout_sec: Optional[int] = None,
    ) -> int:
        if self._custom_task_runner is not None:
            try:
                return self._custom_task_runner(manifest_path)
            except TypeError:
                # Backward compatibility with custom runners that only accept manifest path.
                return self._custom_task_runner(manifest_path)
        return self._default_task_runner(manifest_path, timeout_sec=timeout_sec, cwd=cwd)

    def _default_task_runner(
        self,
        manifest_path: Path,
        timeout_sec: Optional[int] = None,
        cwd: Optional[Path] = None,
    ) -> int:
        run_root = Path(cwd) if cwd is not None else self.repo_root
        runner = run_root / "scripts" / "ops" / "task_runner.py"
        env = os.environ.copy()
        env["MANIFEST"] = str(manifest_path)
        timeout_to_use = self.task_runner_timeout_sec
        if timeout_sec is not None:
            timeout_to_use = max(5, min(timeout_to_use, int(timeout_sec)))
        try:
            proc = subprocess.run(
                [str(run_root / ".venv" / "bin" / "python"), str(runner), "--delivery-mode", "high"],
                cwd=run_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_to_use,
            )
            return proc.returncode
        except subprocess.TimeoutExpired:
            return 124

    def _validate_in_sandbox(self, actions, timeout_sec: Optional[int] = None) -> tuple[int, str]:
        sandbox = SpeculativeSandbox(self.repo_root, mode="auto")
        sandbox_root: Path | None = None
        try:
            sandbox_root = sandbox.fork()
            sandbox_manifest = self._write_manifest(actions, root=sandbox_root)
            timeout_to_use = self.sandbox_timeout_sec
            if timeout_sec is not None:
                timeout_to_use = max(5, min(timeout_to_use, int(timeout_sec)))
            rc = self._run_task_runner_with_cwd(
                sandbox_manifest,
                cwd=sandbox_root,
                timeout_sec=timeout_to_use,
            )
            return rc, f"sandbox_task_runner_rc:{rc}"
        except Exception as exc:
            return 1, f"sandbox_error:{type(exc).__name__}:{exc}"
        finally:
            if sandbox_root:
                sandbox.cleanup()
            self._last_sandbox_report = sandbox.sandbox_report

    def _write_evidence_json(self, return_codes: dict[str, int], notes: list[str], telemetry: dict[str, object]) -> Path:
        evidence_dir = self.repo_root / ".nexus" / "runs" / "latest"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / "evidence.json"
        payload = {
            "return_codes": return_codes,
            "notes": notes,
            "telemetry": telemetry,
            "ts": int(time.time()),
        }
        evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return evidence_path
