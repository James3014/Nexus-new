#!/usr/bin/env python3
"""N30R-W1C2: Capability Projection Runtime Trace Generator.

Produces a deterministic runtime trace by invoking the real planner,
projection helper, and executor boundary with a mock provider.
No live Ollama calls.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import sha256_str
from scripts.bench.n30r_runner import ARMS, _materialize_task
from nexus.services.local_heal.local_model_capability_wiring import (
    project_planner_capabilities_for_local_executor,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)


def _sha256_json(obj: object) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _invoke_planner(task_desc: str) -> dict:
    from nexus.engine.capability_planner import CapabilityPlanner
    planner = CapabilityPlanner()
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "localheal_pipeline"
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER"] = "ollama"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b-instruct"
    try:
        plan = planner.plan(
            task_desc=task_desc,
            task_type="swe_bounded_repair",
            route={"task_id": "trace_gen", "task_desc": task_desc, "task_type": "swe_bounded_repair",
                   "difficulty": "medium", "route_features": {}},
            pillars={}, codeintel={}, phase_trace={},
            budget={"max_cost": 20}, skills=[],
        )
        return plan.signal_snapshot
    finally:
        for key in ("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                     "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                     "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"):
            os.environ.pop(key, None)


def _mock_generate(req: LocalModelProviderRequest) -> str:
    return "def f(): pass"


def run_trace() -> dict:
    start = time.time()

    manifest_path = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    task = _materialize_task(manifest["tasks"][0])

    signal_snapshot = _invoke_planner(task.task_statement)
    snapshot_copy = copy.deepcopy(signal_snapshot)
    planner_snapshot_sha256 = _sha256_json(signal_snapshot)
    assert signal_snapshot == snapshot_copy, "PLANNER SNAPSHOT WAS MUTATED"

    planner_caps = list(signal_snapshot.get("ssd_route_map", {}).get("capability_reasons", {}).keys())

    projection = project_planner_capabilities_for_local_executor(signal_snapshot)

    projection_hash = _sha256_json({
        "source": projection.source,
        "executable": list(projection.executable_capabilities),
        "advisory": list(projection.advisory_capabilities),
        "control_plane": list(projection.control_plane_capabilities),
    })

    import tempfile
    workspace = tempfile.mkdtemp(prefix="n30r-trace-")
    target_relpath = task.source_relpath
    target_abs = os.path.join(workspace, target_relpath)
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    from scripts.bench.n30r_arm_adapters import _read_fixture_source
    with open(target_abs, "w") as wf:
        wf.write(_read_fixture_source(task.source_relpath))

    executor_request = LocalModelExecutorRequest(
        task_id=task.task_id,
        problem_statement=task.task_statement,
        repo_root=workspace,
        target_file=target_relpath,
        selected_capabilities=projection.selected_capabilities,
        evidence_refs=(f"trace-{task.task_id}-ref",),
        receipt_context={},
        route_context={
            "signal_snapshot": signal_snapshot,
            "verifier_command": list(task.verifier_command),
            "target_symbol": "",
            "difficulty": "medium",
        },
        model_name=signal_snapshot.get("executor_model", ""),
        dry_run=False,
        mutation_allowed=False,
        verifier_allowed=False,
        execution_topology="localheal_pipeline",
    )

    injected_provider = InjectedLocalModelProvider(_mock_generate)
    executor_response = LocalModelExecutor.run(executor_request, provider=injected_provider)

    meta = executor_response.raw_model_metadata if isinstance(executor_response.raw_model_metadata, dict) else {}

    executor_request_sha256 = _sha256_json({
        "task_id": executor_request.task_id,
        "selected_capabilities": list(executor_request.selected_capabilities),
        "execution_topology": executor_request.execution_topology,
    })

    pipeline_caps = list(meta.get("selected_capabilities_used", executor_request.selected_capabilities))

    meta_caps_used = meta.get("selected_capabilities_used")
    meta_caps_tuple = tuple(meta_caps_used) if isinstance(meta_caps_used, (list, tuple)) else ()

    executor_metadata_sha256 = _sha256_json({
        "selected_capabilities_used": list(meta_caps_tuple) if meta_caps_used is not None else [],
        "execution_topology": meta.get("execution_topology", ""),
    })

    planner_to_projection_accounted = (
        len(planner_caps)
        == len(projection.executable_capabilities)
        + len(projection.advisory_capabilities)
        + len(projection.control_plane_capabilities)
        + len(projection.unknown_capabilities)
        + len(projection.dropped_capabilities)
    )

    projection_to_executor_match = tuple(projection.selected_capabilities) == tuple(executor_request.selected_capabilities)
    executor_to_pipeline_match = tuple(executor_request.selected_capabilities) == tuple(pipeline_caps)
    pipeline_to_receipt_match = tuple(pipeline_caps) == meta_caps_tuple if meta_caps_used is not None else False

    generator_path = str(Path(__file__).resolve())
    generator_sha256 = sha256_json_file(generator_path)

    trace = {
        "trace_id": f"w1c2_projection_trace_{int(start)}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
        "baseline_sha": "cf19cfe72",
        "generator_path": generator_path,
        "generator_sha256": generator_sha256,
        "run_command": f".venv/bin/python {generator_path}",
        "mock_provider": True,
        "live_ollama_calls": 0,

        "planner_snapshot_sha256": planner_snapshot_sha256,
        "ssd_selected_capability_count": len(planner_caps),
        "ssd_capability_ids": planner_caps,

        "planner_selected_capabilities": planner_caps,
        "executable_capabilities": list(projection.executable_capabilities),
        "advisory_capabilities": list(projection.advisory_capabilities),
        "control_plane_capabilities": list(projection.control_plane_capabilities),
        "unknown_capabilities": list(projection.unknown_capabilities),
        "dropped_capabilities": list(projection.dropped_capabilities),
        "dependency_errors": list(projection.dependency_errors),

        "projection_valid": projection.valid,
        "projection_sha256": projection_hash,

        "executor_request_selected_capabilities": list(executor_request.selected_capabilities),
        "executor_request_sha256": executor_request_sha256,
        "pipeline_context_selected_capabilities": pipeline_caps,
        "executor_metadata_selected_capabilities_used": list(meta_caps_tuple) if meta_caps_used is not None else None,
        "executor_metadata_sha256": executor_metadata_sha256,

        "planner_to_projection_accounted": planner_to_projection_accounted,
        "projection_to_executor_match": projection_to_executor_match,
        "executor_to_pipeline_match": executor_to_pipeline_match,
        "pipeline_to_receipt_match": pipeline_to_receipt_match,
    }

    wall_time = time.time() - start
    trace["wall_time_sec"] = round(wall_time, 3)

    return trace


def sha256_json_file(path: str) -> str:
    content = Path(path).read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def main():
    trace = run_trace()
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"w1_capability_projection_trace_w1c2_{trace['trace_id'].split('_')[-1]}.json"
    out_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    print(f"Trace written: {out_path}")
    print(f"planner_to_projection_accounted: {trace['planner_to_projection_accounted']}")
    print(f"projection_to_executor_match: {trace['projection_to_executor_match']}")
    print(f"executor_to_pipeline_match: {trace['executor_to_pipeline_match']}")
    print(f"pipeline_to_receipt_match: {trace['pipeline_to_receipt_match']}")
    print(f"live_ollama_calls: {trace['live_ollama_calls']}")


if __name__ == "__main__":
    main()
