"""Measurement-only Claude worker for the #2721 bare-vs-Nexus study.

#2721 (prereg v0.4 §9) runs one model, ``claude-haiku-5-5``, in both arms:
the BARE arm calls the Claude CLI directly in the task worktree; the NEXUS arm
reaches the same CLI through P1 (``nexus_worker_candidate``).  This module is
the single definition of that invocation, so both arms run byte-identical
argv and environment and differ only by the prompt text Nexus appends.

The worker exists only on the measurement Gateway: every entry point is inert
unless ``NEXUS_MEASUREMENT_CLAUDE_WORKER=1`` is set in the process
environment, and the live Gateway never sets it.  When it is unset the worker
registry, the provider allowlist and the workforce policy are exactly what
they were before this module existed.

Invocation (fixed, no caller may change it):

* executable: the absolute path in ``NEXUS_MEASUREMENT_CLAUDE_BIN`` (a host
  may have several ``claude`` binaries; no PATH lookup);
* ``--safe-mode --setting-sources ""``: no CLAUDE.md, memory, hooks,
  plugins, MCP servers, or user/project/local settings (``--bare`` cannot be
  used: it never reads the OAuth login the measurement accounts use);
* ``--disallowedTools WebSearch,WebFetch``: no web lookup in either arm;
* ``--permission-mode acceptEdits``, ``--output-format stream-json
  --verbose`` (the tool trace), ``--no-session-persistence``;
* an exact child environment (``measurement_child_env``): HOME, USER,
  LOGNAME, LANG, TMPDIR from the process, a fixed system-only PATH and
  ``CLAUDE_CODE_DISABLE_AUTO_MEMORY=1``; ``run_cli_worker`` adds only its
  run tag and the GitHub-credential isolation keys.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

MEASUREMENT_CLAUDE_ENV = "NEXUS_MEASUREMENT_CLAUDE_WORKER"
MEASUREMENT_CLAUDE_BIN_ENV = "NEXUS_MEASUREMENT_CLAUDE_BIN"
MEASUREMENT_TRACE_DIR_ENV = "NEXUS_MEASUREMENT_TRACE_DIR"

CLAUDE_MEASUREMENT_PROVIDER = "claude"
CLAUDE_MEASUREMENT_MODEL = "claude-haiku-5-5"
CLAUDE_MEASUREMENT_WORKER_ID = "claude_haiku_measure"
CLAUDE_MEASUREMENT_FLAGS: tuple[str, ...] = (
    "-p",
    "--safe-mode",
    "--setting-sources",
    "",
    "--model",
    CLAUDE_MEASUREMENT_MODEL,
    "--permission-mode",
    "acceptEdits",
    "--disallowedTools",
    "WebSearch,WebFetch",
    "--output-format",
    "stream-json",
    "--verbose",
    "--no-session-persistence",
)
CLAUDE_MEASUREMENT_ENV: Mapping[str, str] = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
# Fixed so that the Gateway and the BARE runner give the agent the same tools:
# system directories only (no Homebrew, no ~/.local/bin, so no gh or agy).
CLAUDE_MEASUREMENT_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
# Identity keys the CLI needs for its own login; taken from the process.
_PASSED_IDENTITY_KEYS = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR")
_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def measurement_claude_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """True only for the exact value ``"1"``; anything else keeps the worker off."""
    env = os.environ if environ is None else environ
    return str(env.get(MEASUREMENT_CLAUDE_ENV, "")) == "1"


def measurement_claude_executable(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The configured absolute Claude CLI path, or None when unset or unusable."""
    env = os.environ if environ is None else environ
    raw = str(env.get(MEASUREMENT_CLAUDE_BIN_ENV, "") or "").strip()
    if not raw or not os.path.isabs(raw):
        return None
    path = Path(raw)
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    return str(path)


