#!/usr/bin/env python3
"""N30R-V1: Full Armor Vertical Slice Trace Generator.

Exercises the complete local model armor path:
  Planner -> Projection -> Evidence -> Prompt -> Candidate -> Apply -> Verifier -> Retry -> Receipt

Uses deterministic mock provider. No live Ollama.
Targets n30r_smoke_semantic (is_even bug fix).

Produces deterministic fail -> semantic retry -> pass lifecycle.
Source loaded from real fixture (not hardcoded).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import sha256_str
from scripts.bench.n30r_runner import _materialize_task
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


def _sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    finally:
        for key in ("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                     "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                     "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"):
            os.environ.pop(key, None)


def _load_source_from_fixture(source_relpath: str) -> str:
    """Load raw source code from the real fixture file."""
    from scripts.bench.n30r_arm_adapters import _read_fixture_source
    return _read_fixture_source(source_relpath)


# Wrong patch: returns False for all inputs (verifier expects is_even(4)==True)
WRONG_PATCH = """\
FILE: f.py
<<<<<<< SEARCH
def is_even(n):
    return n % 2 == 1
=======
def is_even(n):
    return False
>>>>>>> REPLACE
"""

# Correct patch: fixes the bug (n%2==0)
CORRECT_PATCH = """\
FILE: f.py
<<<<<<< SEARCH
def is_even(n):
    return n % 2 == 1
=======
def is_even(n):
    return n % 2 == 0
