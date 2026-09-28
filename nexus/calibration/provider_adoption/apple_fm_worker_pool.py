"""Experimental bounded Apple Foundation Models read-only worker pool.

This module is calibration infrastructure only. It does not own routing,
Workforce Admission, fallback selection, mutation, acceptance, or production
authority.
"""

from __future__ import annotations

import concurrent.futures
import json
import math
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from nexus.calibration.provider_adoption.apple_fm_adapter import (
    APPLE_FM_BINARY,
    AppleFMCandidateAdapter,
)

APPLE_FM_WORKER_POOL_SCHEMA = "nexus.provider_experiment.apple_fm_worker_pool.v1"
DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 4
MAX_PROMPT_CHARS = 4000
NETWORK_DENY_PROFILE = "(version 1)(allow default)(deny network*)"

BLOCKED_RISK_TAGS = frozenset({
    "architecture_judgment",
    "mutation",
    "retry_attempt_semantics",
    "state_transition_reasoning",
})


class AppleFMTaskKind(str, Enum):
    CLASSIFICATION = "classification"
    LITERAL_EXTRACTION = "literal_extraction"
    STRUCTURED_JSON = "structured_json"


@dataclass(frozen=True)
class AppleFMReadOnlyTask:
    task_id: str
    kind: AppleFMTaskKind
    prompt: str
    schema: dict[str, Any] | None = None
    allowed_outputs: tuple[str, ...] = ()
    output_pattern: str | None = None
    risk_tags: tuple[str, ...] = ()

    def validate(self) -> None:
        if not isinstance(self.kind, AppleFMTaskKind):
            raise ValueError(f"{self.task_id}: kind must be an AppleFMTaskKind")
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.prompt.strip():
            raise ValueError(f"{self.task_id}: prompt must be non-empty")
        if len(self.prompt) > MAX_PROMPT_CHARS:
            raise ValueError(
                f"{self.task_id}: prompt exceeds bounded small-task limit "
                f"({len(self.prompt)} > {MAX_PROMPT_CHARS})"
            )
        blocked = sorted(BLOCKED_RISK_TAGS.intersection(self.risk_tags))
        if blocked:
            raise ValueError(
                f"{self.task_id}: risk tags are not eligible for Apple FM pool: {blocked}"
            )
        if self.kind == AppleFMTaskKind.CLASSIFICATION:
            if not self.allowed_outputs:
                raise ValueError(f"{self.task_id}: classification requires allowed_outputs")
            if self.output_pattern is not None or self.schema is not None:
                raise ValueError(f"{self.task_id}: classification accepts allowed_outputs only")
        if self.kind == AppleFMTaskKind.LITERAL_EXTRACTION:
            if self.output_pattern is None:
                raise ValueError(f"{self.task_id}: literal_extraction requires output_pattern")
            if self.allowed_outputs or self.schema is not None:
                raise ValueError(f"{self.task_id}: literal_extraction accepts output_pattern only")
            try:
                re.compile(self.output_pattern)
            except re.error as exc:
                raise ValueError(f"{self.task_id}: invalid output_pattern: {exc}") from exc
        if self.kind == AppleFMTaskKind.STRUCTURED_JSON and self.schema is None:
            raise ValueError(f"{self.task_id}: structured_json requires a schema")
        if self.kind == AppleFMTaskKind.STRUCTURED_JSON:
            assert self.schema is not None
            try:
                Draft202012Validator.check_schema(self.schema)
            except SchemaError as exc:
                raise ValueError(f"{self.task_id}: invalid JSON schema: {exc.message}") from exc
        if self.kind == AppleFMTaskKind.STRUCTURED_JSON:
            if self.allowed_outputs or self.output_pattern is not None:
                raise ValueError(f"{self.task_id}: structured_json accepts schema only")


@dataclass(frozen=True)
class AppleFMTaskResult:
    task_id: str
    ok: bool
    output_text: str
    latency_ms: int
    output_contract_valid: bool
    semantic_correctness_status: str
    error_code: str | None
    needs_escalation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "ok": self.ok,
            "output_text": self.output_text,
            "latency_ms": self.latency_ms,
            "output_contract_valid": self.output_contract_valid,
            "semantic_correctness_status": self.semantic_correctness_status,
            "error_code": self.error_code,
            "needs_escalation": self.needs_escalation,
        }