def measurement_child_env(environ: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The exact child environment of every measurement Claude run (both arms)."""
    env = os.environ if environ is None else environ
    child = {key: str(env[key]) for key in _PASSED_IDENTITY_KEYS if env.get(key)}
    child["PATH"] = CLAUDE_MEASUREMENT_PATH
    child.update(CLAUDE_MEASUREMENT_ENV)
    return child


def claude_measurement_argv(prompt: str) -> tuple[str, ...]:
    """Arguments after the executable; the prompt is the final positional."""
    text = str(prompt)
    if not text.strip():
        raise ValueError("claude measurement prompt is empty")
    if text.startswith("-"):
        raise ValueError("claude measurement prompt must not start with '-'")
    return (*CLAUDE_MEASUREMENT_FLAGS, text)


@dataclass(frozen=True)
class ClaudeStreamSummary:
    """What a stream-json run reports about itself."""

    result_seen: bool
    is_error: Optional[bool]
    subtype: str
    num_turns: Optional[int]
    total_cost_usd: Optional[float]
    usage: dict[str, Any]
    model_usage: dict[str, Any]
    models_seen: tuple[str, ...]
    tool_calls: tuple[dict[str, Any], ...]
    permission_denials: tuple[Any, ...]
    session_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_seen": self.result_seen,
            "is_error": self.is_error,
            "subtype": self.subtype,
            "num_turns": self.num_turns,
            "total_cost_usd": self.total_cost_usd,
            "usage": self.usage,
            "model_usage": self.model_usage,
            "models_seen": list(self.models_seen),
            "tool_calls": [dict(call) for call in self.tool_calls],
            "permission_denials": list(self.permission_denials),
            "session_id": self.session_id,
        }


def summarize_stream_json(stdout: str | bytes) -> ClaudeStreamSummary:
    """Parse ``--output-format stream-json`` output; unknown lines are skipped."""
    text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout)
    tool_calls: list[dict[str, Any]] = []
    models: list[str] = []
    result: dict[str, Any] = {}
    session_id = ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            session_id = str(event.get("session_id") or session_id)
            model = event.get("model")
            if isinstance(model, str) and model not in models:
                models.append(model)
        elif kind == "assistant":
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            model = message.get("model")
            if isinstance(model, str) and model not in models:
                models.append(model)
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": str(block.get("id") or ""),
                        "name": str(block.get("name") or ""),
                        "input": block.get("input"),
                        "parent_tool_use_id": event.get("parent_tool_use_id"),
                    })
        elif kind == "result":
            result = event
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    model_usage = result.get("modelUsage") if isinstance(result.get("modelUsage"), dict) else {}
    for name in model_usage:
        if name not in models:
            models.append(str(name))
    num_turns = result.get("num_turns")
    cost = result.get("total_cost_usd")
    denials = result.get("permission_denials")
    return ClaudeStreamSummary(
        result_seen=bool(result),
        is_error=result.get("is_error") if isinstance(result.get("is_error"), bool) else None,
        subtype=str(result.get("subtype") or ""),
        num_turns=num_turns if isinstance(num_turns, int) and not isinstance(num_turns, bool) else None,
        total_cost_usd=float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        usage=dict(usage),
        model_usage=dict(model_usage),
        models_seen=tuple(models),
        tool_calls=tuple(tool_calls),
        permission_denials=tuple(denials) if isinstance(denials, list) else (),
        session_id=str(result.get("session_id") or session_id),
    )


def write_measurement_trace(task_id: str, stdout: bytes, stdout_sha256: str,
                            environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Keep the raw stream-json trace when the measurement host asks for it.

    Only ``NEXUS_MEASUREMENT_TRACE_DIR`` (absolute) enables this; the file is
    content-addressed by the receipt's ``stdout_sha256``, so the receipt
    binds it.  Returns the path written, or None.
    """
    env = os.environ if environ is None else environ
    root = str(env.get(MEASUREMENT_TRACE_DIR_ENV, "") or "").strip()
    if not root or not os.path.isabs(root) or not _SAFE_TASK_ID.fullmatch(str(task_id)):
        return None
    target = Path(root) / str(task_id) / f"{stdout_sha256}.stream.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(stdout)
    os.chmod(target, 0o600)
    return str(target)


class ClaudeMeasurementWorkerAdapter:
    """``WorkerRegistry`` adapter for provider ``claude`` (measurement only).

    Refuses unless the measurement switch is on and the absolute executable is
    configured, refuses any model other than ``claude-haiku-5-5`` (no silent
    substitution), and runs only in the contract's leased target worktree.
    """

    provider = CLAUDE_MEASUREMENT_PROVIDER
    requires_leased_target = True

    def __init__(self, environ: Optional[Mapping[str, str]] = None):
        self._environ = environ

    def _env(self) -> Mapping[str, str]:
        return os.environ if self._environ is None else self._environ

    def preflight(self) -> Any:
        from nexus.executors.worker_contract import WorkerPreflight

        enabled = measurement_claude_enabled(self._env())
        executable = measurement_claude_executable(self._env())
        if not enabled:
            reason = f"{MEASUREMENT_CLAUDE_ENV}=1 is required (measurement Gateway only)"
        elif executable is None:
            reason = f"{MEASUREMENT_CLAUDE_BIN_ENV} must name an absolute executable claude CLI"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=executable,
            executable_available=executable is not None,
            authorized=enabled,
            implementation_status="IMPLEMENTED",
            ready=enabled and executable is not None,
            reason=reason,
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
        model: Optional[str] = None,
        require_leased_target: bool = False,
        **_ignored: Any,
    ) -> Any:
        from nexus.executors.agy_write_admission import leased_target_failure
        from nexus.executors.cli_worker import CliWorkerRequest, CliWorkerStatus, run_cli_worker
        from nexus.executors.worker_contract import (
            WorkerExecutionReceipt,
            WorkerOutcome,
            WorkerProviderUnavailable,
            redacted_output_tail,
        )

        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        if model is not None and str(model) != CLAUDE_MEASUREMENT_MODEL:
            raise WorkerProviderUnavailable(
                f"{self.provider}: model {model!r} is not the measurement model {CLAUDE_MEASUREMENT_MODEL}"
            )
        if require_leased_target or hasattr(contract, "target_worktree_root"):
            failure = leased_target_failure(contract, lease)
            if failure is not None:
                raise WorkerProviderUnavailable(f"{self.provider}: {failure}")
        target = str(Path(lease.target_worktree).resolve())
        request = CliWorkerRequest(
            executable=str(preflight.executable),
            argv=claude_measurement_argv(prompt),
            cwd=target,
            timeout_seconds=float(timeout_seconds or 900.0),
            env=measurement_child_env(self._env()),
            exact_env=True,
            sweep_descendants_on_exit=True,
            sweep_roots=(target,),
        )
        result = run_cli_worker(request, on_process_group=on_process_group)
        summary = summarize_stream_json(result.stdout)
        if result.status is CliWorkerStatus.TIMED_OUT:
            outcome = WorkerOutcome.INCOMPLETE
        elif (
            result.status is not CliWorkerStatus.COMPLETED
            or result.exit_code != 0
            or not summary.result_seen
            or summary.is_error is not False
        ):
            outcome = WorkerOutcome.FAILED
        else:
            outcome = WorkerOutcome.EXECUTION_COMPLETED
        foreign = [name for name in summary.models_seen if name != CLAUDE_MEASUREMENT_MODEL]
        failure = None
        if foreign:
            outcome = WorkerOutcome.FAILED
            failure = f"{self.provider}: model substitution observed: {sorted(foreign)}"
        elif outcome is not WorkerOutcome.EXECUTION_COMPLETED:
            failure = f"{self.provider} execution did not complete successfully ({summary.subtype or result.status.value})"
        write_measurement_trace(str(getattr(contract, "task_id", "")), result.stdout, result.stdout_sha256,
                                self._env())
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=target,
            worker_status=result.status.value,
            outcome=outcome.value,
            exit_code=result.exit_code,
            executable_identity=result.executable_identity,
            argv=result.argv,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            wall_time_ms=result.wall_time_ms,
            process_group_id=result.process_group_id,
            process_group_killed=result.process_group_killed,
            timed_out=result.timed_out,
            provider_calls=1,
            evidence_complete=outcome is WorkerOutcome.EXECUTION_COMPLETED,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=failure,
            provider_attempt_count=1,
            provider_permission_mode="acceptEdits_no_web",
            provider_env_keys_sha256=result.env_keys_sha256 or None,
            stdout_tail=redacted_output_tail(result.stdout),
            stderr_tail=redacted_output_tail(result.stderr),
        )


