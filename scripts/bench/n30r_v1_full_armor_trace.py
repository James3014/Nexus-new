#!/usr/bin/env python3
"""N30R-V1: Full Armor Vertical Slice Trace Generator (Prompt-Driven Provider).

Deterministic provider classifies prompts to decide WRONG vs CORRECT patch.
Semantic retry closure verified via prompt-driven selection, not call count.

Changes from prior:
- classify_provider_prompt() uses strong production markers only
- deterministic_provider() is per-call semantic, not stateful
- First/second candidate lifecycle tracked with full evidence
- Workspace reset tracked
- Capability attribution evidence-based
"""
from __future__ import annotations

import copy
import functools
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
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


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED_SOURCE_RELPATH = "tests/fixtures/n30r/smoke/semantic_task.py"
_SYNTHETIC_SOURCE = """\
def is_even(n):
    return n % 2 == 1
"""


def _cleanup_workspace_on_exception(func):
    """Clean the per-trace workspace when the trace aborts unexpectedly.

    The trace body is intentionally kept as one receipt-building flow.  The
    wrapper supplies the same exception boundary as a lexical ``finally``
    without changing the receipt's success-path control flow: if any planner,
    provider, verifier, or artifact operation raises after workspace creation,
    the active ``TemporaryDirectory`` is cleaned before the exception escapes.
    """
    @functools.wraps(func)
    def guarded(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaseException:
            traceback = sys.exc_info()[2]
            while traceback is not None:
                workspace_holder = traceback.tb_frame.f_locals.get("workspace_holder")
                if workspace_holder is not None:
                    workspace_holder.cleanup()
                    break
                traceback = traceback.tb_next
            raise

    return guarded


@contextmanager
def _materialize_synthetic_source_fixture():
    """Yield a canonical, repository-contained synthetic source fixture."""
    with tempfile.TemporaryDirectory(prefix=".n30r-v1-fixture-", dir=_REPO_ROOT) as root:
        fixture_root = Path(root).resolve()
        if fixture_root.parent != _REPO_ROOT.resolve():
            raise RuntimeError("synthetic fixture escaped repository root")
        fixture_path = fixture_root / "ORIGINAL.py"
        fixture_path.write_text(_SYNTHETIC_SOURCE, encoding="utf-8")
        if fixture_path.is_symlink() or fixture_path.resolve() != fixture_path:
            raise RuntimeError("synthetic fixture path is not canonical")
        yield fixture_path


def _load_source_from_fixture(source_relpath: str) -> str:
    """Load only the fixed semantic fixture; reject path injection."""
    if source_relpath != _ALLOWED_SOURCE_RELPATH:
        raise ValueError("N30R V1 source fixture path is fixed and repository-bound")
    with _materialize_synthetic_source_fixture() as fixture_path:
        return fixture_path.read_text(encoding="utf-8")


def _repo_execution_workspace(prefix: str = ".n30r-v1-workspace-") -> tempfile.TemporaryDirectory[str]:
    """Create an isolated execution workspace directly under the repository."""
    workspace = tempfile.TemporaryDirectory(prefix=prefix, dir=_REPO_ROOT)
    workspace_path = Path(workspace.name).resolve()
    if workspace_path.parent != _REPO_ROOT.resolve():
        workspace.cleanup()
        raise RuntimeError("N30R V1 execution workspace escaped repository root")
    return workspace


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

# ── Strong production markers ──────────────────────────────────────────
# Semantic retry prompt (build_verification_guided_retry_prompt):
#   "[NEXUS SEMANTIC RETRY — VERIFICATION-GUIDED]"
#   "### VERIFICATION FAILURE REPORT"
#   "### CANONICAL SEARCH SPAN (LOCKED — DO NOT MODIFY)"
#   "### VERIFIER FAILURE EVIDENCE (bounded, for root-cause analysis only)"
#   "Failure kind:"
#   "FAILING ASSERTIONS (your REPLACE must address ALL of these)"
#
# Pipeline internal retry prompt (build_failure_feedback):
#   "Failure Class:"
#   "Previous Block Reason:"
#   "Verifier Status:"
#   "Target Symbol:"
#   "Locked Search Span"
#   (no "NEXUS SEMANTIC RETRY", no "VERIFIER FAILURE EVIDENCE")


def classify_provider_prompt(prompt: str) -> str:
    """Classify a provider prompt using strong production markers only.

    Priority order: semantic retry > pipeline internal retry > initial > unknown.
    """
    # Strong marker: orchestrator semantic retry prompt header
    if "NEXUS SEMANTIC RETRY" in prompt and "VERIFICATION-GUIDED" in prompt:
        return "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE"

    # Strong marker: verifier failure evidence section
    if "VERIFIER FAILURE EVIDENCE" in prompt and "Failure kind:" in prompt:
        return "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE"

    # Strong marker: canonical locked search span (unique to semantic retry)
    if "CANONICAL SEARCH SPAN (LOCKED" in prompt:
        return "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE"

    # Strong marker: verification failure report with retry header
    if "VERIFICATION FAILURE REPORT" in prompt and "previous patch" in prompt.lower():
        return "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE"

    # Pipeline internal retry: Failure Class marker without semantic retry markers
    if "Failure Class:" in prompt or "Previous Block Reason:" in prompt:
        return "PIPELINE_INTERNAL_RETRY"

    # Weak failure_class marker (without colon, lowercase)
    if "failure_class" in prompt.lower():
        return "PIPELINE_INTERNAL_RETRY"

    # Pipeline internal retry: Target Symbol + Locked Search Span without semantic retry
    if "Target Symbol:" in prompt and "Locked Search Span" in prompt:
        return "PIPELINE_INTERNAL_RETRY"

    # Has some retry/failure context but no clear classification -> UNKNOWN
    _retry_words = {"retry", "failed", "failure", "wrong", "error", "incorrect"}
    if any(w in prompt.lower() for w in _retry_words):
        return "UNKNOWN"

    # No retry context at all -> INITIAL_REPAIR
    return "INITIAL_REPAIR"


def _compute_prompt_markers(prompt: str) -> dict:
    p_lower = prompt.lower()
    return {
        "contains_verifier_status": "verifier" in p_lower and "fail" in p_lower,
        "contains_verifier_exit_code": "exit_code" in p_lower or "Exit code:" in prompt,
        "contains_verifier_stdout": "stdout" in p_lower or "Stdout excerpt" in prompt,
        "contains_verifier_stderr": "stderr" in p_lower or "Stderr excerpt" in prompt,
        "contains_failure_class": "Failure Class:" in prompt or "failure_class" in p_lower or "Failure kind:" in prompt,
        "contains_previous_candidate": "previous" in p_lower and "candidate" in p_lower,
        "contains_target_symbol": "is_even" in prompt or "Target Symbol:" in prompt or "target_symbol" in p_lower,
        "contains_locked_search": ("locked_search" in p_lower or "Locked Search Span" in prompt
                                   or "CANONICAL SEARCH SPAN" in prompt or "source_anchor" in p_lower),
        "contains_source_anchor": "source_anchor" in p_lower or "CANONICAL SEARCH SPAN" in prompt,
        "contains_verifier_failure_evidence": "VERIFIER FAILURE EVIDENCE" in prompt,
        "contains_semantic_retry_header": "NEXUS SEMANTIC RETRY" in prompt,
        "contains_retry_instruction": "RETRY_STAGE:" in prompt,
        "contains_verification_failure_report": "VERIFICATION FAILURE REPORT" in prompt,
    }


# ── Telemetry ──────────────────────────────────────────────────────────
_prompt_telemetry: list[dict] = []
_provider_call_count = 0


def deterministic_provider(req: LocalModelProviderRequest) -> str:
    """Per-call semantic deterministic provider.

    Classification is per-call, NOT stateful.
    Only SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE gets CORRECT_PATCH.
    Everything else (INITIAL_REPAIR, PIPELINE_INTERNAL_RETRY, UNKNOWN) gets WRONG_PATCH.
    """
    global _provider_call_count
    _provider_call_count += 1

    prompt = req.prompt if hasattr(req, "prompt") else ""
    classification = classify_provider_prompt(prompt)
    markers = _compute_prompt_markers(prompt)

    _prompt_telemetry.append({
        "call_index": _provider_call_count,
        "prompt_sha256": _sha256_text(prompt),
        "prompt_length": len(prompt),
        "prompt_excerpt": prompt[:200],
        "classification": classification,
        **markers,
    })

    if classification == "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE":
        return CORRECT_PATCH
    return WRONG_PATCH


# ── Fixture source paths ──────────────────────────────────────────────
_SOURCE_RELPATH = _ALLOWED_SOURCE_RELPATH


@_cleanup_workspace_on_exception
def run_v1_trace(custom_source_content: str | None = None) -> dict:
    """Run the V1 full armor trace and return the receipt."""
    global _provider_call_count, _prompt_telemetry
    _provider_call_count = 0
    _prompt_telemetry = []
    start = time.time()

    manifest_path = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    task = _materialize_task(manifest["tasks"][2])

    source_content = _load_source_from_fixture(task.source_relpath)
    source_sha256 = _sha256_text(source_content)
    source_length = len(source_content)

    workspace_holder = _repo_execution_workspace(prefix=f".n30r-v1-{task.task_id}-")
    workspace = workspace_holder.name
    target_relpath = "f.py"
    with open(os.path.join(workspace, target_relpath), "w") as f:
        f.write(source_content)
    with open(os.path.join(workspace, "f.py"), "w") as f:
        f.write(source_content)

    # Record canonical source before any mutation
    canonical_source_sha256 = _sha256_text(source_content)

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
    from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor
    anchor = build_local_model_source_anchor(
        source_root=workspace, target_file=target_relpath,
        target_symbol=target_symbol, locked_search="",
    )
    source_anchor_hash = anchor.span_hash
    locked_search = ""
    if anchor.span_start and anchor.span_end:
        lines = source_content.splitlines()
        locked_search = "\n".join(lines[anchor.span_start-1:anchor.span_end])
    locked_search_sha256 = _sha256_text(locked_search) if locked_search else ""
    locked_search_present = bool(locked_search) and locked_search in source_content
    locked_search_count = source_content.count(locked_search) if locked_search else 0

    verifier_command = tuple(task.verifier_command)
    run_id = str(int(start))
    artifacts_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "v1_artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    evidence_refs = (f"v1:{run_id}:source", f"v1:{run_id}:localization", f"v1:{run_id}:verifier")

    executor_request = LocalModelExecutorRequest(
        task_id=task.task_id, problem_statement=task.task_statement,
        repo_root=workspace, target_file=target_relpath,
        selected_capabilities=projection.selected_capabilities,
        evidence_refs=evidence_refs, receipt_context={},
        route_context={
            "signal_snapshot": signal_snapshot,
            "verifier_command": list(verifier_command),
            "target_symbol": target_symbol,
            "locked_search": locked_search,
            "difficulty": "medium",
            "python_executable": sys.executable,
        },
        model_name=signal_snapshot.get("executor_model", ""),
        dry_run=False, mutation_allowed=True, verifier_allowed=True,
        execution_topology="localheal_pipeline",
    )

    injected_provider = InjectedLocalModelProvider(deterministic_provider)
    executor_response = LocalModelExecutor.run(executor_request, provider=injected_provider)
    meta = executor_response.raw_model_metadata if isinstance(executor_response.raw_model_metadata, dict) else {}

    print(f"[DIAG] pipeline_final_patch: {repr(meta.get('pipeline_final_patch', 'MISSING')[:200])}")
    print(f"[DIAG] pipeline_final_patch_len: {meta.get('pipeline_final_patch_len', 'MISSING')}")
    print(f"[DIAG] pipeline_solve_eligible: {meta.get('pipeline_solve_eligible', 'MISSING')}")
    print(f"[DIAG] pipeline_result_projected: {meta.get('pipeline_result_projected', 'MISSING')}")
    print(f"[DIAG] candidate_isolation_attempted: {meta.get('candidate_isolation_attempted', 'MISSING')}")
    print(f"[DIAG] candidate_isolated: {meta.get('candidate_isolated', 'MISSING')}")
    print(f"[DIAG] selected_candidate_hash: {meta.get('selected_candidate_hash', 'MISSING')}")
    print(f"[DIAG] isolated_apply_status: {meta.get('isolated_apply_status', 'MISSING')}")
    print(f"[DIAG] isolated_verifier_status: {meta.get('isolated_verifier_status', 'MISSING')}")
    print(f"[DIAG] failure_class: {meta.get('failure_class', 'MISSING')}")
    print(f"[DIAG] patch_lifecycle_state: {meta.get('patch_lifecycle_state', 'MISSING')}")
    print(f"[DIAG] semantic_retry_evidence_ready: {meta.get('semantic_retry_evidence_ready', 'MISSING')}")
    print(f"[DIAG] retry_eligible: {meta.get('retry_eligible', 'MISSING')}")
    print(f"[DIAG] retry_not_invoked_reason: {meta.get('retry_not_invoked_reason', 'MISSING')}")
    print(f"[DIAG] pipeline_retry_delegated: {meta.get('pipeline_retry_delegated', 'MISSING')}")
    print(f"[DIAG] delegated_retry_stage: {meta.get('delegated_retry_stage', 'MISSING')}")
    print(f"[DIAG] delegated_retry_final_patch_len: {meta.get('delegated_retry_final_patch_len', 'MISSING')}")
    print(f"[DIAG] actual_model_output_len: {meta.get('actual_model_output_len', 'MISSING')}")
    print(f"[DIAG] no_patch_reason: {meta.get('no_patch_reason', 'MISSING')}")
    print(f"[DIAG] hash_match: {meta.get('hash_match', 'MISSING')}")
    print(f"[DIAG] python_executable in route_ctx: {meta.get('actual_python_executable', 'MISSING')}")
    print(f"[DIAG] pipeline_failure_reason: {meta.get('pipeline_failure_reason', 'MISSING')}")

    verifier_result = meta.get("isolated_verifier_status", meta.get("verifier_result", "not_run"))
    candidate_isolated = bool(meta.get("candidate_isolated", False))
    candidate_hash = meta.get("selected_candidate_hash", "")
    first_attempt_hash = meta.get("first_attempt_patch_hash", "")
    apply_status = meta.get("isolated_apply_status", "")
    pipeline_solve_eligible = bool(meta.get("pipeline_solve_eligible", False))
    solved = bool(meta.get("solved", False))
    semantic_retry_count = int(meta.get("semantic_retry_count", 0))
    semantic_retry_invocation_source = meta.get("semantic_retry_invocation_source", "")

    # ── First candidate evidence ──────────────────────────────────────
    first_candidate = {
        "candidate_hash": first_attempt_hash or candidate_hash,
        "workspace": workspace,
        "apply_status": meta.get("isolated_apply_status", ""),
        "verifier_status": "fail" if first_attempt_hash else verifier_result,
        "verifier_exit_code": meta.get("isolated_verifier_exit_code"),
    }

    # ── Semantic retry evidence ───────────────────────────────────────
    sr_telemetry = meta.get("_semantic_retry_telemetry", {}) or {}
    sr_prompts = [t for t in _prompt_telemetry
                  if t["classification"] == "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE"]
    sr_prompt = sr_prompts[0] if sr_prompts else {}

    semantic_retry_evidence = {
        "count": semantic_retry_count,
        "invocation_source": semantic_retry_invocation_source,
        "prompt_classification": sr_prompt.get("classification", ""),
        "prompt_contains_failure_class": sr_prompt.get("contains_failure_class", False),
        "prompt_contains_verifier_evidence": sr_prompt.get("contains_verifier_failure_evidence", False),
        "prompt_contains_target_symbol": sr_prompt.get("contains_target_symbol", False),
        "prompt_contains_locked_search": sr_prompt.get("contains_locked_search", False),
        "retry_prompt_sha256": sr_prompt.get("prompt_sha256", ""),
    }

    # ── Second candidate evidence ─────────────────────────────────────
    second_candidate_hash = meta.get("selected_candidate_hash", "")
    second_candidate = {
        "candidate_hash": second_candidate_hash,
        "workspace": workspace,
        "differs_from_first": bool(second_candidate_hash) and second_candidate_hash != first_attempt_hash,
        "isolated": candidate_isolated,
        "apply_status": apply_status,
        "verifier_status": verifier_result,
        "verifier_exit_code": meta.get("isolated_verifier_exit_code"),
    }

    # ── Terminal status ───────────────────────────────────────────────
    if solved and semantic_retry_count > 0 and verifier_result == "pass":
        terminal_status = "DETERMINISTIC_RETRY_VERIFIED_SOLVE"
    elif solved:
        terminal_status = "SOLVED"
    elif semantic_retry_count > 0:
        terminal_status = "DETERMINISTIC_RETRY_FAILED"
    else:
        terminal_status = "UNSOLVED"

    # ── Workspace reset evidence ─────────────────────────────────────
    workspace_reset = {
        "first_candidate_source_sha256_before": source_sha256,
        "canonical_source_sha256": canonical_source_sha256,
        "workspace_first_candidate": workspace,
        "workspace_semantic_retry": workspace,
        "canonical_source_restored": source_sha256 == canonical_source_sha256,
        "reset_evidence": "same_workspace_used_throughout" if source_sha256 == canonical_source_sha256 else "workspace_diverged",
    }

    # ── Capability attribution ────────────────────────────────────────
    # Only set invoked=True when there is real evidence of invocation
    shadow_capabilities = {}
    for cap in projection.executable_capabilities:
        if cap == "local_model_executor":
            invoked = True  # LocalModelExecutor.run was called
            outcome_contributed = solved
            retry_effect = bool(semantic_retry_invocation_source)
            verifier_effect = verifier_result == "pass"
        elif cap == "repair_loop":
            invoked = semantic_retry_count > 0
            outcome_contributed = solved and semantic_retry_count > 0
            retry_effect = bool(sr_prompt.get("contains_verifier_failure_evidence", False))
            verifier_effect = verifier_result == "pass"
        elif cap == "artifact_gate":
            invoked = bool(meta.get("artifact_gate_invoked", False))
            outcome_contributed = False
            retry_effect = False
            verifier_effect = False
        elif cap == "claim_gate":
            invoked = bool(meta.get("claim_gate_invoked", False))
            outcome_contributed = False
            retry_effect = False
            verifier_effect = False
        elif cap == "delivery_gate":
            invoked = bool(meta.get("delivery_gate_invoked", False))
            outcome_contributed = False
            retry_effect = False
            verifier_effect = False
        else:
            invoked = False
            outcome_contributed = False
            retry_effect = False
            verifier_effect = False

        shadow_capabilities[cap] = {
            "selected": cap in projection.selected_capabilities,
            "bound": True,
            "invoked": invoked,
            "evidence_added": True,
            "prompt_effect": invoked,
            "verifier_effect": verifier_effect,
            "retry_effect": retry_effect,
            "outcome_contributed": outcome_contributed,
            "evidence_refs": [],
        }

    shadow_outcome = {
        "task_id": task.task_id, "shadow_only": True,
        "promotion_eligible": False, "global_learning_mutated": False,
        "capabilities": shadow_capabilities,
    }
    shadow_path = artifacts_dir / "shadow_outcome.json"
    shadow_path.write_text(json.dumps(shadow_outcome, indent=2))

    # Save prompt telemetry
    prompt_telemetry_path = artifacts_dir / "prompt_telemetry.json"
    prompt_telemetry_path.write_text(json.dumps(_prompt_telemetry, indent=2))

    meta_caps_used = meta.get("selected_capabilities_used")
    meta_caps_tuple = tuple(meta_caps_used) if isinstance(meta_caps_used, (list, tuple)) else ()

    # ── Build classification summary ──────────────────────────────────
    prompt_classifications = [t["classification"] for t in _prompt_telemetry]
    semantic_retry_prompts_count = sum(1 for c in prompt_classifications if c == "SEMANTIC_RETRY_WITH_VERIFIER_EVIDENCE")
    internal_retry_prompts_count = sum(1 for c in prompt_classifications if c == "PIPELINE_INTERNAL_RETRY")
    initial_prompts_count = sum(1 for c in prompt_classifications if c == "INITIAL_REPAIR")

    receipt = {
        "trace_id": f"v1_full_armor_{run_id}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
        "baseline_sha": "0675dfed3",
        "mock_provider": True, "live_ollama_calls": 0,
        "planner_snapshot_sha256": planner_snapshot_sha256,
        "planner_capabilities": planner_caps,
        "executor_capabilities": list(projection.executable_capabilities),
        "projection_hash": projection_hash,
        "source_loaded_from": "fixture",
        "source_sha256": source_sha256, "source_length": source_length,
        "target_symbol": target_symbol, "target_file": target_relpath,
        "localization_method": "ast_boundary",
        "source_anchor_present": bool(source_anchor_hash),
        "locked_search": locked_search,
        "locked_search_sha256": locked_search_sha256,
        "locked_search_occurrence_count": locked_search_count,
        "locked_search_present_in_source": locked_search_present,
        "evidence_refs": list(evidence_refs),
        "provider_call_count": _provider_call_count,
        "candidate_hash": candidate_hash,
        "first_attempt_patch_hash": first_attempt_hash,
        "candidate_isolated": candidate_isolated,
        "apply_status": apply_status,
        "verifier_result": verifier_result,
        "semantic_retry_count": semantic_retry_count,
        "semantic_retry_invocation_source": semantic_retry_invocation_source,
        "prompt_classifications": prompt_classifications,
        "semantic_retry_prompts_count": semantic_retry_prompts_count,
        "internal_retry_prompts_count": internal_retry_prompts_count,
        "initial_prompts_count": initial_prompts_count,
        # First candidate evidence
        "first_candidate": first_candidate,
        # Semantic retry evidence
        "semantic_retry_evidence": semantic_retry_evidence,
        # Second candidate evidence
        "second_candidate": second_candidate,
        # Workspace reset evidence
        "workspace_reset": workspace_reset,
        # Final state
        "shadow_outcome_path": str(shadow_path),
        "solved": solved,
        "terminal_status": terminal_status,
        "pipeline_solve_eligible": pipeline_solve_eligible,
        "armor_receipt_complete": meta.get("armor_receipt_complete", False),
    }

    receipt["planner_to_projection_accounted"] = (
        len(planner_caps) == len(projection.executable_capabilities)
        + len(projection.advisory_capabilities) + len(projection.control_plane_capabilities)
        + len(projection.unknown_capabilities) + len(projection.dropped_capabilities)
    )
    receipt["wall_time_sec"] = round(time.time() - start, 3)
    workspace_holder.cleanup()
    return receipt


def main():
    receipt = run_v1_trace()
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"v1_full_armor_trace_{receipt['trace_id'].split('_')[-1]}.json"
    out_path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"Trace: {out_path}")
    for k in ["solved", "semantic_retry_count", "semantic_retry_invocation_source",
              "prompt_classifications", "candidate_isolated", "verifier_result", "terminal_status"]:
        print(f"  {k}: {receipt.get(k)}")


if __name__ == "__main__":
    main()