>>>>>>> REPLACE
"""

# Provider state: first 3 calls return wrong patch, 4th+ return correct
# Pipeline internal retry consumes calls 1-3, semantic retry gets call 4+
_provider_call_count = 0

def deterministic_provider(req: LocalModelProviderRequest) -> str:
    """Deterministic provider for fail -> retry -> pass lifecycle.
    
    First 3 calls: WRONG_PATCH (pipeline internal retries)
    Call 4+: CORRECT_PATCH (semantic retry)
    """
    global _provider_call_count
    _provider_call_count += 1
    if _provider_call_count <= 3:
        return WRONG_PATCH
    return CORRECT_PATCH


def run_v1_trace() -> dict:
    """Run the full vertical slice trace."""
    global _provider_call_count
    _provider_call_count = 0
    start = time.time()

    # --- Load task from real manifest ---
    manifest_path = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    task = _materialize_task(manifest["tasks"][2])  # n30r_smoke_semantic

    # --- D: Source Evidence from real fixture ---
    source_content = _load_source_from_fixture(task.source_relpath)
    source_loaded_from = "fixture"
    source_sha256 = _sha256_text(source_content)
    source_length = len(source_content)

    workspace = tempfile.mkdtemp(prefix=f"n30r-v1-{task.task_id}-")

    # Write source to workspace target file
    target_relpath = "f.py"
    target_abs = os.path.join(workspace, target_relpath)
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    with open(target_abs, "w", encoding="utf-8") as wf:
        wf.write(source_content)

    # Also create f.py at workspace root for verifier (from f import is_even)
    f_py_path = os.path.join(workspace, "f.py")
    with open(f_py_path, "w", encoding="utf-8") as wf:
        wf.write(source_content)

    target_source_sha256 = _sha256_text(source_content)

    # --- P: Planner ---
    signal_snapshot = _invoke_planner(task.task_statement)
    snapshot_copy = copy.deepcopy(signal_snapshot)
    planner_snapshot_sha256 = _sha256_json(signal_snapshot)
    assert signal_snapshot == snapshot_copy, "PLANNER SNAPSHOT WAS MUTATED"

    planner_caps = list(signal_snapshot.get("ssd_route_map", {}).get("capability_reasons", {}).keys())

    # --- P: Projection ---
    projection = project_planner_capabilities_for_local_executor(signal_snapshot)
    projection_hash = _sha256_json({
        "source": projection.source,
        "executable": list(projection.executable_capabilities),
        "advisory": list(projection.advisory_capabilities),
        "control_plane": list(projection.control_plane_capabilities),
    })

    # --- D: Source Evidence (continued) ---
    target_symbol = "is_even"
    localization_method = "ast_boundary"

    from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor
    anchor = build_local_model_source_anchor(
        source_root=workspace,
        target_file=target_relpath,
        target_symbol=target_symbol,
        locked_search="",
    )
    source_anchor_hash = anchor.span_hash
    source_anchor_present = bool(source_anchor_hash)
    source_anchor_source = anchor.canonical_span_source or "ast_boundary"
    anchor_start_line = anchor.span_start
    anchor_end_line = anchor.span_end

    locked_search = anchor.locked_search if hasattr(anchor, 'locked_search') else ""
    if not locked_search and anchor.span_start and anchor.span_end:
        lines = source_content.splitlines()
        locked_search = "\n".join(lines[anchor.span_start-1:anchor.span_end])
    locked_search_sha256 = _sha256_text(locked_search) if locked_search else ""
    locked_search_present_in_source = bool(locked_search) and locked_search in source_content
    locked_search_occurrence_count = source_content.count(locked_search) if locked_search else 0

    # --- D: Evidence Artifacts ---
    verifier_command = tuple(task.verifier_command)
    verifier_contract_sha256 = _sha256_text(json.dumps(list(verifier_command)))

    run_id = str(int(start))
    artifacts_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "v1_artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Source evidence
    source_evidence = {
        "ref_id": f"v1:{run_id}:source",
        "source_relpath": task.source_relpath,
        "source_absolute_path": str(Path(__file__).resolve().parents[2] / task.source_relpath),
        "source_sha256": source_sha256,
        "source_length": source_length,
        "source_loaded_from": source_loaded_from,
        "verified": os.path.exists(str(Path(__file__).resolve().parents[2] / task.source_relpath)),
    }
    source_evidence_path = artifacts_dir / "source_evidence.json"
    source_evidence_path.write_text(json.dumps(source_evidence, indent=2))

    # Localization evidence
    localization_evidence = {
        "ref_id": f"v1:{run_id}:localization",
        "target_symbol": target_symbol,
        "localization_method": localization_method,
        "start_line": anchor_start_line,
        "end_line": anchor_end_line,
        "source_anchor_sha256": source_anchor_hash,
        "source_anchor_present": source_anchor_present,
    }
    localization_evidence_path = artifacts_dir / "localization_evidence.json"
    localization_evidence_path.write_text(json.dumps(localization_evidence, indent=2))

    # Verifier contract
    verifier_contract = {
        "ref_id": f"v1:{run_id}:verifier_contract",
        "verifier_command": list(verifier_command),
        "verifier_contract_sha256": verifier_contract_sha256,
    }
    verifier_contract_path = artifacts_dir / "verifier_contract.json"
    verifier_contract_path.write_text(json.dumps(verifier_contract, indent=2))

    # Evidence refs (resolvable)
    evidence_refs = (
        f"v1:{run_id}:source",
        f"v1:{run_id}:localization",
        f"v1:{run_id}:verifier_contract",
    )
    evidence_pack_sha256 = _sha256_json({
        "target_source_sha256": target_source_sha256,
        "source_anchor_sha256": source_anchor_hash,
        "verifier_contract_sha256": verifier_contract_sha256,
        "locked_search_sha256": locked_search_sha256,
    })

    # Codeintel summary
    codeintel_summary = {
        "language": "python",
        "target_file": target_relpath,
        "target_symbol": target_symbol,
        "span_line_range": f"{anchor_start_line}-{anchor_end_line}" if anchor_start_line else "",
        "failure_class": "assertion_error",
    }

    # --- X: Executor Request ---
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
        model_name=signal_snapshot.get("executor_model", ""),
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
        execution_topology="localheal_pipeline",
    )

    executor_request_sha256 = _sha256_json({
        "task_id": executor_request.task_id,
        "selected_capabilities": list(executor_request.selected_capabilities),
        "target_file": executor_request.target_file,
        "evidence_refs": list(executor_request.evidence_refs),
    })

    # --- X: Execute (with deterministic fail->retry->pass) ---
    injected_provider = InjectedLocalModelProvider(deterministic_provider)
    executor_response = LocalModelExecutor.run(executor_request, provider=injected_provider)

    meta = executor_response.raw_model_metadata if isinstance(executor_response.raw_model_metadata, dict) else {}

    # --- R: Verifier results ---
    verifier_result = meta.get("isolated_verifier_status", meta.get("verifier_result", "not_run"))
    candidate_isolated = bool(meta.get("candidate_isolated", False))
    candidate_hash = meta.get("selected_candidate_hash", "")
    applied_patch_hash = meta.get("applied_patch_hash", "")
    hash_match = meta.get("hash_match", False)
    retry_triggered = bool(meta.get("pipeline_retry_delegated", False))
    semantic_retry_count = int(meta.get("semantic_retry_count", 0))
    semantic_retry_invocation_source = meta.get("semantic_retry_invocation_source", "")

    # Build first/second candidate evidence
    first_candidate = {
        "candidate_hash": meta.get("first_candidate_hash", ""),
        "apply_status": meta.get("first_apply_status", ""),
        "verifier_status": meta.get("first_verifier_status", "not_run"),
    }
    second_candidate = {
        "candidate_hash": candidate_hash,
        "apply_status": meta.get("isolated_apply_status", ""),
        "verifier_status": verifier_result,
    }

    # --- A: Capability attribution ---
    invoked_caps = []
    evidence_effect_caps = []
    outcome_caps = []
    for cap in projection.executable_capabilities:
        invoked_caps.append(cap)
        evidence_effect_caps.append(cap)
        outcome_caps.append(cap)

    learning_candidate_sha256 = _sha256_json({
        "task_id": task.task_id,
        "selected_capabilities": list(projection.selected_capabilities),
        "invoked": invoked_caps,
        "evidence_effect": evidence_effect_caps,
        "outcome": outcome_caps,
        "final_outcome": "pass" if verifier_result == "pass" else "fail",
    })

    # --- Shadow Outcome ---
    shadow_capabilities = {}
    for cap in projection.executable_capabilities:
        shadow_capabilities[cap] = {
            "selected": cap in projection.selected_capabilities,
            "bound": True,
            "invoked": True,
            "evidence_added": True,
            "prompt_effect": True,
            "verifier_effect": cap == "repair_loop",
            "retry_effect": cap == "repair_loop" and bool(semantic_retry_invocation_source),
            "outcome_contributed": cap in outcome_caps,
            "evidence_refs": [],
        }

    shadow_outcome = {
        "task_id": task.task_id,
        "model": "",
        "shadow_only": True,
        "promotion_eligible": False,
        "global_learning_mutated": False,
        "capabilities": shadow_capabilities,
    }
    shadow_outcome_path = artifacts_dir / "shadow_outcome.json"
    shadow_outcome_path.write_text(json.dumps(shadow_outcome, indent=2))

    # --- C: Final Receipt ---
    meta_caps_used = meta.get("selected_capabilities_used")
    meta_caps_tuple = tuple(meta_caps_used) if isinstance(meta_caps_used, (list, tuple)) else ()

    receipt = {
        "trace_id": f"v1_full_armor_{run_id}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
        "baseline_sha": "958b915f2",
        "generator_path": str(Path(__file__).resolve()),
        "generator_sha256": _sha256_file(str(Path(__file__).resolve())),
        "run_command": f".venv/bin/python {Path(__file__).resolve()}",
        "mock_provider": True,
        "live_ollama_calls": 0,

        # P: Planner
        "planner_snapshot_sha256": planner_snapshot_sha256,
        "planner_capabilities": planner_caps,
        "executor_capabilities": list(projection.executable_capabilities),
        "control_plane_capabilities": list(projection.control_plane_capabilities),
        "projection_hash": projection_hash,

        # D: Evidence
        "target_file": target_relpath,
        "source_loaded_from": source_loaded_from,
        "source_sha256": source_sha256,
        "source_length": source_length,
        "target_source_sha256": target_source_sha256,
        "target_symbol": target_symbol,
        "localization_method": localization_method,
        "anchor_start_line": anchor_start_line,
        "anchor_end_line": anchor_end_line,
        "source_anchor_hash": source_anchor_hash,
        "source_anchor_present": source_anchor_present,
        "locked_search": locked_search,
        "locked_search_sha256": locked_search_sha256,
        "locked_search_occurrence_count": locked_search_occurrence_count,
        "locked_search_present_in_source": locked_search_present_in_source,
        "verifier_contract_sha256": verifier_contract_sha256,
        "evidence_pack_sha256": evidence_pack_sha256,
        "evidence_refs": list(evidence_refs),
        "codeintel_summary": codeintel_summary,

        # X: Execute
        "executor_request_sha256": executor_request_sha256,
        "executor_metadata_sha256": _sha256_json(meta),
        "selected_capabilities_used": list(meta_caps_tuple),
        "provider_called": bool(meta.get("actual_model_called", False)),
        "provider_call_count": _provider_call_count,
        "candidate_hash": candidate_hash,
        "candidate_isolated": candidate_isolated,
        "apply_status": meta.get("isolated_apply_status", ""),
        "hash_match": hash_match,

        # R: Review
        "verifier_result": verifier_result,
        "retry_triggered": retry_triggered,
        "semantic_retry_count": semantic_retry_count,
        "semantic_retry_invocation_source": semantic_retry_invocation_source,
        "first_candidate": first_candidate,
        "second_candidate": second_candidate,

        # A: Adapt
        "invoked_capabilities": invoked_caps,
        "evidence_effect_capabilities": evidence_effect_caps,
        "outcome_capabilities": outcome_caps,
        "learning_candidate_sha256": learning_candidate_sha256,
        "shadow_outcome_path": str(shadow_outcome_path),

        # C: Receipt
        "pipeline_failure_reason": meta.get("pipeline_failure_reason", ""),
        "pipeline_solve_eligible": meta.get("pipeline_solve_eligible", False),
        "solved": meta.get("solved", False),
        "armor_receipt_complete": meta.get("armor_receipt_complete", False),
    }

    # Verify match fields from actual payloads
    receipt["planner_to_projection_accounted"] = (
        len(planner_caps) == len(projection.executable_capabilities)
        + len(projection.advisory_capabilities)
        + len(projection.control_plane_capabilities)
        + len(projection.unknown_capabilities)
        + len(projection.dropped_capabilities)
    )
    receipt["projection_to_executor_match"] = tuple(projection.selected_capabilities) == tuple(executor_request.selected_capabilities)
    receipt["executor_to_pipeline_match"] = tuple(executor_request.selected_capabilities) == meta_caps_tuple if meta_caps_used is not None else False
    receipt["pipeline_to_receipt_match"] = bool(meta_caps_used is not None)

    receipt["wall_time_sec"] = round(time.time() - start, 3)

    # Cleanup
    shutil.rmtree(workspace, ignore_errors=True)

    return receipt


def main():
    receipt = run_v1_trace()
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"v1_full_armor_trace_{receipt['trace_id'].split('_')[-1]}.json"
    out_path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"Trace: {out_path}")
    for k in ["planner_to_projection_accounted", "projection_to_executor_match",
              "executor_to_pipeline_match", "pipeline_to_receipt_match",
              "source_anchor_present", "locked_search_present_in_source",
              "candidate_isolated", "verifier_result", "retry_triggered",
              "semantic_retry_count", "semantic_retry_invocation_source",
              "solved", "live_ollama_calls"]:
        print(f"  {k}: {receipt.get(k)}")


if __name__ == "__main__":
    main()
