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

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str) -> ProviderResult: ...


class FakeProvider:
    """Zero-model provider: records prompts, optionally applies a scripted edit."""

    name = "fake"

    def __init__(self, edit: Optional[Callable[[Path, str], None]] = None, model: str = "fake-no-model"):
        self.edit = edit
        self.model = model
        self.prompts: list[dict[str, str]] = []

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str) -> ProviderResult:
        self.prompts.append({"run_id": run_id, "prompt": prompt, "workdir": str(workdir)})
        if self.edit is not None:
            self.edit(Path(workdir), prompt)
        return ProviderResult(status=STATUS_OK, provider=self.name, model=self.model, model_calls=0)


class AgyPoolProvider:
    name = "agy"

    def __init__(self, model_env: str = "NEXUS_AGY_WORKER_MODEL"):
        self.model_env = model_env

    def run(self, *, prompt: str, workdir: Path, timeout_seconds: float, run_id: str) -> ProviderResult:
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
        tokens, token_status, _ = _agy_envelope_tokens(stdout)
        common = dict(
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


def build_provider(name: str) -> Provider:
    if name == "agy":
        return AgyPoolProvider()
    if name == "fake":
        return FakeProvider()
    raise ValueError(f"unknown provider {name!r}")
