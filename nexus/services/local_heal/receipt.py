from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _nexus_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_instance_id(instance_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", instance_id).strip("_") or "unknown"


def _error_reason(ctx: Any) -> str:
    if getattr(ctx, "solve_eligible", False):
        return ""
    explicit_reason = str(getattr(ctx, "failure_reason", "") or "").strip()
    if explicit_reason:
        return explicit_reason
    errors = getattr(ctx, "errors", []) or []
    if errors:
        latest = errors[-1]
        kind = getattr(getattr(latest, "kind", ""), "name", str(getattr(latest, "kind", "")))
        message = str(getattr(latest, "message", "")).strip()
        return f"{kind}:{message}" if kind else message
    report = str(getattr(ctx, "evaluation_report", "") or "").strip()
    if report:
        return "VERIFICATION_FAILED"
    if not getattr(ctx, "final_patch", ""):
        return "NO_PATCH"
    return "NOT_SOLVE_ELIGIBLE"


def _failure_class(ctx: Any) -> str:
    reason = str(_error_reason(ctx))
    if "AttributeError" in reason or "has no attribute" in reason:
        return "hallucinated_api"
    if "MODEL_TIMEOUT" in reason:
        return "timeout"
    if "OOM" in reason or "killed" in reason.lower():
        return "oom"
    # T1.2: Specific failure classes BEFORE generic syntax check
    if "REPLACE_SYNTAX_ERROR" in reason:
        return "syntax_invalid:replacement"
    if "FILE_NOT_FOUND" in reason:
        if "reproduce_bug.py" in reason or "repro" in reason.lower():
            return "file_not_found:wrong_repro_path"
        if "UNKNOWN" in reason or "pending" in reason.lower():
            return "file_not_found:path_resolution"
        return "file_not_found"
    if "NO_EFFECTIVE_CHANGE" in reason:
        return "no_effective_change"
    if "syntax" in reason.lower() or "IndentationError" in reason:
        return "syntax_invalid"
    # Env failures — classify as agent-fixable or externally blocked
    if any(kw in reason for kw in ["ENV_", "ENVIRONMENT", "ImportError", "VIOLATION", "MISSING", "REPRO_"]):
        return _classify_env_failure(ctx, reason)
    if "NO_BLOCKS_FOUND" in reason or "NO_PATCH" in reason or "SEARCH_MISMATCH" in reason or "REFUSAL" in reason:
        # T1.2: Check for mismatch subclass in errors with richer classification
        errors = getattr(ctx, "errors", []) or []
        for err in reversed(errors):
            kind = getattr(getattr(err, "kind", ""), "name", str(getattr(err, "kind", "")))
            if kind == "SEARCH_MISMATCH":
                subclass = getattr(err, "mismatch_subclass", None)
                if subclass:
                    return f"patch_mismatch:{subclass.name}"
                return "patch_mismatch"
        # T1.2: FILE_NOT_FOUND from NO_BLOCKS_FOUND path
        if "FILE_NOT_FOUND" in reason:
            return "file_not_found"
        # T1.2: NO_EFFECTIVE_CHANGE from NO_BLOCKS_FOUND path
        if "NO_EFFECTIVE_CHANGE" in reason:
            return "no_effective_change"
        return "patch_mismatch"
    if "VERIFICATION_FAILED" in reason or "AssertionError" in reason or "LOGIC_REGRESSION" in reason:
        return "semantic_wrong"
    return "unknown"


def _derive_success_attribution(match_authority: Any) -> str:
    """T3: Classify success attribution from match_authority.

    Returns a human-readable attribution string for receipts:
    - 'model_patch_success' — VERBATIM authority (model's SEARCH matched exactly)
    - 'canonical_recovery_success' — CANONICAL_RECOVERY authority (tool recovered the span)
    - 'cross_file_recovery_success' — CROSS_FILE_CORRECTION authority (applied to different file)
    - 'unknown' — authority not set or unrecognized
    """
    authority_str = str(getattr(match_authority, "value", match_authority) or "").lower()
    if authority_str == "verbatim":
        return "model_patch_success"
    elif authority_str == "canonical_recovery":
        return "canonical_recovery_success"
    elif authority_str == "cross_file_correction":
        return "cross_file_recovery_success"
    else:
        return "unknown"


def _has_structured_packet(ctx: Any) -> bool:
    """T3: Check if structured_packet was available for retry evidence."""
    errors = getattr(ctx, "errors", []) or []
    for err in reversed(errors):
        sp = getattr(err, "structured_packet", None)
        if sp is not None:
            return True
    return False


def _extract_failure_telemetry(ctx: Any, failure_reason: str) -> dict:
    """T1.2: Extract enriched telemetry based on failure type."""
    telemetry = {}
    reason = str(failure_reason)

    # SEARCH_MISMATCH: Extract canonical span and match details
    if "SEARCH_MISMATCH" in reason or "CANONICAL_INJECTION_FAILED" in reason:
        errors = getattr(ctx, "errors", []) or []
        for err in reversed(errors):
            kind = getattr(getattr(err, "kind", ""), "name", str(getattr(err, "kind", "")))
            if kind in ("SEARCH_MISMATCH",):
                subclass = getattr(err, "mismatch_subclass", None)
                telemetry["mismatch_subclass"] = subclass.name if subclass else "UNKNOWN"
                telemetry["file_path"] = getattr(err, "file_path", "") or ""
                telemetry["failed_search_text"] = (getattr(err, "failed_search_text", "") or "")[:500]
                closest = getattr(err, "closest_match", "") or ""
                telemetry["closest_match_present"] = bool(closest)
                telemetry["closest_match_preview"] = closest[:200] if closest else ""
                # T1.3: Forward enriched telemetry from validate()
                err_telemetry = getattr(err, "telemetry", None) or {}
                canonical = err_telemetry.get("canonical_span", {})
                closest_info = err_telemetry.get("closest_match", {})
                telemetry["canonical_span"] = canonical
                telemetry["closest_match_info"] = closest_info
                telemetry["auto_corrected_search"] = canonical.get("auto_corrected", False)
                telemetry["original_failed_search_hash"] = canonical.get("original_failed_search_hash", "")
                telemetry["canonical_search_hash"] = canonical.get("canonical_search_hash", "")
                telemetry["resolved_span"] = closest_info.get("resolved_span", "")
                telemetry["resolved_span_lines"] = closest_info.get("resolved_span_lines", 0)
                telemetry["closest_snippet_preview"] = closest_info.get("closest_snippet_preview", "")[:200]
                # T1.4: Canonical span injection telemetry
                injection = err_telemetry.get("injection_status", "")
                if injection:
                    telemetry["injection_status"] = injection
                    telemetry["canonical_span_start_line"] = err_telemetry.get("canonical_span_start_line", 0)
                    telemetry["canonical_span_end_line"] = err_telemetry.get("canonical_span_end_line", 0)
                    telemetry["canonical_span_lines"] = err_telemetry.get("canonical_span_lines", 0)
                    telemetry["lookup_result"] = err_telemetry.get("lookup_result", "")
                    telemetry["lookup_attempts"] = err_telemetry.get("lookup_attempts", [])
                    telemetry["closest_match_similarity"] = err_telemetry.get("closest_match_similarity", 0.0)
                    telemetry["original_search_hash"] = err_telemetry.get("original_search_hash", "")
                    telemetry["canonical_search_hash_from_injection"] = err_telemetry.get("canonical_search_hash", "")
                # T1.8: Symbol-aware canonical span fallback telemetry
                ast_found = err_telemetry.get("ast_symbol_found", False)
                if ast_found:
                    telemetry["target_symbol"] = err_telemetry.get("target_symbol", "")
                    telemetry["target_symbol_source"] = err_telemetry.get("target_symbol_source", "")
                    telemetry["target_symbol_confidence"] = err_telemetry.get("target_symbol_confidence", "low")
                    telemetry["ast_symbol_found"] = True
                    telemetry["ast_symbol_span_start"] = err_telemetry.get("ast_symbol_span_start", 0)
                    telemetry["ast_symbol_span_end"] = err_telemetry.get("ast_symbol_span_end", 0)
                    telemetry["ast_symbol_span_hash"] = err_telemetry.get("ast_symbol_span_hash", "")
                    telemetry["fallback_used"] = err_telemetry.get("fallback_used", False)
                    telemetry["fallback_reason"] = err_telemetry.get("fallback_reason", "")
                    telemetry["canonical_span_source"] = err_telemetry.get("canonical_span_source", "")
                break
        # T1.4: Also check for CANONICAL_INJECTION_FAILED in errors
        if "CANONICAL_INJECTION_FAILED" in reason:
            for err in reversed(errors):
                err_telemetry = getattr(err, "telemetry", None) or {}
                if err_telemetry.get("injection_status"):
                    telemetry["injection_status"] = err_telemetry["injection_status"]
                    telemetry["canonical_span_start_line"] = err_telemetry.get("canonical_span_start_line", 0)
                    telemetry["canonical_span_end_line"] = err_telemetry.get("canonical_span_end_line", 0)
                    telemetry["lookup_result"] = err_telemetry.get("lookup_result", "")
                    telemetry["lookup_attempts"] = err_telemetry.get("lookup_attempts", [])
                    break

    # REPLACE_SYNTAX_ERROR: Extract line/offset
    if "REPLACE_SYNTAX_ERROR" in reason:
        import re
        m = re.search(r'line (\d+), col (\d+)', reason)
        if m:
            telemetry["syntax_error_line"] = int(m.group(1))
            telemetry["syntax_error_offset"] = int(m.group(2))
        m2 = re.search(r'SyntaxError:\s*(.+?)(?:\s*at\s*|$)', reason)
        if m2:
            telemetry["syntax_error_message"] = m2.group(1)[:200]

    # FILE_NOT_FOUND: Extract path and resolution attempts
    if "FILE_NOT_FOUND" in reason:
        # Extract the path from FILE_NOT_FOUND:/path/to/file
        path_match = reason.split("FILE_NOT_FOUND:")[-1].split(",")[0].strip() if "FILE_NOT_FOUND:" in reason else ""
        telemetry["target_path"] = path_match
        repo_dir = str(getattr(ctx, "repo_dir", "") or "")
        telemetry["repo_dir"] = repo_dir
        # Classify the failure reason
        if "reproduce_bug" in path_match or "repro" in path_match:
            telemetry["path_subclass"] = "wrong_repro_path"
        elif not path_match:
            telemetry["path_subclass"] = "empty_path"
        else:
            telemetry["path_subclass"] = "generated_wrong_path"

    # NO_EFFECTIVE_CHANGE: Record diff hash
    if "NO_EFFECTIVE_CHANGE" in reason:
        import hashlib
        final_patch = str(getattr(ctx, "final_patch", "") or "")
        if final_patch:
            telemetry["patch_hash"] = hashlib.sha256(final_patch.encode()).hexdigest()[:16]
            telemetry["patch_length"] = len(final_patch)

    return telemetry


def _classify_env_failure(ctx: Any, reason: str) -> str:
    """
    Classify env failure using EnvFailureTaxonomy.
    Returns taxonomy value string (e.g. 'DEPENDENCY_MISMATCH', 'TOOLCHAIN_MISSING').
    """
    try:
        from nexus.services.local_heal.env_taxonomy import classify_env_failure, TAXONOMY_META
        env_resolution = dict(getattr(ctx, "env_resolution", {}) or {})
        env_denoise = dict(getattr(ctx, "env_denoise", {}) or {})
        taxonomy = classify_env_failure(reason, env_resolution, env_denoise)
        return taxonomy.value
    except Exception:
        # Fallback to ad-hoc classification if taxonomy module unavailable
        return "env_fixable_by_agent"


def build_repair_receipt(ctx: Any, *, model_name: str = "nexus-local-heal", run_group: str = "") -> dict[str, Any]:
    final_patch = str(getattr(ctx, "final_patch", "") or "")
    evaluation_report = str(getattr(ctx, "evaluation_report", "") or "")
    visible_passed = "[FAIL]" not in evaluation_report if evaluation_report else bool(getattr(ctx, "solve_eligible", False))
    hidden_required = bool(getattr(ctx, "hidden_verifier_required", False))
    hidden_passed = bool(getattr(ctx, "hidden_verifier_passed", False))
    patch_paths = sorted(set(re.findall(r"^\+\+\+ b/(.+)$", final_patch, flags=re.MULTILINE)))
    python_executable = str(getattr(ctx, "python_executable", "") or "python3")

    repro_success = bool(getattr(ctx, "reproduced", False))
    failure_reason = _error_reason(ctx)
    
    env_resolution = dict(getattr(ctx, "env_resolution", {}) or {})
    env_failed = not env_resolution.get("ready", True)
    
    # Granular Repro Status
    if env_failed:
        repro_status = _classify_env_failure(ctx, failure_reason).upper()
    elif "ENV_" in failure_reason or "ENVIRONMENT" in failure_reason:
        repro_status = _classify_env_failure(ctx, failure_reason).upper()
    elif repro_success:
        repro_status = "ACTIVE_BUG"
    elif "ALREADY_FIXED" in failure_reason:
        repro_status = "ALREADY_FIXED"
    elif "HARNESS_ANOMALY" in failure_reason:
        repro_status = "HARNESS_ANOMALY"
    elif "RESCUE_FAILED" in failure_reason:
        repro_status = "RESCUE_FAILED"
    elif "REPRO_INVALID" in failure_reason or "NOT_REPRODUCED" in failure_reason:
        repro_status = "INVALID"
    elif not getattr(ctx, "repro_script", ""):
        repro_status = "REPRO_NOT_REACHED"
    else:
        repro_status = "GREEN"

    model_decisions = list(getattr(ctx, "model_decisions", []) or [])
    
    # Attempt to inject runtime telemetry from swe_local_heal
    try:
        from benchmarking.swebench_lite.swe_local_heal import telemetry_store
        if hasattr(telemetry_store, "records") and telemetry_store.records:
            total_tokens = sum(r.get("prompt_eval_count", 0) + r.get("eval_count", 0) for r in telemetry_store.records)
            ctx.op.token_total_estimated = total_tokens
            ctx.op.token_telemetry_status = "success"
            for idx, record in enumerate(telemetry_store.records):
                if idx < len(model_decisions):
                    model_decisions[idx]["telemetry"] = record
    except Exception:
        pass
    
    # 決定 gate_exit
    if env_failed:
        gate_exit = "env_resolver"
    elif not repro_success:
        gate_exit = "repro_runner"
    elif not final_patch:
        gate_exit = "patcher"
    else:
        gate_exit = "verification"

    expected_stop = str(getattr(ctx, "expected_stop_layer", "verification") or "verification")
    expected_family = str(getattr(ctx, "expected_reason_family", "SOLVED") or "SOLVED")
    
    actual_family = _failure_class(ctx)
    if getattr(ctx, "solve_eligible", False):
        actual_family = "SOLVED"

    layer_matched = (gate_exit == expected_stop)
    family_matched = (actual_family == expected_family)
    stop_layer_matched = layer_matched and family_matched

    # 萃取模型分工資訊
    search_model = "unknown"
    patch_model = "unknown"
    for decision in model_decisions:
        phase = decision.get("phase")
        model = decision.get("model", "unknown")
        if phase in ["planning", "reproduction"]:
            search_model = model.split(":")[-1] if ":" in model else model
        elif phase == "patch":
            patch_model = model.split(":")[-1] if ":" in model else model

    model_split = f"search={search_model}/patch={patch_model}"
    if not any(d.get("model") for d in model_decisions):
        model_split = "rescue=0-call"

    # ============================================================
    # V1 SCHEMA FIELDS — Identity / Claim Boundary / Execution Audit
    # ============================================================
    import uuid
    from datetime import datetime, timezone

    instance_id = getattr(ctx, "instance_id", "")
    
    # --- Identity ---
    task_id = instance_id
    run_id = str(uuid.uuid4())
    schema_version = "1.0"
    
    # --- Claim Boundary ---
    # simulated: True only if pipeline did NOT run (e.g. mock/simulated data)
    simulated = False
    
    # run_eligible: task was allowed to enter and run through pipeline
    run_eligible = bool(instance_id)
    
    # claim_eligible: result can be used in public benchmark claims
    # Fail-closed: ALL conditions must be met
    failure_present = bool(failure_reason)
    reached_verification = (gate_exit == "verification")
    actually_solved = bool(getattr(ctx, "solve_eligible", False))
    
    claim_eligible = (
        not simulated
        and run_eligible
        and reached_verification
        and actually_solved
        and not failure_present
    )
    
    # Fail-closed overrides
    if simulated:
        claim_eligible = False
    
    # public_benchmark_allowed: same as claim_eligible (alias for backward compat)
    public_benchmark_allowed = claim_eligible
    
    # --- Execution Audit ---
    observed_stop_layer = gate_exit
    phase_durations = {}
    ll = getattr(ctx, "_latency_ledger", None)
    if ll and hasattr(ll, "phases"):
        for p in ll.phases:
            # PhaseTiming can be dict or dataclass — handle both
            if isinstance(p, dict):
                phase_durations[p.get("name", "unknown")] = p.get("duration_sec", 0.0)
            else:
                phase_durations[getattr(p, "name", "unknown")] = getattr(p, "duration_sec", 0.0)
    
    timestamp = datetime.now(timezone.utc).isoformat()

    # --- Cost Tracking (S7) ---
    total_tokens = int(getattr(ctx, "token_total_estimated", 0) or 0)
    wall_time = float(getattr(ctx, "wall_time_sec", 0.0) or 0.0)
    model_calls = len(model_decisions)
    cost_estimate = 0.0
    if total_tokens > 0 and model_calls > 0:
        cost_estimate = total_tokens * 0.15 / 1_000_000
    
    token_efficiency = ""
    if total_tokens > 0 and actually_solved:
        token_efficiency = f"{total_tokens} tokens / solved"

    return {
        # --- Identity ---
        "schema": "nexus.local_heal.repair_receipt.v1",
        "schema_version": schema_version,
        "task_id": task_id,
        "instance_id": instance_id,
        "run_id": run_id,
        "run_group": run_group or "",
        "timestamp": timestamp,
        
        # --- Claim Boundary ---
        "simulated": simulated,
        "claim_eligible": claim_eligible,
        "solve_eligible": bool(getattr(ctx, "solve_eligible", False)),
        "public_benchmark_allowed": public_benchmark_allowed,
        
        # --- Execution Audit ---
        "expected_stop_layer": expected_stop,
        "observed_stop_layer": observed_stop_layer,
        "phase_durations": phase_durations,
        "model_phase_split": model_split,
        "model_calls": model_calls,
        "wall_time_sec": float(getattr(ctx, "wall_time_sec", 0.0) or 0.0),
        
        # --- Sidecar Tracking ---
        "sidecar_enabled": bool(getattr(ctx, "_sidecar_enabled", False)),
        "sidecar_model": str(getattr(ctx, "_sidecar_model", "")),
        "sidecar_contributed": bool(getattr(ctx, "_sidecar_contributed", False)),
        
        # --- Cost Tracking (S7) ---
        "cost_estimate_usd": cost_estimate,
        "token_efficiency": token_efficiency,
        "total_tokens": total_tokens,
        
        # --- Pipeline Results ---
        "model_name_or_path": model_name,
        "runner_completed": bool(getattr(ctx, "runner_completed", False)),
        "reproduced": repro_success,
        "patch_applied": bool(final_patch),
        "visible_passed": bool(visible_passed),
        "hidden_verifier_required": hidden_required,
        "hidden_passed": bool(hidden_passed if hidden_required else True),
        "gate_passed": bool(getattr(ctx, "solve_eligible", False)),
        "failure_reason": failure_reason,
        
        # --- Evidence ---
        "evidence_refs": [
            ref for ref in [
                "repro_evidence.log",
                "patch.diff" if final_patch else "",
                "verification_report.txt" if evaluation_report else "",
            ] if ref
        ],
        "patch_paths": patch_paths,
        "commands": [f"{python_executable} reproduce_bug.py"] if getattr(ctx, "repro_script", "") else [],
        
        # --- Telemetry ---
        "telemetries": {
            "attempt": int(getattr(ctx, "attempt", 0) or 0),
            "reasoning_mode": getattr(ctx, "reasoning_mode", "INTUITIVE"),
            "patch_len": len(final_patch),
            "model_decisions": model_decisions,
            "env_denoise": dict(getattr(ctx, "env_denoise", {}) or {}),
            "env_resolution": dict(getattr(ctx, "env_resolution", {}) or {}),
            "token_telemetry_status": str(getattr(ctx, "token_telemetry_status", "not_applicable") or "not_applicable"),
            "token_total_estimated": int(getattr(ctx, "token_total_estimated", 0) or 0),
            "preflight_telemetry": dict(getattr(ctx, "preflight_telemetry", {}) or {}),
            "closest_snippet_present": bool(getattr(ctx, "closest_snippet", "")),
            "closest_snippet_similarity": float(getattr(ctx, "closest_snippet_similarity", 0.0) or 0.0),
            "resolved_span": str(getattr(ctx, "resolved_span", "") or ""),
            # T3: match_authority from PatchApplicationResult
            "match_authority": str(getattr(ctx, "match_authority", "") or ""),
            # T3: success_attribution — classifies whether success was model-native or tool-recovered
            "success_attribution": _derive_success_attribution(getattr(ctx, "match_authority", None)),
            # T1.2: Enriched failure telemetry
            "failure_telemetry": _extract_failure_telemetry(ctx, failure_reason),
            # T3: structured_packet telemetry — whether structured evidence was used in retry
            "structured_packet_used": _has_structured_packet(ctx),
            # T1.6: Semantic retry telemetry
            "semantic_retry_telemetry": dict(getattr(ctx, "_semantic_retry_telemetry", {}) or {}),
        },

        # --- S1-prep: StrategyTrace-only (no execution effect) ---
        "strategy_trace": {
            "strategy_trace_only": True,
            "strategy_id": "",
            "strategy_schema": "",
            "task_goal": "",
            "bug_hypothesis": "",
            "repair_strategy": "",
            "target_symbols": [],
            "allowed_paths": [],
            "forbidden_paths": [],
            "invariants": [],
            "abort_conditions": [],
            "canonical_span_source": "",
            "canonical_span_confidence": "",
            "target_symbol": "",
            "target_symbol_source": "",
            "target_symbol_confidence": "",
            "fallback_used": False,
            "fallback_reason": "",
            "semantic_retry_mode": "",
            "model_patch_reward": 0.0,
            "deterministic_fallback_reward": 0.0,
            "ast_fallback_reward": 0.0,
            "model_calls": model_calls,
            "claim_eligible": claim_eligible,
            "public_claim_allowed": public_benchmark_allowed,
        },
        
        # --- Eval Metrics (backward compat) ---
        "eval_metrics": {
            "repro_status": repro_status,
            "failure_class": actual_family,
            "model_phase_split": model_split,
            "context_bytes_before_after": f"{getattr(ctx, 'initial_ctx_len', 0)}/{getattr(ctx, 'final_ctx_len', 0)}",
            "resolved_span_len": int(getattr(ctx, "resolved_span_len", 0) or 0),
            "retry_count": max(0, int(getattr(ctx, "attempt", 0) or 0) - 1),
            "gate_exit": gate_exit,
            "expected_stop_layer": expected_stop,
            "expected_reason_family": expected_family,
            "stop_layer_matched": stop_layer_matched,
            "layer_matched": layer_matched,
            "family_matched": family_matched,
            "wall_time_sec_measured": float(getattr(ctx, "wall_time_sec", 0.0) or 0.0),
            "syntax_gate_passed": bool(getattr(ctx, "syntax_gate_passed", True)),
            "claimability": "public_safe" if public_benchmark_allowed else "observation_only",
            "diagnostics": {
                "prompt_variant_id": str(getattr(ctx, "prompt_variant_id", "default") or "default"),
                "refusal_detected": bool(getattr(ctx, "refusal_detected", False)),
                "empty_response": bool(getattr(ctx, "empty_response", False)),
            }
        },
        
        # --- Latency Ledger ---
        "latency_ledger": getattr(ctx, "_latency_ledger", None) and getattr(ctx._latency_ledger, "to_dict", lambda: {})() or None,
    }


def write_repair_receipt(
    ctx: Any,
    *,
    model_name: str = "nexus-local-heal",
    reports_root: Path | None = None,
    run_group: str = "",
) -> Path:
    report_dir_name = _safe_instance_id(getattr(ctx, "instance_id", ""))
    if run_group:
        report_dir_name = f"{report_dir_name}__{run_group}"
    report_dir = (reports_root or (_nexus_root() / ".nexus/reports/local_heal")) / report_dir_name
    report_dir.mkdir(parents=True, exist_ok=True)

    (report_dir / "repro_evidence.log").write_text(str(getattr(ctx, "repro_evidence", "") or ""), encoding="utf-8")
    final_patch = str(getattr(ctx, "final_patch", "") or "")
    if final_patch:
        (report_dir / "patch.diff").write_text(final_patch, encoding="utf-8")
    evaluation_report = str(getattr(ctx, "evaluation_report", "") or "")
    if evaluation_report:
        (report_dir / "verification_report.txt").write_text(evaluation_report, encoding="utf-8")

    receipt = build_repair_receipt(ctx, model_name=model_name, run_group=run_group)
    receipt["evidence_refs"] = [item for item in receipt["evidence_refs"] if item]
    receipt_path = report_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # P0.1b: Audit trail — track abort receipt coexistence
    abort_receipt_path = report_dir / f"abort_receipt_{getattr(ctx, 'instance_id', '')}.json"
    receipt["abort_receipt_written"] = abort_receipt_path.exists()
    receipt["abort_receipt_path"] = str(abort_receipt_path) if abort_receipt_path.exists() else ""
    receipt["final_receipt_path"] = str(receipt_path)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return receipt_path
