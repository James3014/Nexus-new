"""Model providers for the BARE arm.

``AgyPoolProvider`` runs the exact worker the P1 Gateway runs: the production
``AgyWorkerAdapter`` on a leased pool account (``use_installed_account_pool``,
``require_account_pool``), ``worker_role="implementation"``, model from
``NEXUS_AGY_WORKER_MODEL`` (default ``gemini-3.8-flash-medium``), one provider
call, Seatbelt-confined to the run's work dir.  It reuses the #2528 status and
token helpers from ``real_world_task_runner`` so both benches classify Agy
failures the same way.

``FakeProvider`` makes no model call; it only records the prompt (and may
apply a scripted edit) for zero-model dry runs and tests.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

STATUS_OK = "OK"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_MODEL_FAILED = "MODEL_FAILED"
# Infra statuses: the S4 rule re-runs them in every arm; never a model outcome.
STATUS_INFRA = "INFRA"
INFRA_REASONS = (
    "AGY_POOL_BUSY",
    "POOL_EXHAUSTED",
    "AGY_NOT_AUTHENTICATED",
    "AGY_RUNTIME_NOT_AUTHORIZED",
    "SWEEP_FAILED",
    "NO_LEASED_ACCOUNT",
)


@dataclass
class ProviderResult:
    status: str
    provider: str
    model: str
    model_calls: int = 0
    total_tokens: Optional[int] = None
    token_status: str = "not_run"
    exit_code: Optional[int] = None
    timed_out: bool = False
    failure_reason: str = ""
    infra_reason: str = ""
    account_alias_hash: str = ""
    rotation_attempts: int = 0
    wall_seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Provider(Protocol):
    name: str

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str,
            controller: Optional[Path] = None) -> ProviderResult: ...


class FakeProvider:
    """Zero-model provider: records prompts, optionally applies a scripted edit."""

    name = "fake"

    def __init__(self, edit: Optional[Callable[[Path, str], None]] = None, model: str = "fake-no-model",
                 status: str = STATUS_OK, extra: Optional[dict[str, Any]] = None):
        self.edit = edit
        self.model = model
        self.status = status
        self.extra = dict(extra or {})
        self.prompts: list[dict[str, str]] = []

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str,
            controller: Optional[Path] = None) -> ProviderResult:
        self.prompts.append({"run_id": run_id, "prompt": prompt, "workdir": str(workdir)})
        if self.edit is not None:
            self.edit(Path(workdir), prompt)
        return ProviderResult(status=self.status, provider=self.name, model=self.model, model_calls=0,
                              timed_out=self.status == STATUS_TIMEOUT, extra=dict(self.extra))


class AgyPoolProvider:
    name = "agy"

    def __init__(self, model_env: str = "NEXUS_AGY_WORKER_MODEL"):
        self.model_env = model_env

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str,
            controller: Optional[Path] = None) -> ProviderResult:
        from types import SimpleNamespace

        from nexus.executors.agy_write_admission import paths_overlap
        from nexus.executors.worker_contract import WorkerOutcome, WorkerProviderUnavailable
        from nexus.executors.worker_registry import AgyWorkerAdapter
        from nexus.orchestrator.canonical_source_root import CANONICAL_SOURCE_ROOT
        from nexus.services.agy_account_pool import AgyAccountPoolManager
        from nexus.services.agy_failure_signals import agy_login_required
        from scripts.bench.real_world_task_runner import (
            AGY_BENCH_WORKER_ROLE,
            _agy_envelope_tokens,
            agy_bench_status,
        )

        observed: list[Any] = []
        adapter = AgyWorkerAdapter(
            use_installed_account_pool=True, result_observer=observed.append, require_account_pool=True
        )
        model = adapter._model()
        base = dict(provider=self.name, model=model)
        manager_path = AgyAccountPoolManager.resolve_manager_path()
        pool_switch = os.getenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", "").strip().lower()
        if pool_switch in ("0", "false", "no") or not manager_path or not Path(manager_path).is_file():
            return ProviderResult(status=STATUS_INFRA, infra_reason="AGY_NOT_AUTHENTICATED",
                                  failure_reason="agy account pool not installed or disabled", **base)
        if paths_overlap(Path(os.path.realpath(workdir)), Path(CANONICAL_SOURCE_ROOT).resolve()):
            raise ValueError("BARE work dir must be outside the Nexus checkout")
        preflight = adapter.preflight()
        if not preflight.authorized:
            return ProviderResult(status=STATUS_INFRA, infra_reason="AGY_RUNTIME_NOT_AUTHORIZED",
                                  failure_reason=str(preflight.reason), **base)
        if not preflight.ready:
            return ProviderResult(status=STATUS_INFRA, infra_reason="AGY_POOL_BUSY",
                                  failure_reason=str(preflight.reason), **base)
        started = time.monotonic()
        try:
            receipt = adapter.invoke(
                SimpleNamespace(task_id=run_id, maximum_provider_calls=1),
                SimpleNamespace(target_worktree=str(workdir)),
                prompt=prompt,
                timeout_seconds=float(timeout_seconds),
                worker_role=AGY_BENCH_WORKER_ROLE,
            )
        except WorkerProviderUnavailable as exc:
            return ProviderResult(status=STATUS_INFRA, infra_reason="AGY_POOL_BUSY", failure_reason=str(exc),
                                  wall_seconds=time.monotonic() - started, **base)
        wall = time.monotonic() - started
        sweep_failed = any(
            (result.timed_out and result.process_group_killed is not True)
            or (not result.timed_out and result.descendants_swept is not True)
            for result in observed
        )
        final = next((r for r in observed if r.stdout_sha256 == receipt.stdout_sha256), None)
        stdout = final.stdout.decode("utf-8", errors="replace") if final is not None else ""
        stderr = final.stderr.decode("utf-8", errors="replace") if final is not None else ""
        tokens, token_status, response = _agy_envelope_tokens(stdout)
        common = dict(
            extra=run_evidence(stdout, stderr, response),
            model_calls=int(receipt.provider_attempt_count or 0),
            total_tokens=tokens,
            token_status=token_status,
            exit_code=receipt.exit_code,
            account_alias_hash=str(receipt.account_alias_hash or ""),
            rotation_attempts=int(receipt.account_rotation_attempts or 0),
            wall_seconds=wall,
            **base,
        )
        completed = receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
        if sweep_failed:
            return ProviderResult(status=STATUS_INFRA, infra_reason="SWEEP_FAILED",
                                  failure_reason="agy descendants may survive", **common)
        if completed and not receipt.account_alias_hash:
            return ProviderResult(status=STATUS_INFRA, infra_reason="NO_LEASED_ACCOUNT",
                                  failure_reason="agy ran without a leased pool account", **common)
        if receipt.timed_out:
            return ProviderResult(status=STATUS_TIMEOUT, timed_out=True, failure_reason="timeout", **common)
        if not completed:
            login = final is not None and agy_login_required(stdout, stderr, stdout_is_envelope=True)
            status, _reset = agy_bench_status(receipt.failure_reason, login_prompt_seen=login)
            if status in INFRA_REASONS:
                return ProviderResult(status=STATUS_INFRA, infra_reason=status,
                                      failure_reason=str(receipt.failure_reason or ""), **common)
            return ProviderResult(status=STATUS_MODEL_FAILED, failure_reason=str(receipt.failure_reason or ""), **common)
        return ProviderResult(status=STATUS_OK, **common)


def run_evidence(stdout: str, stderr: str, response: str) -> dict[str, Any]:
    """What the run shows of its tool use (the json envelope has no full trace)."""
    denied: list[dict[str, Any]] = []
    try:
        from nexus.executors.agy_write_admission import top_level_json_objects

        for item in top_level_json_objects(stdout):
            for action in item.get("denied_actions") or []:
                if isinstance(action, dict):
                    denied.append({"action": action.get("action"), "display_name": action.get("display_name")})
    except Exception:  # pragma: no cover - evidence is best effort, never a failure
        pass
    return {"response_text": response[-20000:], "denied_actions": denied, "stderr_tail": stderr[-4000:]}


def claude_identity(executable: str, key_file: Optional[str] = None) -> dict[str, Any]:
    """CLI version (run inside the measurement sandbox) and a non-reversible key id.

    The key itself is never read here beyond hashing: the row keeps only the
    first 12 hex digits of its sha256, enough to tell which key a row used.
    """
    import hashlib
    import tempfile

    from nexus.executors.claude_measurement_worker import (
        MEASUREMENT_ANTHROPIC_ENV_FILE_ENV,
        measurement_claude_api_key,
        run_claude_once,
    )

    environ = {MEASUREMENT_ANTHROPIC_ENV_FILE_ENV: key_file} if key_file else {}
    key = measurement_claude_api_key(environ)
    with tempfile.TemporaryDirectory(prefix="m2721-claude-id-") as tmp:
        run = run_claude_once(executable, target=Path(tmp), prompt="", timeout_seconds=30.0, venv=None,
                              environ={**os.environ, **environ}, argv=("--version",))
    version = (run.result.stdout or run.result.stderr or b"").decode("utf-8", errors="replace").strip()
    return {
        "claude_executable": executable,
        "claude_version": version,
        "account": {
            "auth": "api_key" if key else "none",
            "api_key_sha256_12": hashlib.sha256(key.encode("utf-8")).hexdigest()[:12] if key else None,
        },
    }


def read_claude_trace(trace_dir: Path, task_id: str, stdout_sha256: str) -> dict[str, Any]:
    """The adapter's kept trace (summary) and sidecar for one run."""
    import json as _json

    from nexus.executors.claude_measurement_worker import summarize_stream_json

    base = Path(trace_dir) / task_id
    stream = base / f"{stdout_sha256}.stream.jsonl"
    side = base / f"{stdout_sha256}.run.json"
    summary = summarize_stream_json(stream.read_bytes() if stream.is_file() else b"")
    sidecar = _json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
    observed = None
    if stream.is_file():
        first = stream.read_text(encoding="utf-8").splitlines()[:1]
        try:
            observed = _json.loads(first[0]).get("fake_observed") if first else None
        except ValueError:
            observed = None
    return {"summary": summary, "sidecar": sidecar, "trace_path": str(stream) if stream.is_file() else None,
            "fake_observed": observed}


