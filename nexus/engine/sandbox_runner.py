from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import subprocess
import shutil
import logging
import time
import os
import json
import uuid
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

@dataclass
class ChallengeReport:
    repo_url: str
    challenge_task: str
    success: bool
    phases_completed: List[str]
    phantom_triggers: int
    duration_sec: float

class SandboxRunner:
    """🧬 Nexus v4.0: 陌生工程生存挑戰器
    職責：在隔離環境中對陌生專案執行 Nexus Pipeline，驗證治理鏈魯棒性。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.sandbox_base = project_root / ".nexus" / "sandbox"
        self.sandbox_base.mkdir(parents=True, exist_ok=True)

        # 偵測 macOS 特有的 sandbox-exec 是否可用
        self.has_sandbox_exec = False
        if sys.platform == "darwin":
            try:
                res = subprocess.run(
                    ["sandbox-exec", "-p", "(version 1) (allow default)", "true"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False
                )
                self.has_sandbox_exec = res.returncode == 0
            except Exception:
                self.has_sandbox_exec = False

    def _copy_workspace(self, workspace_path: Path) -> None:
        ignored_names = {
            ".git",
            ".nexus",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
            "htmlcov",
            "build",
            "dist",
        }

        def ignore(_directory: str, names: list[str]) -> set[str]:
            directory_path = Path(_directory)
            return {
                name
                for name in names
                if name in ignored_names
                or name.endswith(".pyc")
                or (directory_path / name).is_symlink()
            }

        shutil.copytree(self.project_root, workspace_path, ignore=ignore)

    def _failure_result(
        self,
        *,
        task: str,
        command: list[str],
        run_id: str,
        run_dir: Path,
        workspace_path: Path,
        cwd: str | Path,
        output_file: str | Path | None,
        cleanup: bool,
        error: str,
        exit_code: int = 126,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        duration_sec: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "schema": "nexus.sandbox_run_task.v1",
            "task": task,
            "success": False,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "duration_sec": duration_sec,
            "command": command,
            "cwd": str(cwd),
            "workspace_source": "local_project_copy",
            "workspace_path": str(workspace_path),
            "run_id": run_id,
            "report_path": str(run_dir / "sandbox_result.json"),
            "output_file": str(output_file) if output_file else None,
            "output_artifact_path": None,
            "cleanup": cleanup,
            "error": error,
            "network_allowed": False,
            "hook_policy": {
                "source_git_metadata_copied": False,
                "git_hooks_copied": False,
                "git_hooks_allowed": False,
            },
        }

    def _write_result(self, run_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
        report_path = run_dir / "sandbox_result.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        result["report_path"] = str(report_path)
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return result

    def _write_python_network_guard(self, run_dir: Path) -> Path:
        guard_dir = run_dir / "python_network_guard"
        guard_dir.mkdir(parents=True, exist_ok=True)
        (guard_dir / "sitecustomize.py").write_text(
            """
from __future__ import annotations

import ipaddress
import socket

_original_create_connection = socket.create_connection
_original_socket_connect = socket.socket.connect


def _is_loopback_host(host: object) -> bool:
    host_text = str(host)
    if host_text in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host_text).is_loopback
    except ValueError:
        return False


def _blocked_error(address: object) -> RuntimeError:
    try:
        host, port = address[:2]
    except Exception:
        host, port = address, "?"
    return RuntimeError(f"Nexus sandbox blocked external network host: {host}:{port}")


def _check_address(address: object) -> None:
    try:
        host = address[0]
    except Exception:
        host = address
    if not _is_loopback_host(host):
        raise _blocked_error(address)


def _guarded_create_connection(address, *args, **kwargs):
    _check_address(address)
    return _original_create_connection(address, *args, **kwargs)


def _guarded_socket_connect(self, address):
    _check_address(address)
    return _original_socket_connect(self, address)


