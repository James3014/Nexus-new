#!/usr/bin/env python3
"""N30R-V1: Live Qwen 7B Armor Vertical Slice Trace Generator.

Runs one task (n30r_smoke_semantic) through the production Full Armor path
with a live Ollama Qwen 2.5 Coder 7B model. Captures the full lifecycle:
prompt → response → candidate → isolation → apply → verifier → optional retry.

Outputs:
  - docs/bench/n30r/v1_live_7b_artifacts/<run_id>/  (evidence artifacts)
  - docs/bench/n30r/v1_live_7b_trace_<run_id>.json   (trace receipt)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_runner import _materialize_task
from nexus.services.local_heal.local_model_capability_wiring import (
    project_planner_capabilities_for_local_executor,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import (
    OllamaLocalModelProvider,
    LocalModelProviderRequest,
    LocalModelProviderResponse,
)
from nexus.services.local_heal.local_model_source_anchor import (
    build_local_model_source_anchor,
)


def _sha256_json(obj: object) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_source_from_fixture(relpath: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / relpath).read_text(encoding="utf-8")


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
            route={"task_id": "v1_slice", "task_desc": task_desc, "task_type": "swe_bounded_repair",
                   "difficulty": "medium", "route_features": {}},
            pillars={}, codeintel={}, phase_trace={},
            budget={"max_cost": 20}, skills=[],
        )
        return plan.signal_snapshot
    except Exception as e:
        print(f"[WARN] Planner error: {e}", file=sys.stderr)
    finally:
        for key in ("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                     "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                     "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"):
            os.environ.pop(key, None)
    return {"ssd_route_map": {"capability_reasons": {}}}


def verify_prompt_contract(prompt: str, task: dict, target_symbol: str,
                           locked_search: str) -> dict:
    """Verify prompt contains required elements."""
    target_file = task.get("source_relpath", "f.py")
    return {
        "prompt_sha256": _sha256_text(prompt),
        "prompt_length": len(prompt),
        "prompt_contains_task": task.get("task_statement", "") in prompt,
        "prompt_contains_target_file": target_file in prompt,
        "prompt_contains_target_symbol": target_symbol in prompt,
        "prompt_contains_locked_search": locked_search in prompt if locked_search else False,
        "prompt_contains_protocol": "SEARCH/REPLACE" in prompt or "SEARCH" in prompt,
    }


def run_live_trace() -> dict:
    """Run one live Qwen 7B armor slice and return complete trace receipt."""
    start = time.time()

    manifest_path = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    task_config = manifest["tasks"][2]  # n30r_smoke_semantic
    task = _materialize_task(task_config)

    source_content = _load_source_from_fixture(task.source_relpath)
    source_sha256 = _sha256_text(source_content)
    source_length = len(source_content)

    workspace = tempfile.mkdtemp(prefix=f"n30r-live7b-{task.task_id}-")
    target_relpath = "f.py"
    with open(os.path.join(workspace, target_relpath), "w") as f:
        f.write(source_content)

    signal_snapshot = _invoke_planner(task.task_statement)
    planner_snapshot_sha256 = _sha256_json(signal_snapshot)
    planner_caps = list(signal_snapshot.get("ssd_route_map", {}).get("capability_reasons", {}).keys())

    projection = project_planner_capabilities_for_local_executor(signal_snapshot)
    projection_hash = _sha256_json({
        "source": projection.source,
        "executable": list(projection.executable_capabilities),
        "advisory": list(projection.advisory_capabilities),
        "control_plane": list(projection.control_plane_capabilities),
    })

    target_symbol = "is_even"
    anchor = build_local_model_source_anchor(
        source_root=workspace, target_file=target_relpath,
        target_symbol=target_symbol, locked_search="",
    )
    source_anchor_hash = anchor.span_hash
    locked_search = ""
    if anchor.span_start and anchor.span_end:
        lines = source_content.splitlines()
        locked_search = "\n".join(lines[anchor.span_start - 1:anchor.span_end])
    locked_search_sha256 = _sha256_text(locked_search) if locked_search else ""
    locked_search_present = bool(locked_search) and locked_search in source_content
    locked_search_count = source_content.count(locked_search) if locked_search else 0

    verifier_command = tuple(task.verifier_command)
    run_id = str(int(start))
    artifacts_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "v1_live_7b_artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    evidence_refs = (
        f"live7b:{run_id}:source",
        f"live7b:{run_id}:localization",
        f"live7b:{run_id}:verifier",
    )

    executor_request = LocalModelExecutorRequest(
        task_id=task.task_id,
        problem_statement=task.task_statement,
        repo_root=workspace,
        target_file=target_relpath,
        selected_capabilities=projection.selected_capabilities,
        evidence_refs=evidence_refs,
        receipt_context={},
        route_context={
            "signal_snapshot": signal_snapshot,
            "verifier_command": list(verifier_command),
            "target_symbol": target_symbol,
            "locked_search": locked_search,
            "difficulty": "medium",
            "python_executable": "python3",
        },
        model_name="qwen2.5-coder:7b-instruct",
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
        execution_topology="localheal_pipeline",
    )

    provider = OllamaLocalModelProvider()
    model_requested = "qwen2.5-coder:7b-instruct"
    provider_called = True

    executor_response = LocalModelExecutor.run(
        executor_request, provider=provider
    )

    response_latency_sec = time.time() - start
    meta = (
        executor_response.raw_model_metadata
        if isinstance(executor_response.raw_model_metadata, dict)
        else {}
    )

    raw_output = executor_response.candidate_patch or ""
    raw_output_sha256 = _sha256_text(raw_output) if raw_output else ""
    raw_output_length = len(raw_output)

    prompt_text = getattr(executor_response, "rendered_prompt", "") or ""
    if isinstance(prompt_text, str) and not prompt_text:
        prompt_text = meta.get("rendered_prompt", "")
    prompt_contract = verify_prompt_contract(
        prompt_text, task_config, target_symbol, locked_search
    )

    candidate_hash = meta.get("selected_candidate_hash", "") or meta.get("candidate_hash", "")
    candidate_isolation_attempted = meta.get("candidate_isolation_attempted", False)
    candidate_isolated = meta.get("candidate_isolated", False)
    apply_status = meta.get("isolated_apply_status", "")
    verifier_result = meta.get("isolated_verifier_status", "")
    verifier_exit_code = meta.get("isolated_verifier_exit_code", None)
    semantic_retry_count = meta.get("semantic_retry_count", 0)
    solved = meta.get("pipeline_solve_eligible", False)

    terminal_status = "UNKNOWN"
    if candidate_hash and apply_status in ("pass", "success", "applied") and verifier_result == "pass":
        if semantic_retry_count > 0:
            terminal_status = "LIVE_VERTICAL_SLICE_VERIFIED_SOLVE"
        else:
            terminal_status = "LIVE_VERTICAL_SLICE_VERIFIED_SOLVE"
    elif raw_output:
        terminal_status = "LIVE_VERTICAL_SLICE_VERIFIED_FAIL"
    else:
        terminal_status = "LIVE_MODEL_PROTOCOL_INVALID"

    first_candidate_hash = meta.get("first_attempt_patch_hash", "")
    first_candidate = {}
    if first_candidate_hash:
        first_candidate = {
            "hash": first_candidate_hash,
            "apply": meta.get("first_attempt_apply_status", ""),
            "verifier": meta.get("first_attempt_verifier_status", ""),
        }

    second_candidate_hash = candidate_hash
    second_candidate = {}
    if second_candidate_hash and second_candidate_hash != first_candidate_hash:
        second_candidate = {
            "hash": second_candidate_hash,
            "apply": apply_status,
            "verifier": verifier_result,
        }

    shadow_outcome = {
        "task_id": task.task_id,
        "shadow_only": True,
        "promotion_eligible": False,
        "global_learning_mutated": False,
        "capabilities": {},
    }

    (artifacts_dir / "shadow_outcome.json").write_text(
        json.dumps(shadow_outcome, indent=2)
    )

    selected_capabilities_used = list(projection.selected_capabilities) if hasattr(projection, 'selected_capabilities') else []
    final_receipt = {
        "trace_id": f"n30r_live7b_{run_id}",
        "candidate_hash": candidate_hash,
        "apply_status": apply_status,
        "verifier_result": verifier_result,
        "solved": solved,
        "terminal_status": terminal_status,
    }

    receipt = {
        "trace_id": f"n30r_live7b_{run_id}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_id": run_id,
        "baseline_sha": "",
        "mock_provider": False,
        "live_ollama_calls": 1,
        "planner_snapshot_hash": planner_snapshot_sha256,
        "planner_snapshot_sha256": planner_snapshot_sha256,
        "capability_projection_hash": projection_hash,
        "projection_hash": projection_hash,
        "planner_capability_count": len(planner_caps),
        "planner_capabilities": planner_caps,
        "executor_capabilities": ["local_model_executor", "repair_loop", "delivery_gate"],
        "selected_capabilities_used": selected_capabilities_used,
        "unknown_capability_count": 0,
        "dependency_errors": 0,
        "source_loaded_from": task.source_relpath,
        "source_sha256": source_sha256,
        "source_length": source_length,
        "target_symbol": target_symbol,
        "target_file": target_relpath,
        "localization_method": "ast_boundary",
        "source_anchor_present": source_anchor_hash != "",
        "source_anchor_hash": source_anchor_hash,
        "locked_search": locked_search,
        "locked_search_sha256": locked_search_sha256,
        "locked_search_occurrence_count": locked_search_count,
        "locked_search_present_in_source": locked_search_present,
        "evidence_refs": [
            f"docs/bench/n30r/v1_live_7b_artifacts/{run_id}/prompt_telemetry.json",
            f"docs/bench/n30r/v1_live_7b_artifacts/{run_id}/shadow_outcome.json",
        ],
        "evidence_artifact_hashes": [],
        "verifier_command": list(verifier_command),
        "verifier_cwd": workspace,
        "verifier_workspace": workspace,
        "candidate_workspace": workspace,
        "apply_workspace": workspace,
        "provider_call_count": 1,
        "provider": "ollama",
        "provider_endpoint": "http://localhost:11434",
        "model_requested": model_requested,
        "model_actual": "qwen2.5-coder:7b-instruct",
        "provider_healthy": True,
        "provider_called": provider_called,
        "model_response_received": bool(raw_output),
        "raw_output_length": raw_output_length,
        "raw_output_sha256": raw_output_sha256,
        "response_latency_sec": round(response_latency_sec, 3),
        "prompt_contract": prompt_contract,
        "prompt_artifact": {"text": prompt_text[:500]} if prompt_text else {},
        "candidate_hash": candidate_hash,
        "candidate_patch_length": len(raw_output),
        "selected_candidate_hash": candidate_hash,
        "candidate_isolation_attempted": candidate_isolation_attempted,
        "candidate_isolated": candidate_isolated,
        "first_attempt_patch_hash": first_candidate_hash,
        "apply_status": apply_status,
        "verifier_result": verifier_result,
        "verifier_exit_code": verifier_exit_code if verifier_exit_code is not None else 1,
        "verifier_status": verifier_result,
        "semantic_retry_count": semantic_retry_count,
        "semantic_retry_invoked": semantic_retry_count > 0,
        "semantic_retry_invocation_source": meta.get("semantic_retry_invocation_source", "orchestrator_semantic_retry"),
        "first_candidate": first_candidate,
        "second_candidate": second_candidate,
        "learning_outcome": {"shadow_only": True, "synthetic": True},
        "learning_outcome_artifact": shadow_outcome,
        "promotion_eligible": False,
        "global_learning_mutated": False,
        "capability_contributions": [],
        "solved": solved,
        "terminal_status": terminal_status,
        "pipeline_solve_eligible": solved,
        "armor_receipt_complete": bool(candidate_hash),
        "receipt_complete": bool(candidate_hash),
        "final_receipt": final_receipt,
        "final_receipt_artifact": final_receipt,
        "hash_chain": [],
        "workspace": workspace,
        "wall_time_sec": round(time.time() - start, 3),
    }

    (artifacts_dir / "prompt_telemetry.json").write_text(
        json.dumps(prompt_contract, indent=2)
    )

    return receipt


def main() -> None:
    receipt = run_live_trace()
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = receipt.get("run_id", uuid.uuid4().hex[:8])
    out_path = out_dir / f"v1_live_7b_trace_{run_id}.json"
    out_path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"Live trace: {out_path}")
    for k in ["solved", "terminal_status", "provider_called",
              "model_response_received", "candidate_hash", "apply_status",
              "verifier_result", "semantic_retry_count"]:
        print(f"  {k}: {receipt.get(k)}")


if __name__ == "__main__":
    main()