def _json_dumps(value: Any) -> str:
    import json as _json

    return _json.dumps(value, ensure_ascii=False, default=str)


def claude_usage_fields(summary: Any) -> dict[str, Any]:
    usage = summary.usage or {}
    fields = {key: int(usage.get(key) or 0) for key in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    fields["total_tokens"] = sum(fields.values())
    return fields


class ClaudeProvider:
    """BARE arm on ``claude-haiku-5-5`` through the Nexus measurement adapter itself.

    ``ClaudeMeasurementWorkerAdapter`` is exactly what the measurement Gateway's
    P1 worker runs, so the BARE arm gets the identical argv, isolated HOME and
    config dir, API key, Seatbelt profile, API-only proxy, task venv and
    time cap; only the prompt (no Nexus context) and the paths differ.
    """

    name = "claude"

    def __init__(self, executable: str, trace_dir: Path, key_file: Optional[str] = None,
                 identity: Optional[dict[str, Any]] = None):
        if not os.path.isabs(executable):
            raise ValueError("claude executable must be an absolute path")
        self.executable = executable
        self.trace_dir = Path(trace_dir).resolve()
        self.key_file = key_file
        self.identity = identity if identity is not None else claude_identity(executable, key_file)

    def environ(self, measurement_root: Optional[Path] = None) -> dict[str, str]:
        from nexus.executors.claude_measurement_worker import (
            MEASUREMENT_ANTHROPIC_ENV_FILE_ENV,
            MEASUREMENT_CLAUDE_BIN_ENV,
            MEASUREMENT_CLAUDE_ENV,
            MEASUREMENT_READ_ROOTS_ENV,
            MEASUREMENT_TRACE_DIR_ENV,
        )

        env = {key: value for key, value in os.environ.items() if key in ("USER", "LOGNAME", "LANG")}
        for passthrough in ("NEXUS_MEASUREMENT_CLAUDE_TIMEOUT_SECONDS", "NEXUS_MEASUREMENT_KEY_LABEL"):
            if os.environ.get(passthrough):
                env[passthrough] = os.environ[passthrough]
        if measurement_root is not None:
            # The BARE run's own fresh Controller is its measurement root (H2').
            env["NEXUS_MEASURE_EXTERNAL_TARGET_ROOT"] = str(Path(measurement_root).resolve())
        env.update({MEASUREMENT_CLAUDE_ENV: "1", MEASUREMENT_CLAUDE_BIN_ENV: self.executable,
                    MEASUREMENT_TRACE_DIR_ENV: str(self.trace_dir)})
        if self.key_file:
            env[MEASUREMENT_ANTHROPIC_ENV_FILE_ENV] = self.key_file
        if os.environ.get(MEASUREMENT_READ_ROOTS_ENV):
            env[MEASUREMENT_READ_ROOTS_ENV] = os.environ[MEASUREMENT_READ_ROOTS_ENV]
        return env

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str,
            controller: Optional[Path] = None) -> ProviderResult:
        from types import SimpleNamespace

        from nexus.executors.claude_measurement_worker import (
            CLAUDE_MEASUREMENT_MODEL,
            ClaudeMeasurementWorkerAdapter,
        )
        from nexus.executors.worker_contract import WorkerOutcome, WorkerProviderUnavailable

        workdir = Path(workdir).resolve()
        # Same contract shape as P1: controller root -> ../venv is the task venv.
        # Same contract shape as P1: target is a worktree of the Controller,
        # and <controller>/../venv is the task venv.
        contract = SimpleNamespace(task_id=run_id, target_worktree_root=str(workdir.parent),
                                   target_repo_root=str(workdir),
                                   controller_repo_root=str(controller or workdir))
        lease = SimpleNamespace(task_id=run_id, target_worktree=str(workdir))
        base = dict(provider=self.name, model=CLAUDE_MEASUREMENT_MODEL)
        started = time.monotonic()
        try:
            receipt = ClaudeMeasurementWorkerAdapter(
                environ=self.environ(Path(controller).parent if controller else None)
            ).invoke(
                contract, lease, prompt=prompt, timeout_seconds=float(timeout_seconds), model=CLAUDE_MEASUREMENT_MODEL
            )
        except WorkerProviderUnavailable as exc:
            return ProviderResult(status=STATUS_INFRA, infra_reason="CLAUDE_UNAVAILABLE", failure_reason=str(exc),
                                  wall_seconds=time.monotonic() - started, extra=dict(self.identity), **base)
        wall = time.monotonic() - started
        trace = read_claude_trace(self.trace_dir, run_id, receipt.stdout_sha256)
        summary = trace["summary"]
        usage = claude_usage_fields(summary)
        extra = {
            **self.identity,
            "trace_path": trace["trace_path"],
            "worker_span_ms": receipt.wall_time_ms,
            "num_turns": summary.num_turns,
            "total_cost_usd": summary.total_cost_usd,
            "usage": usage,
            "models_seen": list(summary.models_seen),
            "tool_calls": [{"name": call["name"]} for call in summary.tool_calls],
            "tool_call_count": len(summary.tool_calls),
            # Tool inputs (Bash commands, paths) for the UPSTREAM_LOOKUP scan.
            "tool_inputs_text": "\n".join(
                _json_dumps(call.get("input")) for call in summary.tool_calls
            )[:200000],
            "permission_denials": list(summary.permission_denials),
            "init": summary.init,
            "seatbelt_sha256": receipt.provider_permission_profile_sha256,
            "proxy_attempts": trace["sidecar"].get("proxy_attempts"),
            "env_keys": trace["sidecar"].get("env_keys"),
            "argv_sha256": trace["sidecar"].get("argv_sha256"),
            "served_models": list(summary.served_models),
            "cli_timeout_seconds": trace["sidecar"].get("cli_timeout_seconds"),
            "key_label": trace["sidecar"].get("key_label"),
            "api_key_sha256_12": trace["sidecar"].get("api_key_sha256_12"),
            "fake_observed": trace["fake_observed"],
            "receipt_failure_reason": receipt.failure_reason,
        }
        common = dict(model_calls=summary.num_turns or 0, total_tokens=usage["total_tokens"],
                      token_status="measured" if summary.result_seen else "missing_result",
                      exit_code=receipt.exit_code, wall_seconds=wall, extra=extra, **base)
        reason = str(receipt.failure_reason or "")
        if reason.startswith("claude_infra:"):
            return ProviderResult(status=STATUS_INFRA, infra_reason=reason.split(":", 1)[1].upper(),
                                  failure_reason=reason, **common)
        if receipt.timed_out:
            return ProviderResult(status=STATUS_TIMEOUT, timed_out=True, failure_reason="timeout", **common)
        if receipt.outcome != WorkerOutcome.EXECUTION_COMPLETED.value:
            return ProviderResult(status=STATUS_MODEL_FAILED, failure_reason=reason, **common)
        return ProviderResult(status=STATUS_OK, **common)


def build_provider(name: str, **options: Any) -> Provider:
    if name == "claude":
        return ClaudeProvider(options["claude_bin"], options["trace_dir"], options.get("key_file"))
    if name == "agy":
        return AgyPoolProvider()
    if name == "fake":
        return FakeProvider()
    raise ValueError(f"unknown provider {name!r}")
