from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nexus.learning.zero_trust_v2_receipts import canonical_json_hash


DEFAULT_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "PYTHONPATH")
DEFAULT_TIMEOUT_SEC = 3
DEFAULT_MEMORY_MB = 512


def _env_allowlist_hash(env: dict[str, str]) -> str:
    return canonical_json_hash({key: env[key] for key in sorted(env)})


def _artifact_hash(payload: dict[str, Any]) -> str:
    return canonical_json_hash(payload)


def _sandbox_signature(*, attestation_body: dict[str, Any], signing_secret: str) -> str:
    digest = canonical_json_hash(attestation_body)
    return hmac.new(signing_secret.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()


def _macos_sandbox_profile(workspace_dir: Path, tmp_dir: Path) -> str:
    workspace = str(workspace_dir).replace("\\", "\\\\").replace('"', '\\"')
    tmp = str(tmp_dir).replace("\\", "\\\\").replace('"', '\\"')
    return f"""
(version 1)
(allow default)
(deny network*)
(allow file-read* (subpath "{workspace}"))
(allow file-write* (subpath "{workspace}"))
(allow file-read* (subpath "{tmp}"))
(allow file-write* (subpath "{tmp}"))
"""


def run_macos_sandbox_probe(
    command: Sequence[str],
    *,
    signing_secret: str,
    workspace_files: dict[str, str] | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    memory_mb: int = DEFAULT_MEMORY_MB,
    sandbox_exec_path: str | None = None,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    base_tmp_dir: str | Path | None = None,
    env_source: dict[str, str] | None = None,
    env_allowlist: Sequence[str] = DEFAULT_ENV_ALLOWLIST,
) -> dict[str, Any]:
    """Run one command through a macOS sandbox probe and return runner-owned attestation.

    The child environment is allowlisted. The signing secret is consumed only by
    the observer process and is never forwarded to the child process.
    """

    if not command:
        raise ValueError("command must not be empty")
    if not signing_secret:
        raise ValueError("signing_secret must not be empty")

    sandbox_exec = sandbox_exec_path or shutil.which("sandbox-exec")
    source_env = dict(env_source if env_source is not None else os.environ)
    child_env = {key: source_env[key] for key in env_allowlist if key in source_env}
    sandbox_available = bool(sandbox_exec)

    root_path = Path(tempfile.mkdtemp(prefix="nexus-ztv2-runner-", dir=str(base_tmp_dir) if base_tmp_dir else None))
    workspace_dir = root_path / "workspace"
    tmp_dir = root_path / "tmp"
    workspace_dir.mkdir()
    tmp_dir.mkdir()
    for relative_path, content in (workspace_files or {}).items():
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("workspace file paths must be relative and stay inside the sandbox workspace")
        target = workspace_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    profile_path = root_path / "sandbox.sb"
    profile_path.write_text(_macos_sandbox_profile(workspace_dir, tmp_dir), encoding="utf-8")
    child_env["TMPDIR"] = str(tmp_dir)

    if sandbox_available:
        runner_cmd = [str(sandbox_exec), "-f", str(profile_path), *list(command)]
    else:
        runner_cmd = list(command)

    try:
        try:
            completed = subprocess_run(
                runner_cmd,
                cwd=str(workspace_dir),
                env=child_env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            returncode = int(completed.returncode)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            returncode = 124
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else "timeout"
            timed_out = True
    finally:
        shutil.rmtree(root_path, ignore_errors=True)

    sandbox_apply_failed = sandbox_available and returncode == 71 and "sandbox_apply" in stderr
    command_passed = returncode == 0 and not timed_out and not sandbox_apply_failed
    raw_observation = {
        "returncode": returncode,
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        "timed_out": timed_out,
        "sandbox_available": sandbox_available,
        "sandbox_apply_failed": sandbox_apply_failed,
    }
    artifact_hash = _artifact_hash(raw_observation)
    teardown_status = "PASS" if not root_path.exists() else "FAIL"
    attestation_body = {
        "issuer": "nexus.runner",
        "sandbox_mode": "macos_sandbox",
        "status": "PASS" if command_passed and teardown_status == "PASS" else "BLOCKED",
        "network_disabled": sandbox_available and not sandbox_apply_failed,
        "workspace_isolated": True,
        "tmp_isolated": True,
        "env_allowlist_hash": _env_allowlist_hash(child_env),
        "resource_limits": {"cpu": "process_timeout", "memory_mb": memory_mb, "timeout_sec": timeout_sec},
        "teardown_status": teardown_status,
        "artifact_hash": artifact_hash,
        "runner_quarantine_status": "NONE" if teardown_status == "PASS" else "QUARANTINED",
        "raw_observation": raw_observation,
    }
    attestation = {
        **attestation_body,
        "signature": _sandbox_signature(attestation_body=attestation_body, signing_secret=signing_secret),
    }
    promotion_eligible = command_passed and teardown_status == "PASS"
    return {
        "schema": "nexus.zero_trust_v2.physical_sandbox_probe.v1",
        "status": "PASS" if promotion_eligible else "BLOCKED",
        "promotion_eligible": promotion_eligible,
        "command": list(command),
        "sandbox_attestation": attestation,
    }