# -- Gateway readiness (nexus_worker_candidate preflight) ---------------------

PROBE_PROMPT = "Reply with exactly the word ok and nothing else."
PROBE_TTL_SECONDS = 3600
_PROBE_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _blocked(provider_result: dict[str, Any], blocker: str, **extra: Any) -> dict[str, Any]:
    provider_result.update(status="BLOCKED", blocker=blocker, execution_ready=False, **extra)
    return provider_result


def measurement_claude_preflight(
    requested_model: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    runner: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """``nexus.provider_preflight.v1`` for provider ``claude`` on a measurement Gateway.

    Readiness is proven by one real call of the exact measurement invocation
    (a one-word reply, run in an empty temporary directory) whose stream-json
    result must be a success served only by ``claude-haiku-5-5``.  The proof
    is cached per (binary sha256, CLI version, model) for one hour.
    """
    import datetime
    import hashlib
    import subprocess
    import tempfile

    env = os.environ if environ is None else environ
    run = runner or subprocess.run
    clock = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
    result: dict[str, Any] = {
        "schema": "nexus.provider_preflight.v1",
        "provider": CLAUDE_MEASUREMENT_PROVIDER,
        "requested_model": str(requested_model or ""),
        "resolved_model": str(requested_model or ""),
        "requested_model_verified": False,
        "binary_found": False,
        "binary_path": None,
        "binary_sha256": None,
        "cli_version": None,
        "authenticated": False,
        "authentication_required": False,
        "model_reachable": False,
        "status": "BLOCKED",
        "blocker": None,
        "next_action": None,
        "readiness_status": "BLOCKED",
        "execution_ready": False,
        "measurement_only": True,
    }
    if not measurement_claude_enabled(env):
        return _blocked(result, "MEASUREMENT_CLAUDE_WORKER_DISABLED")
    if str(requested_model or "") != CLAUDE_MEASUREMENT_MODEL:
        return _blocked(result, "MEASUREMENT_CLAUDE_MODEL_MISMATCH")
    executable = measurement_claude_executable(env)
    if executable is None:
        return _blocked(result, "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE")
    binary_sha256 = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    result.update(binary_found=True, binary_path=executable, binary_sha256=binary_sha256)
    with tempfile.TemporaryDirectory(prefix="nexus-claude-preflight-") as scratch:
        version = run([executable, "--version"], cwd=scratch, capture_output=True, text=True,
                      timeout=15, check=False)
        cli_version = (version.stdout or version.stderr or "").strip()[:512]
        result.update(cli_version=cli_version,
                      cli_version_sha256=hashlib.sha256(cli_version.encode("utf-8")).hexdigest())
        if version.returncode != 0 or not cli_version:
            return _blocked(result, "MEASUREMENT_CLAUDE_VERSION_FAILED")
        key = (binary_sha256, cli_version, CLAUDE_MEASUREMENT_MODEL)
        cached = _PROBE_CACHE.get(key)
        current = clock()
        if cached is None or datetime.datetime.fromisoformat(cached["probe_expires_at"]) <= current:
            child_env = measurement_child_env(env)
            probe = run([executable, *claude_measurement_argv(PROBE_PROMPT)], cwd=scratch, capture_output=True,
                        text=True, timeout=120, check=False, env=child_env)
            summary = summarize_stream_json(probe.stdout or "")
            served = set(summary.models_seen)
            if (
                probe.returncode != 0
                or summary.is_error is not False
                or not served
                or served != {CLAUDE_MEASUREMENT_MODEL}
            ):
                return _blocked(result, "MEASUREMENT_CLAUDE_PROBE_FAILED",
                                probe_subtype=summary.subtype, probe_models=sorted(served))
            evidence = {
                "binary_sha256": binary_sha256,
                "cli_version": cli_version,
                "model": CLAUDE_MEASUREMENT_MODEL,
                "session_id": summary.session_id,
                "probed_at": current.isoformat(),
            }
            cached = {
                "probe_evidence_hash": hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "probe_expires_at": (current + datetime.timedelta(seconds=PROBE_TTL_SECONDS)).isoformat(),
                "probed_at": evidence["probed_at"],
            }
            _PROBE_CACHE[key] = cached
    result.update(
        status="VERSION_VERIFIED",
        readiness_status="MODEL_VERIFIED",
        execution_ready=True,
        model_reachable=True,
        requested_model_verified=True,
        authenticated=True,
        authentication_evidence="successful_exact_model_probe",
        probe_evidence_hash=cached["probe_evidence_hash"],
        probe_expires_at=cached["probe_expires_at"],
        probed_at=cached["probed_at"],
    )
    return result
