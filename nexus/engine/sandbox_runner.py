from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import subprocess
import shutil
import logging
import time
import os
import json
import stat
import uuid
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

from nexus.core.state_root import persistent_state_root

logger = logging.getLogger(__name__)

@dataclass
class ChallengeReport:
    repo_url: str
    challenge_task: str
    success: bool
    phases_completed: List[str]
    phantom_triggers: int
    duration_sec: float

def _guard_write_deny_rule(guard_dir: Path) -> str:
    """Deny writes to the Python network guard, even under an allowed write path.

    sandbox-exec applies the last matching rule, so this goes at the end of the profile.
    It matters when the run record dir sits under /tmp or /private/tmp (both writable):
    the sandboxed process must not be able to rewrite its own guard (#2698 review).
    """
    paths = [str(guard_dir)]
    real = str(guard_dir.resolve())
    if real not in paths:
        paths.append(real)
    return "\n".join(f'(deny file-write* (subpath "{path}"))' for path in paths)


def _run_dir_write_deny_rule(run_dir: Path) -> str:
    """Deny writes to the run record dir and renames of any directory above it (#2785).

    When ``run_dir`` sits under an allowed write path (/tmp, /private/tmp) the sandboxed
    process could otherwise rename ``run_dir`` (or one of its parents) and put a
    symlink in its place: a later Python child would load a ``sitecustomize.py`` the
    process wrote, and the parent would write ``sandbox_result.json`` through it.

    ``(subpath run_dir)`` refuses every write inside the record dir, including renaming
    it.  ``(literal <ancestor>)`` refuses renaming or removing each parent directory
    while still allowing new files next to it, because Seatbelt checks a rename
    against the source path only.  Both the literal and the resolved spelling are
    listed, since sandbox-exec matches real paths.  It goes at the end of the
    profile, next to the guard deny: the last matching rule wins.  The parent's own
    writes (guard, report, artifacts) happen outside the sandbox and are unaffected.
    """
    forms: list[Path] = [Path(os.path.abspath(run_dir))]
    real = Path(os.path.realpath(run_dir))
    if real not in forms:
        forms.append(real)
    subpaths = [str(form) for form in forms]
    ancestors: list[str] = []
    for form in forms:
        for parent in form.parents:
            text = str(parent)
            if text not in ancestors:
                ancestors.append(text)
    lines = [f'(deny file-write* (subpath "{path}"))' for path in subpaths]
    lines.extend(f'(deny file-write* (literal "{path}"))' for path in ancestors)
    return "\n".join(lines)


# Reason code when run_dir is no longer the directory the parent created (#2785).
RUN_DIR_REPLACED = "run_dir_replaced_during_run"


class RunDirUnsafe(RuntimeError):
    """run_dir is a symlink, not a directory, or not the directory recorded before the run."""


@dataclass(frozen=True)
class RunDirIdentity:
    st_dev: int
    st_ino: int
    real_path: str


def _capture_run_dir_identity(run_dir: Path) -> RunDirIdentity:
    info = os.lstat(run_dir)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RunDirUnsafe(f"{run_dir} is not a real directory")
    return RunDirIdentity(info.st_dev, info.st_ino, os.path.realpath(run_dir))


