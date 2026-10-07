"""Canonical provider-effect lifecycle for bounded research experiments.

This module deliberately owns only effect admission, durable operation identity,
same-effect reconciliation, and immutable response/receipt publication. It owns
no model/provider selection, retry policy, semantic verification, acceptance,
merge, release, or production authority.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.research.experiment_run_guard import (
    ExperimentRunContract,
    ExperimentRunGuard,
    ExperimentRunLease,
    RunEffectConflict,
    write_immutable_artifact,
)

_RUNNING_STATES = {"RUNNING", "QUEUED"}
_UNKNOWN_STATE = "OUTCOME_UNKNOWN"


class ConfirmedNoEffectBeforeLaunch(RuntimeError):
    """The caller proved that provider effect creation did not occur."""


class ExperimentEffectOutcomeUnknown(RuntimeError):
    """The same provider effect remains unresolved and must not be replaced."""


@dataclass(frozen=True)
class EffectArtifacts:
    response_path: Path
    response_bytes: bytes
    receipt_path: Path
    receipt_bytes: bytes


@dataclass(frozen=True)
class ExperimentEffectResult:
    operation_id: str
    terminal_record: dict[str, Any]
    response_sha256: str
    receipt_sha256: str
    response_publication: str
    receipt_publication: str


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ExperimentEffectController:
    """Execute or reconcile exactly one effect for one acquired run lease."""

    def __init__(
        self,
        lease: ExperimentRunLease,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lease = lease
        self._sleep = sleep
        self._monotonic = monotonic

    def run(
        self,
        *,
        launch_effect: Callable[[], str],
        read_status: Callable[[str], Mapping[str, Any]],
        reconcile_effect: Callable[[str], Mapping[str, Any]],
        build_artifacts: Callable[[Mapping[str, Any]], EffectArtifacts],
        poll_interval_seconds: float = 15.0,
        wait_timeout_seconds: float = 720.0,
    ) -> ExperimentEffectResult:
        operation_id = self._admit_or_resume(launch_effect)
        terminal = self._wait_for_terminal(
            operation_id=operation_id,
            read_status=read_status,
            reconcile_effect=reconcile_effect,
            poll_interval_seconds=poll_interval_seconds,
            wait_timeout_seconds=wait_timeout_seconds,
        )
        artifacts = build_artifacts(terminal)
        response_publication = write_immutable_artifact(
            artifacts.response_path,
            artifacts.response_bytes,
        )
        receipt_publication = write_immutable_artifact(
            artifacts.receipt_path,
            artifacts.receipt_bytes,
        )
        response_sha256 = _sha256_bytes(artifacts.response_bytes)
        receipt_sha256 = _sha256_bytes(artifacts.receipt_bytes)
        self._lease.mark_terminal(
            operation_id=operation_id,
            response_sha256=response_sha256,
            receipt_sha256=receipt_sha256,
        )
        return ExperimentEffectResult(
            operation_id=operation_id,
            terminal_record=dict(terminal),
            response_sha256=response_sha256,
            receipt_sha256=receipt_sha256,
            response_publication=response_publication,
            receipt_publication=receipt_publication,
        )

    def _admit_or_resume(self, launch_effect: Callable[[], str]) -> str:
        effect = self._lease.effect_record()
        state = effect["state"]
        if state == "TERMINAL":
            raise RunEffectConflict("RUN_EFFECT_ALREADY_TERMINAL")
        if state in {"STARTED", _UNKNOWN_STATE}:
            operation_id = effect.get("operation_id")
            if not operation_id:
                raise ExperimentEffectOutcomeUnknown(
                    "RUN_EFFECT_OPERATION_UNKNOWN_RECONCILIATION_ONLY"
                )
            return str(operation_id)
        if state != "NOT_STARTED":
            raise RunEffectConflict("RUN_EFFECT_STATE_INVALID")

        self._lease.begin_effect()
        try:
            operation_id = launch_effect()
        except ConfirmedNoEffectBeforeLaunch:
            self._lease.mark_no_effect()
            raise
        except BaseException:
            self._lease.mark_outcome_unknown()
            raise
        if not isinstance(operation_id, str) or not operation_id.strip():
            self._lease.mark_outcome_unknown()
            raise ExperimentEffectOutcomeUnknown("PROVIDER_OPERATION_ID_MISSING")
        self._lease.bind_operation(operation_id)
        return operation_id

    def _wait_for_terminal(
        self,
        *,
        operation_id: str,
        read_status: Callable[[str], Mapping[str, Any]],
        reconcile_effect: Callable[[str], Mapping[str, Any]],
        poll_interval_seconds: float,
        wait_timeout_seconds: float,
    ) -> dict[str, Any]:
        if poll_interval_seconds < 0 or wait_timeout_seconds <= 0:
            raise ValueError("invalid effect wait bounds")
        deadline = self._monotonic() + wait_timeout_seconds
        while True:
            observed = dict(read_status(operation_id))
            status = observed.get("status")
            if status not in _RUNNING_STATES:
                break
            if self._monotonic() >= deadline:
                self._lease.mark_outcome_unknown(operation_id=operation_id)
                raise ExperimentEffectOutcomeUnknown("PROVIDER_EFFECT_WAIT_TIMEOUT")
            self._sleep(poll_interval_seconds)

        if observed.get("status") == _UNKNOWN_STATE:
            observed = dict(reconcile_effect(operation_id))
        if observed.get("status") == _UNKNOWN_STATE:
            self._lease.mark_outcome_unknown(operation_id=operation_id)
            raise ExperimentEffectOutcomeUnknown("PROVIDER_EFFECT_OUTCOME_UNKNOWN")
        if observed.get("operation_id") not in {None, operation_id}:
            self._lease.mark_outcome_unknown(operation_id=operation_id)
            raise ExperimentEffectOutcomeUnknown("PROVIDER_OPERATION_IDENTITY_MISMATCH")
        return observed


def run_guarded_effect(
    *,
    state_root: Path,
    contract: ExperimentRunContract,
    launch_effect: Callable[[], str],
    read_status: Callable[[str], Mapping[str, Any]],
    reconcile_effect: Callable[[str], Mapping[str, Any]],
    build_artifacts: Callable[[Mapping[str, Any]], EffectArtifacts],
    poll_interval_seconds: float = 15.0,
    wait_timeout_seconds: float = 720.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> ExperimentEffectResult:
    """Canonical shared entry point for one guarded provider effect.

    Callers supply provider-specific launch/status/reconcile functions and artifact
    construction only. This function owns the run lease and therefore makes a
    second same-run provider start impossible once the effect slot is consumed.
    """

    guard = ExperimentRunGuard(state_root)
    with guard.acquire(contract) as lease:
        return ExperimentEffectController(lease, sleep=sleep, monotonic=monotonic).run(
            launch_effect=launch_effect,
            read_status=read_status,
            reconcile_effect=reconcile_effect,
            build_artifacts=build_artifacts,
            poll_interval_seconds=poll_interval_seconds,
            wait_timeout_seconds=wait_timeout_seconds,
        )
