from __future__ import annotations

import json
import time
import concurrent.futures
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import click

from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.findings_memory import FindingsMemoryStore
from nexus.research.local_sprint_mutator import generate_local_candidate
from nexus.research.sprint_service import SprintConfig, run_hyper_sprint, LLMCandidateGenerator


def _derive_findings_query(task_desc: str, target_file: str | None = None) -> str:
    text = " ".join((task_desc or "").split())
    if target_file:
        text = f"{text} {target_file}".strip()
    return text[:200]


def read_belief_confidence_fast(repo_root: Path) -> float:
    path = (repo_root / ".nexus" / "belief_state.json").resolve()
    if not path.exists():
        return 1.0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("confidence", payload.get("belief_confidence", 1.0))
        value = float(raw)
        return min(1.0, max(0.0, value))
    except Exception:
        return 1.0


def read_capability_tuning_fast(repo_root: Path) -> dict[str, Any]:
    import os

    override = str(os.environ.get("NEXUS_CAPABILITY_TUNING_FILE", "") or "").strip()
    if override:
        path = Path(override).resolve()
    else:
        path = (repo_root / ".nexus" / "config" / "capability_tuning.json").resolve()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_phase_slo_summary_fast(repo_root: Path) -> dict[str, Any]:
    path = (repo_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").resolve()
    if not path.exists():
        return {"phase_slo_pass": False, "global": {"required_done_ratio": 0.0}, "status": "UNAVAILABLE", "reason": "phase_slo_summary_missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid_phase_slo_payload")
        payload.setdefault("phase_slo_pass", False)
        payload.setdefault("global", {"required_done_ratio": 0.0})
        payload.setdefault("status", "SUCCESS")
        payload.setdefault("reason", "")
        return payload
    except Exception:
        return {"phase_slo_pass": False, "global": {"required_done_ratio": 0.0}, "status": "UNAVAILABLE", "reason": "phase_slo_summary_invalid"}


def build_route(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str | None = None,
) -> dict:

    findings_hits = 0
    historical_hints = []
    adjusted_root_cause_confidence = root_cause_confidence
    effective_findings_query = findings_query or _derive_findings_query(task_desc, target_file=target_file)
    if effective_findings_query:
        store = FindingsMemoryStore(repo_root)
        hits = store.search(effective_findings_query)
        findings_hits = len(hits)
        for h in hits:
            historical_hints.extend(h.retrieval_hints)

        if findings_hits >= 1:
            adjusted_root_cause_confidence = max(0.0, root_cause_confidence - 0.15)

    policy = ResearchPolicy()
    prediction = {
        "candidate_count": candidate_count,
        "root_cause_confidence": adjusted_root_cause_confidence,
    }
    decision = policy.route({}, task_desc, task_type=task_type, prediction=prediction)

    # 🐝 [P2 Optimization] Doc-Fix Interception
    task_lower = (task_desc or "").lower()
    target_lower = (target_file or "").lower()
    doc_patterns = ["readme", ".md", "doc:", "fix typo", "documentation", "typo:"]
    is_doc_fix = any(p in task_lower for p in doc_patterns) or any(p in target_lower for p in doc_patterns if p.startswith("."))
    
    task_upper = (task_desc or "").upper()
    hard_keywords = ["FLAKY", "RACE", "DEADLOCK", "TIMEOUT", "LATENCY", "WEBSOCKET", "SDK", "API"]
    has_hard_signal = any(kw in task_upper for kw in hard_keywords)
    
    # R2 Tuning: Feature/Refactor prefer baseline, Bugfix with risk prefers hyper
    if is_doc_fix:
        recommended_flow = "baseline"
        recommended_reason = "Matched Doc-Fix Rule"
    elif task_type in ["feature", "refactor"]:
        recommended_flow = "baseline"
        recommended_reason = f"structural_task_type_{task_type}_prefer_baseline"
    else:
        # Bugfix case
        is_risky_bug = (
            candidate_count > 1
            or adjusted_root_cause_confidence < 0.75
            or findings_hits > 0
            or has_hard_signal
            or decision.should_research
        )
        recommended_flow = "hyper_sprint" if is_risky_bug else "baseline"
        recommended_reason = "complex_bug_prefer_hyper" if is_risky_bug else "simple_bug_prefer_baseline"

    if recommended_flow == "hyper_sprint":
        should_research = True
        mode = decision.mode if decision.mode != "skip" else "external"
        reason = decision.reason if decision.reason != "clear_root_cause" else recommended_reason
    else:
        should_research = False
        mode = "skip"
        reason = recommended_reason if is_doc_fix else "clear_root_cause"

    risk_level = "HIGH" if (has_hard_signal or task_type == "feature") else "LOW"
    if adjusted_root_cause_confidence < 0.5:
        risk_level = "CRITICAL"

    risk_score = 0
    risk_score += 30 if has_hard_signal else 0
    risk_score += 25 if task_type in {"feature", "refactor"} else 10
    risk_score += 25 if adjusted_root_cause_confidence < 0.7 else 0
    risk_score += 15 if findings_hits > 0 else 0
    risk_score += 10 if candidate_count > 1 else 0
    risk_score = min(100, risk_score)
    route_features = {
        "task_type": task_type,
        "has_hard_signal": has_hard_signal,
        "is_doc_fix": is_doc_fix,
        "candidate_count": int(candidate_count),
        "findings_hits": int(findings_hits),
        "adjusted_root_cause_confidence": round(float(adjusted_root_cause_confidence), 4),
        "risk_score": risk_score,
    }

    explain = {
        "task_type": task_type,
        "risk": risk_level,
        "files": [target_file] if target_file else [],
        "history": {"findings_hits": findings_hits, "hints_count": len(historical_hints)},
        "confidence": round(adjusted_root_cause_confidence, 2),
        "reasoning": f"Flow '{recommended_flow}' chosen due to {recommended_reason}. TaskType: {task_type}."
    }

    return {
        "should_research": should_research,
        "mode": mode,
        "reason": reason,
        "rounds": decision.rounds if should_research else 0,
        "stable_wins": decision.stable_wins if should_research else 0,
        "findings_hits": findings_hits,
        "prior_fix_hits": findings_hits,
        "historical_hints": list(dict.fromkeys(historical_hints))[:3],  # Unique, max 3
        "adjusted_root_cause_confidence": adjusted_root_cause_confidence,
        "require_codex_audit": adjusted_root_cause_confidence < 0.6,
        "recommended_flow": recommended_flow,
        "recommended_reason": recommended_reason,
        "explain_payload": explain,
        "route_features": route_features,
    }


def build_hyper_execution_profile(
    *,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    route_recommended_flow: str,
    belief_confidence: float = 1.0,
    prior_fix_hits: int = 0,
    tuning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = (task_desc or "").lower()
    hard_keywords = ["flaky", "race", "deadlock", "timeout", "latency", "websocket", "sdk", "api"]
    has_hard_keyword = any(keyword in text for keyword in hard_keywords)
    low_confidence = float(root_cause_confidence) < 0.75
    risk_bug = task_type == "bug" and route_recommended_flow == "hyper_sprint"
    is_hard_task = bool(has_hard_keyword or low_confidence or risk_bug)

    effective_candidate_count = max(1, int(candidate_count))
    effective_max_rounds = 1
    effective_stage1_max_parallel = 1
    tuning_reasons: list[str] = []

    if risk_bug:
        effective_candidate_count = max(effective_candidate_count, 3)
        effective_max_rounds = max(effective_max_rounds, 2)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        tuning_reasons.append("risk_bug_promote_hyper_budget")

    if has_hard_keyword:
        effective_candidate_count = max(effective_candidate_count, 4)
        effective_max_rounds = max(effective_max_rounds, 3)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        tuning_reasons.append("hard_keyword_detected")

    if low_confidence:
        effective_candidate_count = max(effective_candidate_count, 4)
        effective_max_rounds = max(effective_max_rounds, 3)
        tuning_reasons.append("low_root_cause_confidence")

    if float(belief_confidence) < 0.6:
        effective_candidate_count = max(effective_candidate_count, 4)
        effective_max_rounds = max(effective_max_rounds, 3)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        tuning_reasons.append("low_belief_confidence")

    if int(prior_fix_hits or 0) >= 2 and is_hard_task:
        effective_candidate_count = max(effective_candidate_count, 5)
        effective_max_rounds = max(effective_max_rounds, 3)
        tuning_reasons.append("prior_fix_hits_boost")
    if int(prior_fix_hits or 0) >= 3 and is_hard_task:
        effective_candidate_count = max(effective_candidate_count, 6)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 3)
        tuning_reasons.append("prior_fix_hits_first_pass_accelerate")

    knobs = (tuning or {}).get("knobs", {}) if isinstance(tuning, dict) else {}
    candidate_boost = int(knobs.get("candidate_boost", 0) or 0)
    max_rounds_boost = int(knobs.get("max_rounds_boost", 0) or 0)
    stage1_parallel_boost = int(knobs.get("stage1_parallel_boost", 0) or 0)
    if candidate_boost != 0:
        effective_candidate_count = max(1, effective_candidate_count + candidate_boost)
        tuning_reasons.append(f"tuning_candidate_boost:{candidate_boost}")
    if max_rounds_boost != 0:
        effective_max_rounds = max(1, effective_max_rounds + max_rounds_boost)
        tuning_reasons.append(f"tuning_max_rounds_boost:{max_rounds_boost}")
    if stage1_parallel_boost != 0:
        effective_stage1_max_parallel = max(1, effective_stage1_max_parallel + stage1_parallel_boost)
        tuning_reasons.append(f"tuning_stage1_parallel_boost:{stage1_parallel_boost}")

    # Keep runtime bounded for CLI calls.
    effective_candidate_count = min(effective_candidate_count, 6)
    effective_max_rounds = min(effective_max_rounds, 4)
    effective_stage1_max_parallel = min(effective_stage1_max_parallel, 3)

    return {
        "is_hard_task": is_hard_task,
        "has_hard_keyword": has_hard_keyword,
        "low_confidence": low_confidence,
        "risk_bug": risk_bug,
        "belief_confidence": float(belief_confidence),
        "prior_fix_hits": int(prior_fix_hits or 0),
        "effective_candidate_count": effective_candidate_count,
        "effective_max_rounds": effective_max_rounds,
        "effective_stage1_max_parallel": effective_stage1_max_parallel,
        "tuning_reasons": tuning_reasons,
    }




def run_auto_flow(
    *,
    repo_root: Path,
    task_desc: str,
    target_file: str,
    test_file: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    llm_mode: bool,
    llm_baseline: bool,
    timeout_sec: int,
    stage1_timeout_sec: int,
    max_time_ratio_guard: float,
    baseline_fast_sec: float,
    history_window: int,
    history_fail_threshold: int,
    dynamic_timeout_multiplier: float,
    min_dynamic_stage1_timeout: int,
    force_flow: str | None,
    report_file: str,
    output_file: Path | None,
):
    """Internal impl for Auto Flow Runner: route -> run baseline/hyper -> enforce guard -> emit report."""

    route = build_route(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
    )
    tuning_payload = read_capability_tuning_fast(repo_root)
    tuning_knobs = (tuning_payload.get("knobs", {}) if isinstance(tuning_payload, dict) else {}) or {}
    execution_profile = build_hyper_execution_profile(
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        route_recommended_flow=str(route.get("recommended_flow", "")),
        belief_confidence=read_belief_confidence_fast(repo_root),
        prior_fix_hits=int(route.get("prior_fix_hits", 0) or 0),
        tuning=tuning_payload,
    )
    tuned_baseline_fast_sec = baseline_fast_sec
    try:
        tuned_fast = float(tuning_knobs.get("baseline_fast_sec", baseline_fast_sec))
        if tuned_fast >= 0:
            tuned_baseline_fast_sec = tuned_fast
    except Exception:
        tuned_baseline_fast_sec = baseline_fast_sec
    skip_baseline_probe_for_hard = bool(tuning_knobs.get("skip_baseline_probe_for_hard", False))
    chosen_flow = force_flow or route["recommended_flow"]
    learn_phase_slo = read_phase_slo_summary_fast(repo_root)
    learn_gate_blocked = (
        not bool(learn_phase_slo.get("phase_slo_pass", False))
        or float((learn_phase_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0) < 0.95
    )
    if force_flow is None and chosen_flow == "hyper_sprint" and learn_gate_blocked and not execution_profile["is_hard_task"]:
        chosen_flow = "baseline"
    flow_key = f"{target_file}|{test_file}"
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()

    def _read_history() -> dict:
        if history_path.exists():
            try:
                return json.loads(history_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _write_history(data: dict) -> None:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    history_data = _read_history()
    recent = list(history_data.get(flow_key, []))
    recent_window = recent[-max(1, history_window):]
    recent_hyper_fails = sum(1 for item in recent_window if item.get("flow") == "hyper_sprint" and item.get("status") == "FAILED")
    stage1_fail_signals = sum(
        1
        for item in recent_window
        if item.get("flow") == "hyper_sprint"
        and item.get("status") == "FAILED"
        and "stage1_no_passing_candidate" in str(item.get("reason", ""))
    )
    nightshift_recommended = bool(recent_hyper_fails >= 2 or stage1_fail_signals >= 1)
    history_forced_baseline = False
    if force_flow is None and chosen_flow == "hyper_sprint" and recent_hyper_fails >= max(1, history_fail_threshold):
        chosen_flow = "baseline"
        history_forced_baseline = True

    guard_hit = False
    target_path = (repo_root / target_file).resolve()
    if not target_path.exists():
        raise click.ClickException(f"Target file not found: {target_file}")
    pytest_cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", test_file]
    original_code = target_path.read_text(encoding="utf-8")

    def _generate_baseline_patch(trial: int = 0) -> tuple[str, str]:
        """R4: Enhanced baseline generation with LLM fast-fallback and conservative local paths."""
        source_label = "local"
        fallback_reason = None
        
        # [NEW: X-2] Prior-Art from Claims
        try:
            from nexus.research.learn_mode import LearnModeService
            svc = LearnModeService(repo_root)
            prior_fixes = svc.ask(topic="bug-fixes", question=task_desc, top_k=5)
            if prior_fixes.get("citations"):
                prior_context = "\n".join([c["claim"] for c in prior_fixes["citations"][:3]])
                task_desc_for_llm = f"{task_desc}\n\n[Prior Art]\n{prior_context}"
            else:
                task_desc_for_llm = task_desc
        except Exception:
            task_desc_for_llm = task_desc
        
        if llm_baseline and task_type in ["feature", "refactor"]:
            try:
                # Use a very short timeout for baseline assistance to avoid blocking
                gen = LLMCandidateGenerator(repo_root, safe_mode=True)
                # Note: gen.generate internal timeout depends on gateway, but we wrap it here if possible
                # For now, we trust internal model_chain but monitor for rapid failure
                patched, meta = gen.generate(source_code=original_code, task=task_desc_for_llm, mutation_hint="baseline", seed=trial)
                if patched and patched != original_code:
                    return patched, "llm_assisted"
                else:
                    fallback_reason = "llm_generation_empty_fallback_local"
            except Exception as e:
                err_str = str(e).lower()
                if "timeout" in err_str:
                    fallback_reason = "llm_timeout_fallback_local"
                elif any(p in err_str for p in ["quota", "429", "limit"]):
                    fallback_reason = "llm_quota_fallback_local"
                else:
                    fallback_reason = f"llm_error_{err_str}_fallback_local"
        
        # Local fallback intentionally uses raw task_desc to avoid prior-art keyword pollution
        # (e.g., stale "flaky/race" hints forcing conservative patch on unrelated tasks).
        patched = generate_local_candidate(original_code, task_desc, "baseline", trial)
        
        # If still no mutation and it's structural, try a generic structural hint as last resort
        if patched == original_code and task_type in ["feature", "refactor"]:
            # Last resort: force a pattern match if keywords exist
            if "discount" in task_desc.lower():
                from nexus.research.local_sprint_mutator import _feature_discount_patch
                patched = _feature_discount_patch(original_code)
                source_label = "local_conservative_feature"
            elif "parser" in task_desc.lower() or "refactor" in task_desc.lower():
                from nexus.research.local_sprint_mutator import _refactor_parser_patch
                patched = _refactor_parser_patch(original_code)
                source_label = "local_conservative_refactor"
        
        label = source_label
        if fallback_reason:
            label = f"{source_label}({fallback_reason})"
            
        return patched, label

    def _run_baseline_apply() -> dict:
        start = time.time()
        ok = False
        err = ""
        try:
            patched, source = _generate_baseline_patch()
            if patched == original_code:
                err = "no_mutation_generated"
            else:
                target_path.write_text(patched, encoding="utf-8")
                res = subprocess.run(pytest_cmd, cwd=repo_root, capture_output=True, text=True, timeout=timeout_sec)
                ok = res.returncode == 0
                if not ok:
                    err = "pytest_failed"
                    target_path.write_text(original_code, encoding="utf-8")
        except subprocess.TimeoutExpired:
            err = "test_timeout"
            target_path.write_text(original_code, encoding="utf-8")
        return {
            "flow": "baseline",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.time() - start, 4),
            "error": err,
            "report": {
                "source": source,
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
        }

    def _run_baseline_probe() -> dict:
        # Probe run used by guard. Always restore original state.
        start = time.time()
        ok = False
        err = ""
        source = "local"
        patched = original_code
        try:
            patched, source = _generate_baseline_patch()
            if patched == original_code:
                err = "no_mutation_generated"
            else:
                target_path.write_text(patched, encoding="utf-8")
                res = subprocess.run(pytest_cmd, cwd=repo_root, capture_output=True, text=True, timeout=timeout_sec)
                ok = res.returncode == 0
                if not ok:
                    err = "pytest_failed"
        except subprocess.TimeoutExpired:
            err = "test_timeout"
        finally:
            target_path.write_text(original_code, encoding="utf-8")
        return {
            "flow": "baseline_probe",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.time() - start, 4),
            "error": err,
            "report": {
                "source": source,
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
            "_patch": patched if ok else None,
        }

    def _run_hyper_apply() -> dict:
        start = time.time()
        effective_stage1_timeout = stage1_timeout_sec
        if baseline_probe and baseline_probe.get("elapsed_sec", 0) > 0:
            dynamic_timeout = int(round(float(baseline_probe["elapsed_sec"]) * max(1.0, dynamic_timeout_multiplier)))
            effective_stage1_timeout = max(
                min_dynamic_stage1_timeout,
                min(stage1_timeout_sec, dynamic_timeout),
            )
        cfg = SprintConfig(
            task=task_desc,
            target_file=target_file,
            test_file=test_file,
            candidate_count=execution_profile["effective_candidate_count"],
            max_rounds=execution_profile["effective_max_rounds"],
            timeout_sec=timeout_sec,
            safe_mode=True,
            stage1_max_parallel=execution_profile["effective_stage1_max_parallel"],
            stage1_timeout_sec=effective_stage1_timeout,
            llm_mode=llm_mode,
        )
        res = run_hyper_sprint(repo_root=repo_root, config=cfg)
        ok = res.status == "SUCCESS" and bool(res.patch)
        err = ""
        if ok:
            target_path.write_text(res.patch, encoding="utf-8")
        else:
            err = res.reason
        return {
            "flow": "hyper_sprint",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.time() - start, 4),
            "error": err,
            "report": {
                "status": res.status,
                "reason": res.reason,
                "winner_source": res.winner_source,
                "error_codes": res.error_codes,
                "rejection_summary": res.rejection_summary,
                "attempt_count": res.attempt_count,
                "model_calls": res.model_calls,
                "total_tokens": res.total_tokens,
                "token_capture_status": res.token_capture_status,
                "effective_stage1_timeout_sec": effective_stage1_timeout,
            },
        }

    baseline_probe = None
    early_baseline_shortcut = False
    baseline_probe_skipped = False
    if chosen_flow == "baseline":
        result = _run_baseline_apply()
        strategy_path = "baseline_only"
    else:
        if (
            force_flow is None
            and execution_profile["is_hard_task"]
            and skip_baseline_probe_for_hard
        ):
            baseline_probe_skipped = True
            result = _run_hyper_apply()
            strategy_path = "hyper_direct_hard_skip_probe"
        else:
        # Probe first to avoid unnecessary Hyper run for obvious quick fixes.
            baseline_probe = _run_baseline_probe()
            if (
                force_flow is None
                and baseline_probe["status"] == "SUCCESS"
                and tuned_baseline_fast_sec > 0
                and baseline_probe["elapsed_sec"] <= tuned_baseline_fast_sec
            ):
                early_baseline_shortcut = True
                probe_patch = baseline_probe.get("_patch")
                if isinstance(probe_patch, str) and probe_patch and probe_patch != original_code:
                    target_path.write_text(probe_patch, encoding="utf-8")
                    result = {
                        "flow": "baseline",
                        "status": "SUCCESS",
                        "elapsed_sec": baseline_probe["elapsed_sec"],
                        "error": "",
                        "report": {
                            **(baseline_probe.get("report", {}) if isinstance(baseline_probe.get("report"), dict) else {}),
                            "reused_from_probe": True,
                        },
                    }
                else:
                    target_path.write_text(original_code, encoding="utf-8")
                    result = _run_baseline_apply()
                chosen_flow = "baseline"
                strategy_path = "probe_success_fastpath_baseline"
            else:
                result = _run_hyper_apply()
                strategy_path = "probe_then_hyper"
                min_probe_sec_for_ratio_guard = 0.05
                if (
                    baseline_probe["status"] == "SUCCESS"
                    and result["status"] == "SUCCESS"
                    and baseline_probe["elapsed_sec"] >= min_probe_sec_for_ratio_guard
                    and result["elapsed_sec"] > max_time_ratio_guard * baseline_probe["elapsed_sec"]
                ):
                    guard_hit = True
                    target_path.write_text(original_code, encoding="utf-8")
                    result = _run_baseline_apply()
                    chosen_flow = "baseline"
                    strategy_path = "hyper_guard_fallback_to_baseline"

    baseline_probe_for_report = None
    if isinstance(baseline_probe, dict):
        baseline_probe_for_report = {k: v for k, v in baseline_probe.items() if k != "_patch"}

    payload = {
        "schema_version": "1.0",
        "task_desc": task_desc,
        "task_type": task_type,
        "route": route,
        "execution_profile": execution_profile,
        "chosen_flow": chosen_flow,
        "guard": {
            "hit": guard_hit,
            "early_baseline_shortcut": early_baseline_shortcut,
            "history_forced_baseline": history_forced_baseline,
            "learn_forced_baseline": bool(learn_gate_blocked and force_flow is None and not execution_profile["is_hard_task"]),
            "recent_hyper_failures": recent_hyper_fails,
            "nightshift_recommended": nightshift_recommended,
            "stage1_fail_signals": stage1_fail_signals,
            "history_window": max(1, history_window),
            "baseline_fast_sec": tuned_baseline_fast_sec,
            "max_time_ratio_guard": max_time_ratio_guard,
            "baseline_probe_skipped": baseline_probe_skipped,
            "baseline_probe": baseline_probe_for_report,
        },
        "learn_phase_slo": {
            "phase_slo_pass": bool(learn_phase_slo.get("phase_slo_pass", False)),
            "required_done_ratio": float((learn_phase_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0),
            "status": learn_phase_slo.get("status", "UNAVAILABLE"),
            "reason": learn_phase_slo.get("reason", ""),
        },
        "result": result,
        "strategy": {
            "path": strategy_path,
            "forced_flow": force_flow or "auto",
            "flow_ladder": ["baseline_probe", "hyper_sprint", "baseline_fallback"],
            "learn_gate_blocked": bool(learn_gate_blocked),
        },
        "io": {
            "output_written": False,
            "output_path": None,
        },
    }
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if output_file:
        written = _write_output_file(output_file, payload)
        payload["io"]["output_written"] = True
        payload["io"]["output_path"] = str(written)
        # keep report + output payload in sync
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    recent.append(
        {
            "flow": chosen_flow,
            "status": result["status"],
            "reason": result.get("error", ""),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    history_data[flow_key] = recent[-200:]
    _write_history(history_data)
    return payload, out_path


def _is_strictly_doc_fix(task: str, target_file: str) -> tuple[bool, str]:
    is_doc_file = any(target_file.endswith(ext) for ext in [".md", ".txt", ".rst"])
    has_code_intent = any(kw in task.lower() for kw in ["fix bug", "implement", "logic", "refactor"])
    
    score = 0
    if is_doc_file: score += 50
    if not has_code_intent: score += 30
    
    # Final Decision
    is_doc = score >= 80
    reason = f"Substance Score={score} (FileDoc={is_doc_file}, NoCodeIntent={not has_code_intent})"
    return is_doc, reason