def _run_dir_mismatch(run_dir: Path, identity: RunDirIdentity) -> str | None:
    """Return why ``run_dir`` is not the recorded directory any more, or None if it is."""
    try:
        info = os.lstat(run_dir)
    except OSError as exc:
        return f"lstat failed: {exc}"
    if stat.S_ISLNK(info.st_mode):
        return "run_dir is a symlink"
    if not stat.S_ISDIR(info.st_mode):
        return "run_dir is not a directory"
    if (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
        return "run_dir device/inode changed"
    # A renamed parent replaced by a symlink to the renamed tree keeps the same
    # device/inode at the end of the path; the resolved path tells them apart.
    if os.path.realpath(run_dir) != identity.real_path:
        return "run_dir resolves to a different path"
    return None


# Device files every process may write (mirrors nexus/engine/sandboxed_lane.py).
SANDBOX_DEVICE_WRITE_RULE = (
    '(allow file-write* (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))'
)


class SandboxRunner:
    """🧬 Nexus v4.0: 陌生工程生存挑戰器
    職責：在隔離環境中對陌生專案執行 Nexus Pipeline，驗證治理鏈魯棒性。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        # Run records (sandbox_result.json, collected artifacts) stay readable after
        # run_task returns.  They follow NEXUS_STATE_ROOT (#2688), so on the live
        # Gateway they no longer land inside the per-deploy tree (#2698).  Created on
        # first use, not here: constructing a runner writes nothing.
        self.sandbox_base = persistent_state_root(project_root) / ".nexus" / "sandbox"

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

    def _make_scratch_dir(self, prefix: str) -> Path:
        """A fresh system temp directory outside the project and the deployment tree (#2698).

        The working copy and the Python network guard live here, never under
        ``project_root``: on the live Gateway that is the per-deploy directory.
        """
        scratch = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
        project_real = Path(self.project_root).resolve()
        if scratch == project_real or project_real in scratch.parents:
            shutil.rmtree(scratch, ignore_errors=True)
            raise RuntimeError(
                f"sandbox temp dir {scratch} is inside the project root {project_real}; "
                "set TMPDIR to a directory outside it"
            )
        return scratch

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

    def _write_result(
        self,
        run_dir: Path,
        result: dict[str, Any],
        identity: RunDirIdentity | None = None,
    ) -> dict[str, Any]:
        """Write sandbox_result.json without following any symlink at run_dir (#2785).

        ``run_dir`` must still be the directory recorded in ``identity`` (same device
        and inode, same resolved path, not a symlink), and the report itself is opened
        with ``O_NOFOLLOW`` relative to that directory.  Otherwise nothing is written:
        the run is marked failed with ``RUN_DIR_REPLACED`` and ``report_path`` is None.
        """
        report_path = run_dir / "sandbox_result.json"
        try:
            if identity is None:
                run_dir.mkdir(parents=True, exist_ok=True)
                identity = _capture_run_dir_identity(run_dir)
            mismatch = _run_dir_mismatch(run_dir, identity)
            if mismatch:
                raise RunDirUnsafe(mismatch)
            result["report_path"] = str(report_path)
            self._write_report_nofollow(
                run_dir,
                identity,
                report_path.name,
                json.dumps(result, indent=2, ensure_ascii=False),
            )
        except (RunDirUnsafe, OSError) as exc:
            result["success"] = False
            if result.get("error") not in (None, RUN_DIR_REPLACED):
                result["original_error"] = result["error"]
            result["error"] = RUN_DIR_REPLACED
            result["report_path"] = None
            result["report_write_refused"] = str(exc)
            logger.error("sandbox run record not written: %s", exc)
        return result

    @staticmethod
    def _write_report_nofollow(
        run_dir: Path, identity: RunDirIdentity, name: str, text: str
    ) -> None:
        dir_fd = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(dir_fd)
            if (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
                raise RunDirUnsafe("run_dir device/inode changed before the report write")
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o644,
                dir_fd=dir_fd,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise RunDirUnsafe(f"{name} is not a regular file")
                handle.write(text)
        finally:
            os.close(dir_fd)

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
        """根據讀寫白名單動態拼接 macOS sandbox-exec 的 Profile (使用 subpath 語意支援子目錄加載)"""
        profile = [
            "(version 1)",
            "(deny default)",
            "(deny network-outbound)",
            "(allow process-fork)",
            "(allow process-exec*)",
            "(allow file-read*)",
        ]
        if read_literals:
            for path in read_literals:
                profile.append(f'(allow file-read* (subpath "{path}"))')
        if write_literals:
            for path in write_literals:
                profile.append(f'(allow file-write* (subpath "{path}"))')
        # pytest and most tools write /dev/null; without this every pytest run inside the
        # sandbox stops with INTERNALERROR exit 3 (#2685).  Same rule as sandboxed_lane.
        profile.append(SANDBOX_DEVICE_WRITE_RULE)
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
        command_list = [str(part) for part in command]
        run_dir.mkdir(parents=True, exist_ok=True)
        # Recorded before the child starts; checked again before anything is written
        # back into run_dir (#2785).
        run_dir_identity = _capture_run_dir_identity(run_dir)
        # The working copy goes to a system temp dir, removed on exit when cleanup is
        # set (#2698).  The run record and the network guard stay in run_dir, outside
        # the sandbox's write paths, so the process cannot rewrite its own guard.
        scratch_dir = self._make_scratch_dir(f"nexus-sandbox-{run_id}-")
        workspace_path = scratch_dir / "workspace"

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
                return self._write_result(run_dir, result_payload, run_dir_identity)
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
                return self._write_result(run_dir, result_payload, run_dir_identity)

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
                    return self._write_result(run_dir, result_payload, run_dir_identity)

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
                    applied_profile = elastic_profile
                else:
                    # 動態影響路徑 (Blast Radius) 自動推導演算法
                    read_paths = [
                        "/usr",
                        "/bin",
                        "/sbin",
                        "/private",
                        "/System",
                        "/Library",
                        str(workspace_path),
                    ]
                    # sandbox-exec matches real paths: a symlinked project root such as
                    # /var/... (-> /private/var/...) never matches unless resolved (#2685).
                    workspace_real = str(workspace_path.resolve())
                    if workspace_real not in read_paths:
                        read_paths.append(workspace_real)
                    if Path("/opt/homebrew").exists():
                        read_paths.append("/opt/homebrew")
                    # 收集所有 Python 運行相關的路徑
                    python_paths = [
                        sys.prefix,
                        sys.base_prefix,
                        sys.exec_prefix,
                        sys.base_exec_prefix,
                    ]
                    for p in python_paths:
                        if p:
                            read_paths.append(p)
                            try:
                                resolved = str(Path(p).resolve())
                                if resolved not in read_paths:
                                    read_paths.append(resolved)
                            except Exception:
                                pass

                    # 額外確保 Python 實體執行檔與符號連結所在之 resolve 目錄在白名單中
                    try:
                        real_exec_dir = str(Path(sys.executable).resolve().parent)
                        if real_exec_dir not in read_paths:
                            read_paths.append(real_exec_dir)
                        sym_exec_dir = str(Path(sys.executable).parent)
                        if sym_exec_dir not in read_paths:
                            read_paths.append(sym_exec_dir)
                    except Exception:
                        pass

                    write_paths = [
                        str(workspace_path),
                        "/tmp",
                        "/private/tmp",
                    ]
                    if workspace_real not in write_paths:
                        write_paths.append(workspace_real)
                    if output_path:
                        write_paths.append(str(output_path.parent))

                    applied_profile = self.build_elastic_profile(
                        read_literals=read_paths,
                        write_literals=write_paths
                    )

                applied_profile = (
                    f"{applied_profile}\n{_guard_write_deny_rule(guard_dir)}"
                    f"\n{_run_dir_write_deny_rule(run_dir)}"
                )
                active_command = [
                    "sandbox-exec",
                    "-p",
                    applied_profile,
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
            mismatch = _run_dir_mismatch(run_dir, run_dir_identity)
            if mismatch:
                result_payload = self._failure_result(
                    task=task,
                    command=command_list,
                    run_id=run_id,
                    run_dir=run_dir,
                    workspace_path=workspace_path,
                    cwd=cwd,
                    output_file=output_file,
                    cleanup=cleanup,
                    error=RUN_DIR_REPLACED,
                    exit_code=126,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    duration_sec=duration_sec,
                )
                result_payload["run_dir_mismatch"] = mismatch
                # _write_result sees the same mismatch and writes nothing.
                return self._write_result(run_dir, result_payload, run_dir_identity)
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
            return self._write_result(run_dir, result_payload, run_dir_identity)
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
            return self._write_result(run_dir, result_payload, run_dir_identity)
        finally:
            if cleanup:
                shutil.rmtree(scratch_dir, ignore_errors=True)

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
        # Clone into a system temp dir, not under project_root (#2698).
        scratch_dir = self._make_scratch_dir(f"nexus-sandbox-{session_id}-")
        target_dir = scratch_dir / session_id
        
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
            # 4. 清理: the report is built above; nothing reads the clone afterwards.
            shutil.rmtree(scratch_dir, ignore_errors=True)
