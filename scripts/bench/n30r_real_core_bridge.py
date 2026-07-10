"""N30R-R1B genuine production executor bridge.

Invokes the real Nexus production path:
  CapabilityPlanner.plan()
  → planner-owned signal_snapshot (immutable)
  → LocalModelExecutorRequest
  → LocalModelExecutor.run(request, provider=...)
  → LocalHealPipelineCapabilityExecutor
  → HealPipeline.run()
  → candidate isolation
  → isolated apply
  → isolated verifier
  → LocalModelExecutorResponse
  → benchmark receipt projection

This bridge does NOT:
  - build production prompts
  - call model providers directly
  - parse model output
  - apply patches
  - run verifiers
  - implement semantic retry
  - implement candidate isolation
  - mutate the planner snapshot
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.bench.n30r_contracts import (
    N30RArmSpec,
    N30RTaskSpec,
    N30RTerminalStatus,
    sha256_str,
)
from scripts.bench.n30r_arm_adapters import ProviderFn, _read_fixture_source

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)
from nexus.services.local_heal.local_model_capability_wiring import project_planner_capabilities_for_local_executor


REAL_CORE_ARM_ID = "N30R_B_7B_REAL_CORE"
FROZEN_TOPOLOGY = "localheal_pipeline"
FROZEN_PLANNER_VERSION = "capability_planner_v1"
VALID_PLANNER_VERSIONS = {"capability_planner_v1", "capability_planner_v2"}

REQUIRED_PLANNER_FIELDS = frozenset({
    "planner_version",
    "selected_executor",
    "execution_topology",
    "protocol_mode",
    "executor_model",
    "ssd_route_map",
    "context_slimming_policy",
    "harness_relevance_policy",
    "research_isolation_policy",
})


@dataclass
class RealCoreBridgeResult:
    terminal_status: str
    raw_output: str
    patch_text: str
    apply_status: str
    verifier_status: str
    wall_time_sec: float
    timed_out: bool
    timeout_stage: str
    model_actual: str
    provider_actual: str
    prompt_text: str
    planner_called: bool
    planner_version: str
    route_truth_source: str
    signal_snapshot_sha256: str
    selected_executor: str
    execution_topology: str
    local_model_executor_called: bool
    production_local_path_used: bool
    legacy_adapter_called: bool
    model_call_count: int
    semantic_retry_count: int
    candidate_id: str
    candidate_workspace_id: str
    production_receipt_sha256: str
    execution_path_kind: str


def invoke_capability_planner(
    task_spec: N30RTaskSpec,
    source_code: str,
) -> dict[str, Any]:
    from nexus.engine.capability_planner import CapabilityPlanner
    planner = CapabilityPlanner()
    route = {
        "task_id": task_spec.task_id,
        "task_desc": task_spec.task_statement,
        "task_type": "swe_bounded_repair",
        "difficulty": "medium",
        "route_features": {},
    }
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = FROZEN_TOPOLOGY
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER"] = "ollama"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b-instruct"
    try:
        plan = planner.plan(
            task_desc=task_spec.task_statement,
            task_type="swe_bounded_repair",
            route=route,
            pillars={}, codeintel={}, phase_trace={},
            budget={"max_cost": 20}, skills=[],
        )
        return plan.signal_snapshot
    finally:
        for key in ("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                     "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                     "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"):
            os.environ.pop(key, None)


def validate_planner_snapshot(signal_snapshot: dict[str, Any]) -> list[str]:
    errors = []
    pv = signal_snapshot.get("planner_version")
    if not pv:
        errors.append("missing_planner_version")
    elif pv not in VALID_PLANNER_VERSIONS:
        errors.append(f"invalid_planner_version:{pv}")
    missing = [f for f in REQUIRED_PLANNER_FIELDS if f not in signal_snapshot]
    if missing:
        errors.append(f"incomplete_signal_snapshot:missing={missing}")
    topo = signal_snapshot.get("execution_topology")
    if topo != FROZEN_TOPOLOGY:
        errors.append(f"wrong_topology:{topo}")
    return errors


def _build_production_receipt_hash(response: LocalModelExecutorResponse) -> str:
    payload = {
        "invoked": response.invoked,
        "local_model_called": response.local_model_called,
        "candidate_hash": response.candidate_hash,
        "provider": response.provider,
        "model_name": response.model_name,
        "error": response.error,
        "timeout": response.timeout,
        "evidence_refs": list(response.evidence_refs),
        "cascade_stages_run": list(response.cascade_stages_run),
        "raw_model_metadata": response.raw_model_metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_real_core_bridge(
    task: N30RTaskSpec,
    arm: N30RArmSpec,
    provider: ProviderFn,
    seed: int,
    trial_index: int,
    run_id: str,
    timeout_limit: float = 120.0,
) -> RealCoreBridgeResult:
    start = time.time()

    orig_code = _read_fixture_source(task.source_relpath)

    try:
        signal_snapshot = invoke_capability_planner(task, orig_code)
    except Exception as e:
        wall_time = time.time() - start
        return _fail_closed_result(
            wall_time, "planner_invocation_failed", signal_snapshot={},
            planner_called=False, orig_code=orig_code, task=task, run_id=run_id,
            seed=seed, trial_index=trial_index,
        )

    snapshot_copy = copy.deepcopy(signal_snapshot)

    validation_errors = validate_planner_snapshot(signal_snapshot)
    if validation_errors:
        wall_time = time.time() - start
        return _fail_closed_result(
            wall_time, f"snapshot_validation_failed:{validation_errors}",
            signal_snapshot=signal_snapshot, planner_called=True,
            orig_code=orig_code, task=task, run_id=run_id,
            seed=seed, trial_index=trial_index,
        )

    assert signal_snapshot == snapshot_copy, "PLANNER SNAPSHOT WAS MUTATED"

    import tempfile as _tempfile
    workspace = _tempfile.mkdtemp(prefix=f"n30r-{task.task_id}-")
    target_relpath = task.source_relpath
    target_abs_path = os.path.join(workspace, target_relpath)
    os.makedirs(os.path.dirname(target_abs_path), exist_ok=True)
    with open(target_abs_path, "w", encoding="utf-8") as wf:
        wf.write(orig_code)

    projection = project_planner_capabilities_for_local_executor(signal_snapshot)
    if not projection.valid:
        wall_time = time.time() - start
        return _fail_closed_result(
            wall_time, f"capability_projection_invalid:{projection.failure_reason}",
            signal_snapshot=signal_snapshot, planner_called=True,
            orig_code=orig_code, task=task, run_id=run_id,
            seed=seed, trial_index=trial_index,
        )

    executor_request = LocalModelExecutorRequest(
        task_id=task.task_id,
        problem_statement=task.task_statement,
        repo_root=workspace,
        target_file=target_relpath,
        selected_capabilities=projection.selected_capabilities,
        evidence_refs=(f"n30r-{task.task_id}-ref",),
        receipt_context={
            "benchmark_run_id": run_id,
            "trial_index": trial_index,
            "seed": seed,
            "arm_id": REAL_CORE_ARM_ID,
        },
        route_context={
            "signal_snapshot": signal_snapshot,
            "verifier_command": list(task.verifier_command),
            "target_symbol": "",
            "difficulty": "medium",
        },
        model_name=signal_snapshot.get("executor_model", arm.model_name),
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
        execution_topology=FROZEN_TOPOLOGY,
    )

    def _wrapped_generate(req: LocalModelProviderRequest) -> str:
        return provider(req.model_name, "", req.prompt)

    injected_provider = InjectedLocalModelProvider(_wrapped_generate)

    executor_call_started = True
    try:
        executor_response = LocalModelExecutor.run(executor_request, provider=injected_provider)
    except Exception as e:
        wall_time = time.time() - start
        return _fail_closed_result(
            wall_time, f"executor_invocation_failed:{e}",
            signal_snapshot=signal_snapshot, planner_called=True,
            orig_code=orig_code, task=task, run_id=run_id,
            seed=seed, trial_index=trial_index,
            executor_invoked=True,
        )

    executor_call_completed = True

    if not isinstance(executor_response, LocalModelExecutorResponse):
        wall_time = time.time() - start
        return _fail_closed_result(
            wall_time, "non_executor_response_type",
            signal_snapshot=signal_snapshot, planner_called=True,
            orig_code=orig_code, task=task, run_id=run_id,
            seed=seed, trial_index=trial_index,
            executor_invoked=True,
        )

    meta = executor_response.raw_model_metadata if isinstance(executor_response.raw_model_metadata, dict) else {}

    pipeline_run_called = bool(meta.get("localheal_pipeline_run_called", False))
    pipeline_actual_execution = bool(meta.get("localheal_pipeline_actual_execution", False))
    topo_from_meta = meta.get("execution_topology", "")

    if not (pipeline_run_called and pipeline_actual_execution and topo_from_meta == FROZEN_TOPOLOGY):
        wall_time = time.time() - start
        return _fail_closed_result(
            wall_time, f"pipeline_execution_incomplete:run_called={pipeline_run_called},actual={pipeline_actual_execution},topo={topo_from_meta}",
            signal_snapshot=signal_snapshot, planner_called=True,
            orig_code=orig_code, task=task, run_id=run_id,
            seed=seed, trial_index=trial_index,
            executor_invoked=True,
        )

    production_receipt_hash = _build_production_receipt_hash(executor_response)

    raw_output = executor_response.candidate_patch or ""
    candidate_hash = executor_response.candidate_hash or ""
    verifier_status = meta.get("isolated_verifier_status", meta.get("verifier_result", "not_run"))
    semantic_retry_count = int(meta.get("semantic_retry_count", 0))

    candidate_isolation_attempted = bool(meta.get("candidate_isolation_attempted", False))
    candidate_output_isolated = bool(meta.get("candidate_output_isolated", False))
    candidate_hash_empty = not bool(candidate_hash)
    selected_candidate_hash = meta.get("selected_candidate_hash", "")
    candidate_isolated = (
        candidate_isolation_attempted
        and candidate_output_isolated
        and not candidate_hash_empty
        and bool(selected_candidate_hash)
    )

    terminal_status = N30RTerminalStatus.CONTRACT_INVALID.value
    if executor_response.invoked and raw_output:
        if verifier_status == "pass":
            terminal_status = N30RTerminalStatus.VERIFIED_SOLVE.value
        else:
            terminal_status = N30RTerminalStatus.VERIFIED_FAIL.value
    elif not executor_response.invoked:
        terminal_status = N30RTerminalStatus.CONTRACT_INVALID.value
    elif not raw_output:
        terminal_status = N30RTerminalStatus.INFRA_INVALID.value

    if executor_response.timeout:
        terminal_status = N30RTerminalStatus.MODEL_TIMEOUT.value

    wall_time = time.time() - start

    model_actual = executor_response.model_name or signal_snapshot.get("executor_model", "")
    provider_actual = executor_response.provider or signal_snapshot.get("executor_provider", "")

    route_truth_source = signal_snapshot.get("route_truth_source", "")

    prod_path_used = executor_response.invoked and pipeline_run_called and pipeline_actual_execution

    return RealCoreBridgeResult(
        terminal_status=terminal_status,
        raw_output=raw_output,
        patch_text=raw_output,
        apply_status="executor_applied" if raw_output else "none",
        verifier_status=verifier_status,
        wall_time_sec=round(wall_time, 3),
        timed_out=executor_response.timeout,
        timeout_stage="model_call" if executor_response.timeout else "",
        model_actual=model_actual,
        provider_actual=provider_actual,
        prompt_text="",
        planner_called=True,
        planner_version=signal_snapshot.get("planner_version", ""),
        route_truth_source=route_truth_source,
        signal_snapshot_sha256=sha256_str(json.dumps(signal_snapshot, sort_keys=True, default=str)),
        selected_executor=signal_snapshot.get("selected_executor", ""),
        execution_topology=FROZEN_TOPOLOGY,
        local_model_executor_called=True,
        production_local_path_used=prod_path_used,
        legacy_adapter_called=False,
        model_call_count=1 + semantic_retry_count,
        semantic_retry_count=semantic_retry_count,
        candidate_id=candidate_hash if not candidate_hash_empty else "",
        candidate_workspace_id=workspace,
        production_receipt_sha256=production_receipt_hash,
        execution_path_kind="nexus_production_localheal_pipeline",
    )


def _fail_closed_result(
    wall_time: float,
    reason: str,
    signal_snapshot: dict,
    planner_called: bool,
    orig_code: str,
    task: N30RTaskSpec,
    run_id: str,
    seed: int,
    trial_index: int,
    executor_invoked: bool = False,
) -> RealCoreBridgeResult:
    return RealCoreBridgeResult(
        terminal_status=N30RTerminalStatus.CONTRACT_INVALID.value,
        raw_output="", patch_text="", apply_status="none",
        verifier_status=reason,
        wall_time_sec=round(wall_time, 3), timed_out=False, timeout_stage="",
        model_actual=signal_snapshot.get("executor_model", ""),
        provider_actual=signal_snapshot.get("executor_provider", ""),
        prompt_text="",
        planner_called=planner_called,
        planner_version=signal_snapshot.get("planner_version", ""),
        route_truth_source=signal_snapshot.get("route_truth_source", ""),
        signal_snapshot_sha256=sha256_str(json.dumps(signal_snapshot, sort_keys=True, default=str)) if signal_snapshot else "",
        selected_executor=signal_snapshot.get("selected_executor", ""),
        execution_topology=signal_snapshot.get("execution_topology", ""),
        local_model_executor_called=executor_invoked,
        production_local_path_used=False,
        legacy_adapter_called=False,
        model_call_count=0, semantic_retry_count=0,
        candidate_id="", candidate_workspace_id="",
        production_receipt_sha256="",
        execution_path_kind="nexus_production_localheal_pipeline",
    )
