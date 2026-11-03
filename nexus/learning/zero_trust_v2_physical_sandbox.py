from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nexus.learning.zero_trust_v2_receipts import canonical_json_hash
from nexus.learning.zero_trust_v2_sandbox import sandbox_attestation_signature


DEFAULT_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "PYTHONPATH")
DEFAULT_TIMEOUT_SEC = 3
DEFAULT_MEMORY_MB = 512
# Writes the child may need to start or run ordinary shell commands, beyond its own dirs.
SANDBOX_DEVICE_WRITE_ALLOWLIST = ("/dev/null",)
# sandbox-exec's own exit codes: EX_USAGE, EX_DATAERR (profile parse), EX_OSERR (apply/exec).
SANDBOX_EXEC_FAILURE_RETURNCODES = frozenset({64, 65, 71})


# The one directory the sandbox launcher is taken from; the observer's PATH is not consulted (#3240).
TRUSTED_SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def _file_sha256(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _env_allowlist_hash(env: dict[str, str]) -> str:
    return canonical_json_hash({key: env[key] for key in sorted(env)})


def _artifact_hash(payload: dict[str, Any]) -> str:
    return canonical_json_hash(payload)


def _sandbox_signature(*, attestation_body: dict[str, Any], signing_secret: str) -> str:
    return sandbox_attestation_signature(
        attestation_body=attestation_body, signing_secret=signing_secret
    )


def _sbpl_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write_allow_rule(workspace_dir: Path, tmp_dir: Path) -> str:
    # Paths are resolved because the sandbox matches real paths (/var -> /private/var).
    filters = [
        f'(subpath "{_sbpl_string(str(workspace_dir.resolve()))}")',
        f'(subpath "{_sbpl_string(str(tmp_dir.resolve()))}")',
        *(f'(literal "{_sbpl_string(path)}")' for path in SANDBOX_DEVICE_WRITE_ALLOWLIST),
    ]
    return f"(allow file-write* {' '.join(filters)})"


def _macos_sandbox_profile(workspace_dir: Path, tmp_dir: Path) -> str:
    workspace = _sbpl_string(str(workspace_dir.resolve()))
    tmp = _sbpl_string(str(tmp_dir.resolve()))
    # Reads stay allowed (the attestation claims no read isolation); writes are
    # denied everywhere except the workspace, its tmp dir and the device allowlist.
    return f"""
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-read* (subpath "{workspace}"))
(allow file-read* (subpath "{tmp}"))
{_write_allow_rule(workspace_dir, tmp_dir)}
"""


def _profile_confines_writes(profile: str, *, workspace_dir: Path, tmp_dir: Path) -> bool:
    """True when the profile denies writes and re-allows only workspace, tmp and devices."""

    rules = [line.strip() for line in profile.splitlines() if line.strip()]
    if "(deny file-write*)" not in rules:
        return False
    expected = _write_allow_rule(workspace_dir, tmp_dir)
    after_deny = rules[rules.index("(deny file-write*)") + 1 :]
    if not all(rule == expected or rule.startswith("(allow file-read* ") for rule in after_deny):
        return False
    return all(rule in ("(deny file-write*)", expected) for rule in rules if "file-write" in rule)


def _sandbox_launch_failed(*, returncode: int, stderr: str) -> bool:
    """True when sandbox-exec itself failed, so the profile was not demonstrably applied.

    sandbox-exec exits 64/65/71 with a ``sandbox-exec:`` diagnostic when it cannot
    parse or apply the profile or exec the command. Those codes are treated as a
    launch failure even when the child could have produced them (fail closed). A
    negative code means a signal, which may have arrived before the profile applied.
    """

    if returncode == 0:
        return False
    if returncode < 0 or returncode in SANDBOX_EXEC_FAILURE_RETURNCODES:
        return True
    return "sandbox-exec:" in stderr or "sandbox_apply" in stderr


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

    sandbox_exec = sandbox_exec_path or shutil.which(
        "sandbox-exec", path=str(Path(TRUSTED_SANDBOX_EXEC).parent)
    )
    sandbox_exec_unexpected = bool(sandbox_exec) and str(sandbox_exec) != TRUSTED_SANDBOX_EXEC
    sandbox_exec_sha256 = _file_sha256(str(sandbox_exec) if sandbox_exec else None)
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
    profile = _macos_sandbox_profile(workspace_dir, tmp_dir)
    profile_path.write_text(profile, encoding="utf-8")
    writes_confined = _profile_confines_writes(
        profile, workspace_dir=workspace_dir, tmp_dir=tmp_dir
    )
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

    sandbox_apply_failed = (
        sandbox_available
        and not timed_out
        and _sandbox_launch_failed(returncode=returncode, stderr=stderr)
    )
    command_passed = returncode == 0 and not timed_out and not sandbox_apply_failed
    # A timeout leaves no exit status, so the profile is not demonstrably applied.
    sandbox_ran = (
        sandbox_available
        and not sandbox_exec_unexpected
        and not timed_out
        and not sandbox_apply_failed
    )
    isolated = sandbox_ran and writes_confined
    if not sandbox_available:
        isolation_reason = "sandbox_exec_unavailable"
    elif sandbox_exec_unexpected:
        isolation_reason = "sandbox_exec_path_unexpected"
    elif timed_out:
        isolation_reason = "sandbox_outcome_unknown_timeout"
    elif sandbox_apply_failed:
        isolation_reason = (
            "sandbox_apply_failed" if "sandbox_apply" in str(stderr) else "sandbox_launch_failed"
        )
    elif not writes_confined:
        isolation_reason = "profile_write_scope_unconfined"
    else:
        isolation_reason = None
    raw_observation = {
        "returncode": returncode,
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        "timed_out": timed_out,
        "sandbox_available": sandbox_available,
        "sandbox_exec_path": str(sandbox_exec) if sandbox_exec else None,
        "sandbox_exec_sha256": sandbox_exec_sha256,
        "sandbox_apply_failed": sandbox_apply_failed,
        "write_scope_confined": writes_confined,
    }
    artifact_hash = _artifact_hash(raw_observation)
    teardown_status = "PASS" if not root_path.exists() else "FAIL"
    attestation_body = {
        "issuer": "nexus.runner",
        "sandbox_mode": "macos_sandbox",
        "status": "PASS" if command_passed and teardown_status == "PASS" else "BLOCKED",
        "network_disabled": sandbox_ran,
        "workspace_isolated": isolated,
        "workspace_isolation_reason": isolation_reason,
        "tmp_isolated": isolated,
        "env_allowlist_hash": _env_allowlist_hash(child_env),
        # Only the timeout is enforced on the child; the memory figure is what the caller
        # asked for and nothing applies it, so it is not reported as a limit (#3229).
        "resource_limits": {
            "cpu": "process_timeout",
            "memory_mb": None,
            "memory_mb_requested": memory_mb,
            "memory_enforced": False,
            "timeout_sec": timeout_sec,
        },
        "teardown_status": teardown_status,
        "artifact_hash": artifact_hash,
        "runner_quarantine_status": "NONE" if teardown_status == "PASS" else "QUARANTINED",
        "raw_observation": raw_observation,
    }
    attestation = {
        **attestation_body,
        "signature": _sandbox_signature(attestation_body=attestation_body, signing_secret=signing_secret),
    }
    promotion_eligible = command_passed and isolated and teardown_status == "PASS"
    return {
        "schema": "nexus.zero_trust_v2.physical_sandbox_probe.v1",
        "status": "PASS" if promotion_eligible else "BLOCKED",
        "promotion_eligible": promotion_eligible,
        "command": list(command),
        "sandbox_attestation": attestation,
    }