@dataclass(frozen=True)
class AppleFMWorkerPoolReceipt:
    schema: str
    requested_concurrency: int
    effective_concurrency: int
    total_tasks: int
    contract_valid_tasks: int
    contract_invalid_tasks: int
    wall_time_ms: int
    throughput_rps: float
    p50_latency_ms: int
    p95_latency_ms: int
    network_denial_required: bool
    automatic_fallback: str
    claim_ceiling: str
    results: tuple[AppleFMTaskResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "requested_concurrency": self.requested_concurrency,
            "effective_concurrency": self.effective_concurrency,
            "total_tasks": self.total_tasks,
            "contract_valid_tasks": self.contract_valid_tasks,
            "contract_invalid_tasks": self.contract_invalid_tasks,
            "wall_time_ms": self.wall_time_ms,
            "throughput_rps": self.throughput_rps,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "network_denial_required": self.network_denial_required,
            "automatic_fallback": self.automatic_fallback,
            "claim_ceiling": self.claim_ceiling,
            "results": [result.to_dict() for result in self.results],
        }


class AppleFMReadOnlyWorkerPool:
    """Bounded experimental pool for small read-only Apple FM tasks."""

    def __init__(
        self,
        *,
        binary_path: str = APPLE_FM_BINARY,
        sandbox_exec_path: str = "/usr/bin/sandbox-exec",
        default_concurrency: int = DEFAULT_CONCURRENCY,
        max_concurrency: int = MAX_CONCURRENCY,
        timeout_s: float = 30.0,
        require_network_denial: bool = True,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        environment_preflight: Callable[[], tuple[bool, str]] | None = None,
    ) -> None:
        if default_concurrency < 1:
            raise ValueError("default_concurrency must be >= 1")
        if max_concurrency < default_concurrency:
            raise ValueError("max_concurrency must be >= default_concurrency")
        if max_concurrency > MAX_CONCURRENCY:
            raise ValueError(f"max_concurrency cannot exceed calibrated cap {MAX_CONCURRENCY}")
        self.binary_path = binary_path
        self.sandbox_exec_path = sandbox_exec_path
        self.default_concurrency = default_concurrency
        self.max_concurrency = max_concurrency
        self.timeout_s = timeout_s
        self.require_network_denial = require_network_denial
        self._command_runner = command_runner
        self._environment_preflight = environment_preflight

    def _preflight(self) -> None:
        if self._environment_preflight is not None:
            blocked, reason = self._environment_preflight()
        else:
            blocked, reason = AppleFMCandidateAdapter(self.binary_path).is_environment_blocked()
        if blocked:
            raise RuntimeError(reason)
        if self.require_network_denial and not os.path.isfile(self.sandbox_exec_path):
            raise RuntimeError(
                f"NETWORK_DENIAL_UNAVAILABLE: sandbox executable missing at {self.sandbox_exec_path}"
            )

    def _base_argv(self) -> list[str]:
        fm_argv = [self.binary_path, "respond", "--no-stream", "--greedy"]
        if not self.require_network_denial:
            return fm_argv
        return [
            self.sandbox_exec_path,
            "-p",
            NETWORK_DENY_PROFILE,
            *fm_argv,
        ]

    def _execute_one(self, task: AppleFMReadOnlyTask) -> AppleFMTaskResult:
        started = time.perf_counter()
        try:
            argv = self._base_argv()
            if task.kind == AppleFMTaskKind.STRUCTURED_JSON:
                assert task.schema is not None
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".json",
                    delete=True,
                    encoding="utf-8",
                ) as schema_file:
                    json.dump(task.schema, schema_file, sort_keys=True)
                    schema_file.flush()
                    completed = self._command_runner(
                        [*argv, "--schema", schema_file.name, task.prompt],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_s,
                    )
            else:
                completed = self._command_runner(
                    [*argv, task.prompt],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            output = completed.stdout.strip()
            if completed.returncode != 0:
                return AppleFMTaskResult(
                    task_id=task.task_id,
                    ok=False,
                    output_text=output,
                    latency_ms=latency_ms,
                    output_contract_valid=False,
                    semantic_correctness_status="NOT_EVALUATED",
                    error_code=f"FM_EXIT_{completed.returncode}",
                    needs_escalation=True,
                )
            if not output:
                return AppleFMTaskResult(
                    task_id=task.task_id,
                    ok=False,
                    output_text="",
                    latency_ms=latency_ms,
                    output_contract_valid=False,
                    semantic_correctness_status="NOT_EVALUATED",
                    error_code="EMPTY_OUTPUT",
                    needs_escalation=True,
                )

            output_contract_valid = True
            error_code: str | None = None
            if task.kind == AppleFMTaskKind.CLASSIFICATION:
                if output not in task.allowed_outputs:
                    output_contract_valid = False
                    error_code = "OUTPUT_NOT_IN_ALLOWED_SET"
            elif task.kind == AppleFMTaskKind.LITERAL_EXTRACTION:
                assert task.output_pattern is not None
                if re.fullmatch(task.output_pattern, output) is None:
                    output_contract_valid = False
                    error_code = "OUTPUT_PATTERN_MISMATCH"
            elif task.kind == AppleFMTaskKind.STRUCTURED_JSON:
                assert task.schema is not None
                try:
                    payload = json.loads(output)
                except json.JSONDecodeError:
                    output_contract_valid = False
                    error_code = "INVALID_JSON"
                else:
                    try:
                        Draft202012Validator(task.schema).validate(payload)
                    except ValidationError:
                        output_contract_valid = False
                        error_code = "SCHEMA_VIOLATION"
            return AppleFMTaskResult(
                task_id=task.task_id,
                ok=output_contract_valid,
                output_text=output,
                latency_ms=latency_ms,
                output_contract_valid=output_contract_valid,
                semantic_correctness_status="NOT_EVALUATED",
                error_code=error_code,
                needs_escalation=not output_contract_valid,
            )
        except subprocess.TimeoutExpired:
            return AppleFMTaskResult(
                task_id=task.task_id,
                ok=False,
                output_text="",
                latency_ms=int(self.timeout_s * 1000),
                output_contract_valid=False,
                semantic_correctness_status="NOT_EVALUATED",
                error_code="PROVIDER_TIMEOUT",
                needs_escalation=True,
            )
        except Exception as exc:
            return AppleFMTaskResult(
                task_id=task.task_id,
                ok=False,
                output_text="",
                latency_ms=int((time.perf_counter() - started) * 1000),
                output_contract_valid=False,
                semantic_correctness_status="NOT_EVALUATED",
                error_code=f"INTERNAL_ERROR:{type(exc).__name__}",
                needs_escalation=True,
            )

    @staticmethod
    def _percentile(values: Sequence[int], percentile: float) -> int:
        ordered = sorted(values)
        rank = max(1, math.ceil(percentile * len(ordered)))
        return ordered[rank - 1]

    def run_batch(
        self,
        tasks: Sequence[AppleFMReadOnlyTask],
        *,
        concurrency: int | None = None,
    ) -> AppleFMWorkerPoolReceipt:
        frozen_tasks = tuple(tasks)
        if not frozen_tasks:
            raise ValueError("tasks must be non-empty")
        seen: set[str] = set()
        for task in frozen_tasks:
            task.validate()
            if task.task_id in seen:
                raise ValueError(f"duplicate task_id: {task.task_id}")
            seen.add(task.task_id)

        requested = self.default_concurrency if concurrency is None else concurrency
        if requested < 1 or requested > self.max_concurrency:
            raise ValueError(
                f"concurrency must be between 1 and {self.max_concurrency}; got {requested}"
            )

        self._preflight()
        started = time.perf_counter()
        ordered_results: list[AppleFMTaskResult | None] = [None] * len(frozen_tasks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=requested) as executor:
            future_to_index = {
                executor.submit(self._execute_one, task): index
                for index, task in enumerate(frozen_tasks)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                ordered_results[future_to_index[future]] = future.result()

        wall_time_ms = int((time.perf_counter() - started) * 1000)
        results = tuple(result for result in ordered_results if result is not None)
        if len(results) != len(frozen_tasks):
            raise RuntimeError("worker pool lost one or more task results")
        latencies = [result.latency_ms for result in results]
        successful = sum(result.ok for result in results)
        return AppleFMWorkerPoolReceipt(
            schema=APPLE_FM_WORKER_POOL_SCHEMA,
            requested_concurrency=requested,
            effective_concurrency=requested,
            total_tasks=len(results),
            contract_valid_tasks=successful,
            contract_invalid_tasks=len(results) - successful,
            wall_time_ms=wall_time_ms,
            throughput_rps=round(len(results) / max(wall_time_ms / 1000.0, 0.001), 3),
            p50_latency_ms=self._percentile(latencies, 0.50),
            p95_latency_ms=self._percentile(latencies, 0.95),
            network_denial_required=self.require_network_denial,
            automatic_fallback="DISABLED",
            claim_ceiling="EXPERIMENT_ONLY",
            results=results,
        )