socket.create_connection = _guarded_create_connection
socket.socket.connect = _guarded_socket_connect
""".lstrip(),
            encoding="utf-8",
        )
        return guard_dir

    def build_elastic_profile(
        self,
        read_literals: list[str] | None = None,
        write_literals: list[str] | None = None,
    ) -> str:
        """根據讀寫白名單動態拼接 macOS sandbox-exec 的 Profile"""
        profile = ["(version 1)", "(deny default)", "(deny network-outbound)"]
        if read_literals:
            for path in read_literals:
                profile.append(f'(allow file-read* (literal "{path}"))')
        if write_literals:
            for path in write_literals:
                profile.append(f'(allow file-write* (literal "{path}"))')
        return "\n".join(profile)

    def run_task(
        self,
        task: str,
        *,
        command: list[str] | tuple[str, ...] | None,
        cwd: str | Path = ".",
        timeout_sec: int = 60,
        output_file: str | Path | None = None,
        cleanup: bool = True,
        elastic_profile: str | None = None,
    ) -> dict[str, Any]:
        """Run an explicit local command inside a copied workspace sandbox."""
        if not command:
            raise ValueError("Sandbox physical runner requires an explicit command.")

        start_time = time.time()
        run_id = f"run_{int(start_time * 1000)}_{uuid.uuid4().hex[:8]}"
        run_dir = self.sandbox_base / "runs" / run_id
        workspace_path = run_dir / "workspace"
        command_list = [str(part) for part in command]
        run_dir.mkdir(parents=True, exist_ok=True)

        result_payload: dict[str, Any] | None = None
        try:
            self._copy_workspace(workspace_path)
            cwd_path = Path(cwd)
            effective_cwd = cwd_path if cwd_path.is_absolute() else workspace_path / cwd_path
            effective_cwd = effective_cwd.resolve()
            if not effective_cwd.is_relative_to(workspace_path.resolve()):
                result_payload = self._failure_result(
                    task=task,
                    command=command_list,
                    run_id=run_id,
                    run_dir=run_dir,
                    workspace_path=workspace_path,
                    cwd=cwd,
                    output_file=output_file,
                    cleanup=cleanup,
                    error="cwd_outside_sandbox_workspace",
                    duration_sec=time.time() - start_time,
                )
                return self._write_result(run_dir, result_payload)
            if not effective_cwd.exists() or not effective_cwd.is_dir():
                result_payload = self._failure_result(
                    task=task,
                    command=command_list,
                    run_id=run_id,
                    run_dir=run_dir,
                    workspace_path=workspace_path,
                    cwd=cwd,
                    output_file=output_file,
                    cleanup=cleanup,
                    error="cwd_missing",
                    duration_sec=time.time() - start_time,
                )
                return self._write_result(run_dir, result_payload)

            output_path: Path | None = None
            if output_file:
                requested_output = Path(output_file)
                output_path = requested_output if requested_output.is_absolute() else workspace_path / requested_output
                output_path = output_path.resolve()
                if not output_path.is_relative_to(workspace_path.resolve()):
                    result_payload = self._failure_result(
                        task=task,
                        command=command_list,
                        run_id=run_id,
                        run_dir=run_dir,
                        workspace_path=workspace_path,
                        cwd=cwd,
                        output_file=output_file,
                        cleanup=cleanup,
                        error="output_file_outside_sandbox_workspace",
                        duration_sec=time.time() - start_time,
                    )
                    return self._write_result(run_dir, result_payload)

            env = os.environ.copy()
            guard_dir = self._write_python_network_guard(run_dir)
            env["NEXUS_SANDBOX_NO_NETWORK"] = "1"
            env["NEXUS_SANDBOX_WORKSPACE"] = str(workspace_path)
            env["PYTHONPATH"] = os.pathsep.join(
                part for part in [str(guard_dir), env.get("PYTHONPATH", "")] if part
            )
            active_command = command_list
            barrier_mode = "python_sitecustomize"
            loopback_allowed = True

            if self.has_sandbox_exec:
                if elastic_profile:
                    active_command = [
                        "sandbox-exec",
                        "-p",
                        elastic_profile,
                    ] + command_list
                    barrier_mode = "os_level_sandbox_exec"
                    loopback_allowed = False
                else:
                    active_command = [
                        "sandbox-exec",
                        "-p",
                        "(version 1) (allow default) (deny network-outbound)",
                    ] + command_list
                    barrier_mode = "os_level_sandbox_exec"
                    loopback_allowed = False

            proc = subprocess.run(
                active_command,
                cwd=effective_cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            duration_sec = time.time() - start_time
            output_artifact_path = None
            output_artifact = None
            output_missing = False
            if output_path is not None:
                if output_path.exists() and output_path.is_file():
                    artifact_path = run_dir / "artifacts" / output_path.relative_to(workspace_path)
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(output_path, artifact_path)
                    output_artifact_path = str(artifact_path)
                    artifact_bytes = artifact_path.read_bytes()
                    output_artifact = {
                        "sandbox_relative_path": str(output_path.relative_to(workspace_path)),
                        "artifact_path": output_artifact_path,
                        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                        "size_bytes": len(artifact_bytes),
                    }
                else:
                    output_missing = True

            success = proc.returncode == 0 and not output_missing
            result_payload = {
                "schema": "nexus.sandbox_run_task.v1",
                "task": task,
                "success": success,
                "exit_code": 127 if output_missing and proc.returncode == 0 else proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "timed_out": False,
                "duration_sec": duration_sec,
                "command": command_list,
                "cwd": str(cwd),
                "effective_cwd": str(effective_cwd),
                "workspace_source": "local_project_copy",
                "workspace_path": str(workspace_path),
                "run_id": run_id,
                "report_path": str(run_dir / "sandbox_result.json"),
                "output_file": str(output_file) if output_file else None,
                "output_artifact_path": output_artifact_path,
                "output_artifact": output_artifact,
                "cleanup": cleanup,
                "error": "output_file_missing" if output_missing else None,
                "network_allowed": False,
                "hook_policy": {
                    "source_git_metadata_copied": False,
                    "git_hooks_copied": False,
                    "git_hooks_allowed": False,
                },
                "network_barrier": {
                    "mode": barrier_mode,
                    "loopback_allowed": loopback_allowed,
                    "external_allowed": False,
                },
            }
            return self._write_result(run_dir, result_payload)
        except subprocess.TimeoutExpired as exc:
            result_payload = self._failure_result(
                task=task,
                command=command_list,
                run_id=run_id,
                run_dir=run_dir,
                workspace_path=workspace_path,
                cwd=cwd,
                output_file=output_file,
                cleanup=cleanup,
                error="timeout",
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
                duration_sec=time.time() - start_time,
            )
            return self._write_result(run_dir, result_payload)
        finally:
            if cleanup and workspace_path.exists():
                shutil.rmtree(workspace_path, ignore_errors=True)

    def _collect_runtime_signals(self, target_dir: Path) -> tuple[List[str], int]:
        """Read runtime event log and derive executed phases + phantom triggers."""
        events_path = target_dir / "events_sourced.jsonl"
        if not events_path.exists():
            return [], 0

        phases: List[str] = []
        phantom_triggers = 0
        with events_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw, strict=False)
                except json.JSONDecodeError:
                    continue

                phase = str(event.get("phase", "")).strip()
                if phase and phase not in phases:
                    phases.append(phase)

                event_type = str(event.get("event_type", "")).lower()
                payload = event.get("payload", {})
                payload_text = json.dumps(payload, ensure_ascii=False).lower() if isinstance(payload, dict) else str(payload).lower()
                if "phantom" in event_type or "phantom" in payload_text:
                    phantom_triggers += 1

        return phases, phantom_triggers

    def run_challenge(self, repo_url: str, task: str) -> ChallengeReport:
        start_time = time.time()
        # 1. 創立隔離目錄
        session_id = f"challenge_{int(time.time())}"
        target_dir = self.sandbox_base / session_id
        
        logger.info(f"🥊 [Sandbox] Starting challenge on {repo_url}...")
        
        try:
            # 2. Clone (Shallow)
            clone_result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
                check=False,
                capture_output=True,
                text=True,
            )
            if clone_result.returncode != 0:
                logger.error(
                    "❌ [Sandbox] git clone failed RC=%s stderr=%s",
                    clone_result.returncode,
                    (clone_result.stderr or "").strip()[-400:],
                )
                return ChallengeReport(
                    repo_url=repo_url,
                    challenge_task=task,
                    success=False,
                    phases_completed=[],
                    phantom_triggers=0,
                    duration_sec=time.time() - start_time,
                )
            
            # 3. 物理掛載：啟動真實 Nexus 分身
            logger.info(f"🚀 [Sandbox] Deploying true Nexus clone into sandbox for task: {task}")
            
            cli_path = self.project_root / "scripts" / "engine" / "nexus_cli.py"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            
            cmd = ["python3", str(cli_path), "run", "--task", task, "--silent"]
            result = subprocess.run(
                cmd,
                cwd=str(target_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            
            success = result.returncode == 0
            if not success:
                logger.error(f"❌ [Sandbox] Nexus pipeline failed with RC={result.returncode}")
                # logger.debug(f"Stderr: {result.stderr}")
            else:
                logger.info(f"✅ [Sandbox] Nexus pipeline succeeded.")

            phases_completed, phantom_triggers = self._collect_runtime_signals(target_dir)
            
            return ChallengeReport(
                repo_url=repo_url,
                challenge_task=task,
                success=success,
                phases_completed=phases_completed,
                phantom_triggers=phantom_triggers,
                duration_sec=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"❌ [Sandbox] Challenge failed: {e}")
            return ChallengeReport(
                repo_url=repo_url,
                challenge_task=task,
                success=False,
                phases_completed=[],
                phantom_triggers=0,
                duration_sec=time.time() - start_time
            )
        finally:
            # 4. 清理 (可選)
            # shutil.rmtree(target_dir, ignore_errors=True)
            pass
