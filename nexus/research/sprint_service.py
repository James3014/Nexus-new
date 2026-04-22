from __future__ import annotations

import json
import sys
import subprocess
import time
from datetime import datetime
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from nexus.core.outcome_schema import SprintOutcome
from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.day_shift_optimizer import DayShiftOptimizer
from nexus.research.local_sprint_mutator import generate_local_candidate
from nexus.research.swarm_broker import SwarmBroker
from .runtime.runtime_resilience import compute_time_budget, classify_infra_block, get_retry_delay, RetryParams


@dataclass
class SprintConfig:
    task: str
    target_file: str
    test_file: Optional[str] = None
    candidate_count: int = 3
    max_rounds: int = 5
    timeout_sec: int = 60
    safe_mode: bool = True
    stage1_max_parallel: int = 1
    stage1_timeout_sec: int = 20
    llm_mode: bool = False


@dataclass
class CandidateEval:
    seed: int
    score: float
    cost: float = 1.0
    hint: str = ""
    error: str = ""
    stdout: str = ""
    candidate_code: str = ""
    source: str = "local"
    elapsed_sec: float = 0.0


@dataclass
class SprintResult:
    status: str
    reason: str
    target_file: str
    winner_source: str
    final_score: float
    elapsed_sec: float
    attempt_count: int
    model_calls: int
    quota_backoffs: int
    test_timeouts: int
    total_tokens: int = 0
    token_capture_status: str = "not_applicable_local_only"
    error_codes: list[str] = field(default_factory=list)
    rejection_summary: dict[str, int] = field(default_factory=dict)
    learning_trace: dict[str, Any] = field(default_factory=dict)
    candidates: list[CandidateEval] = field(default_factory=list)
    pytest_cmd: list[str] = field(default_factory=list)
    promotable: bool = False
    patch: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [asdict(c) for c in self.candidates]
        return payload


class LLMCandidateGenerator:
    source = "llm"

    def __init__(self, project_root: Path, safe_mode: bool):
        from nexus.services.gateway import BattlesuitGateway
        self.gateway = BattlesuitGateway(project_root=project_root)
        self.safe_mode = safe_mode

    def generate(self, *, source_code: str, task: str, mutation_hint: str, seed: int) -> tuple[str, dict[str, Any]]:
        def _estimate_tokens(text: str) -> int:
            # Fallback estimate when gateway does not return token usage.
            return max(1, len(text) // 4)

        prompt_text = (
            "You are executing Stage 1 of a Hyper-Sprint (Gladiator mode).\n"
            f"Task: {task}\n"
            f"Strategy/Hint for this candidate: {mutation_hint}\n\n"
            f"[CURRENT SOURCE]\n{source_code}\n\n"
            "Return ONLY the full updated file content in the 'patch' field."
        )
        model_chain = ["gemini-3-flash-preview"] if self.safe_mode else ["gemini-3-flash-preview", "gemini-3.1-pro-preview"]
        quota_backoffs = 0
        model_calls = 0
        last_err = ""
        for idx, model in enumerate(model_chain):
            try:
                model_calls += 1
                out, raw = self.gateway.ask_structured(
                    prompt=prompt_text,
                    payload="Return FULL file content.",
                    phase="R",
                    output_schema={"status": "APPROVED | FAIL", "patch": "Full target file content"},
                    model_name=model,
                )
                code = out.get("patch") or raw
                tokens_used = 0
                token_capture_status = "unknown"
                if isinstance(out, dict):
                    try:
                        tokens_used = int(out.get("tokens_used", 0) or 0)
                    except (TypeError, ValueError):
                        tokens_used = 0
                    token_capture_status = str(out.get("token_capture_status", "unknown") or "unknown")
                if tokens_used <= 0 and model_calls > 0:
                    tokens_used = _estimate_tokens(prompt_text) + _estimate_tokens(str(code))
                    token_capture_status = "estimated"
                return code, {
                    "source": self.source,
                    "model_calls": model_calls,
                    "quota_backoffs": quota_backoffs,
                    "tokens_used": tokens_used,
                    "token_capture_status": token_capture_status,
                }
            except Exception as exc:  # noqa: BLE001
                err = str(exc).lower()
                last_err = str(exc)
                infra_code = classify_infra_block(err)
                if infra_code == "infra_blocked:quota":
                    quota_backoffs += 1
                    delay = get_retry_delay(RetryParams(attempt=quota_backoffs, max_retries=3))
                    time.sleep(delay)
                    continue
                if idx < len(model_chain) - 1:
                    continue
                raise
        raise RuntimeError(last_err or "all_models_failed")

class LocalCandidateGenerator:
    source = "local"

    def generate(self, source_code: str, task: str, mutation_hint: str, seed: int) -> tuple[str, dict[str, Any]]:
        from .local_sprint_mutator import generate_local_candidate
        code = generate_local_candidate(source_code, task, mutation_hint, seed)
        return code, {
            "source": self.source,
            "model_calls": 0,
            "quota_backoffs": 0,
            "tokens_used": 0,
            "token_capture_status": "not_applicable_local_only",
        }

class SprintExecutor:
    def __init__(self, repo_root: Path, scope_files: list[str], pytest_cmd: list[str], timeout_sec: int):
        self.repo_root = repo_root
        self.scope_files = scope_files
        self.pytest_cmd = pytest_cmd
        self.timeout_sec = timeout_sec
        self.broker = SwarmBroker(repo_root)

    def evaluate_candidate(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        evaluator = CandidateEvaluator(self.repo_root, self.pytest_cmd, self.timeout_sec)
        target_rel = self.scope_files[0]
        original = (self.repo_root / target_rel).read_text(encoding="utf-8") if (self.repo_root / target_rel).exists() else ""

        # Swarm handling (Executor-specific) with timing instrumentation
        start_create = time.time()
        swarm_dir = self.broker.acquire(timeout_sec=self.timeout_sec)
        create_elapsed = time.time() - start_create

        if not swarm_dir:
            return CandidateEval(seed=seed, score=0.0, hint=hint, error="broker_timeout", source=source)

        try:
            start_sync = time.time()
            self.broker.sync_scope(swarm_dir, scope_files=self.scope_files)
            sync_elapsed = time.time() - start_sync

            # Use evaluator but on swarm_dir
            evaluator.repo_root = swarm_dir
            start_test = time.time()
            res = evaluator.evaluate(seed=seed, hint=hint, code=code, source=source, target_file=target_rel, original_code=original)
            test_elapsed = time.time() - start_test

            # Record detailed timings in hint or extra (here we use CandidateEval which we'll ensure has enough fields)
            return CandidateEval(
                seed=res.seed,
                score=res.score,
                hint=f"{res.hint} | create:{create_elapsed:.2f}s sync:{sync_elapsed:.2f}s test:{test_elapsed:.2f}s",
                stdout=res.stdout,
                error=res.error,
                candidate_code=res.candidate_code,
                source=res.source,
                elapsed_sec=res.elapsed_sec
            )
        finally:
            self.broker.release(swarm_dir)

class InPlaceSprintExecutor:
    """
    Fast local executor for local-first mode.
    Applies candidate code in-place, runs scoped tests, then restores the original file.
    """

    def __init__(self, repo_root: Path, target_file: str, pytest_cmd: list[str], timeout_sec: int):
        self.repo_root = repo_root
        self.target_file = target_file
        self.pytest_cmd = pytest_cmd
        self.timeout_sec = timeout_sec

    def evaluate_candidate(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        start = time.time()
        target_path = self.repo_root / self.target_file
        original = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        try:
            if code == original:
                return CandidateEval(
                    seed=seed,
                    score=0.2,
                    hint=hint,
                    error="no_change_candidate",
                    candidate_code=code,
                    source=source,
                    elapsed_sec=round(time.time() - start, 4),
                )
            if target_path.suffix == ".py":
                try:
                    compile(code, str(target_path), "exec")
                except SyntaxError as exc:
                    return CandidateEval(
                        seed=seed,
                        score=0.0,
                        hint=hint,
                        error=f"syntax_error:{exc.msg}",
                        candidate_code=code,
                        source=source,
                        elapsed_sec=round(time.time() - start, 4),
                    )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code, encoding="utf-8")
            res = subprocess.run(
                self.pytest_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                cwd=self.repo_root,
            )
            return CandidateEval(
                seed=seed,
                score=1.0 if res.returncode == 0 else 0.4,
                hint=hint,
                stdout=res.stdout,
                candidate_code=code,
                source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        except subprocess.TimeoutExpired as exc:
            return CandidateEval(
                seed=seed,
                score=0.0,
                hint=hint,
                error=str(exc),
                candidate_code=code,
                source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        except Exception as exc:  # noqa: BLE001
            return CandidateEval(
                seed=seed,
                score=0.0,
                hint=hint,
                error=str(exc),
                candidate_code=code,
                source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        finally:
            target_path.write_text(original, encoding="utf-8")


def promote_patch_to_branch(*, repo_root: Path, target_file: str, patch_code: str, score: float, run_id: str) -> str:
    branch_name = f"hyper-sprint/{run_id}"
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_root, check=True, capture_output=True)
    (repo_root / target_file).write_text(patch_code, encoding="utf-8")
    subprocess.run(["git", "add", target_file], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"opt(dayshift): optimize {target_file} (score: {score})"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return branch_name


def write_sprint_report(*, repo_root: Path, result: SprintResult, report_file: str) -> Path:
    report_path = (repo_root / report_file).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return report_path


def run_hyper_sprint(*, repo_root: Path, config: SprintConfig) -> SprintResult:
    start = time.time()
    policy = ResearchPolicy()
    scope_files = [config.target_file] + ([config.test_file] if config.test_file else [])
    effective_timeout = compute_time_budget(config.timeout_sec)
    pytest_cmd = [sys.executable, "-m", "pytest", "-q", "--maxfail=1"] + ([config.test_file] if config.test_file else [])

    target_path = repo_root / config.target_file
    source_code = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    llm_mode_effective = bool(config.llm_mode)
    learn_slo_guard = {
        "phase_slo_pass": False,
        "required_done_ratio": 0.0,
        "active": False,
        "reason": "",
    }
    try:
        from nexus.research.learn_mode import LearnModeService

        learn_slo = LearnModeService(repo_root).read_phase_slo_summary()
        required_done_ratio = float((learn_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0)
        phase_slo_pass = bool(learn_slo.get("phase_slo_pass", False))
        learn_slo_guard["phase_slo_pass"] = phase_slo_pass
        learn_slo_guard["required_done_ratio"] = required_done_ratio
        if llm_mode_effective and (not phase_slo_pass or required_done_ratio < 0.95):
            llm_mode_effective = False
            learn_slo_guard["active"] = True
            learn_slo_guard["reason"] = "learn_phase_slo_not_ready"
    except Exception as exc:  # noqa: BLE001
        learn_slo_guard["reason"] = f"learn_slo_read_error:{exc}"

    llm_generator: Optional[LLMCandidateGenerator] = LLMCandidateGenerator(repo_root, config.safe_mode) if llm_mode_effective else None
    local_generator = LocalCandidateGenerator()
    # Local-first fast path: avoid heavy swarm sync when no external LLM is used.
    if llm_mode_effective:
        executor = SprintExecutor(repo_root, scope_files=scope_files, pytest_cmd=pytest_cmd, timeout_sec=config.stage1_timeout_sec)
    else:
        executor = InPlaceSprintExecutor(
            repo_root=repo_root,
            target_file=config.target_file,
            pytest_cmd=pytest_cmd,
            timeout_sec=config.stage1_timeout_sec,
        )

    candidates: list[CandidateEval] = []
    model_calls = 0
    total_tokens = 0
    token_capture_statuses: set[str] = set()
    quota_backoffs = 0
    test_timeouts = 0
    error_codes: list[str] = []
    learning_trace: dict[str, Any] = {
        "retrieval_hits": 0,
        "retrieval_hints": [],
        "mempalace_verified": False,
        "memory_written": False,
        "arweave_tx_id": None,
        "learn_slo_guard": learn_slo_guard,
    }

    # Learning loop (retrieve): pull recent hints before candidate generation.
    historical_hints: list[str] = []
    try:
        from nexus.research.findings_memory import FindingsMemoryStore

        store = FindingsMemoryStore(repo_root)
        hits = store.search(config.task, scope="both")
        learning_trace["retrieval_hits"] = len(hits)
        for h in hits:
            historical_hints.extend(h.retrieval_hints)
        historical_hints = list(dict.fromkeys(historical_hints))[:3]
        learning_trace["retrieval_hints"] = historical_hints
    except Exception as exc:  # noqa: BLE001
        learning_trace["retrieval_error"] = str(exc)
        store = None

    def _semantic_guard(source: str, candidate: str, task: str, source_label: str = "llm") -> tuple[bool, str]:
        if candidate.strip() == source.strip():
            return False, "no_change_candidate"
        
        # R7: Strict rejection for invalid AST/syntax
        try:
            compile(candidate, "<semantic_guard>", "exec")
        except SyntaxError as exc:
            return False, f"syntax_error: {exc}"

        src_lines = {ln.strip() for ln in source.splitlines() if ln.strip()}
        cand_lines = {ln.strip() for ln in candidate.splitlines() if ln.strip()}
        changed_count = len(cand_lines - src_lines)
        task_l = task.lower()
        feature_words = ("implement", "add", "create", "introduce", "support", "enable")
        
        is_feature = any(w in task_l for w in feature_words)
        is_refactor = "refactor" in task_l
        
        if changed_count < 1:
            return False, "semantic_guard_zero_delta"

        # R9.1: Context-aware delta requirement
        is_trusted_local = str(source_label).lower() == "local"
        
        # If it's a feature from LLM, require at least 2 lines of change to reduce low-quality hallucinations
        if is_feature and not is_trusted_local and changed_count < 2:
            return False, "semantic_guard_low_delta_feature"
            
        return True, ""

    def _build_rejection_summary(items: list[CandidateEval], codes: list[str]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for c in items:
            if c.error:
                key = c.error
                if c.error.startswith("syntax_error:"):
                    key = "syntax_error"
                elif "timed out" in c.error.lower():
                    key = "test_timeout"
                elif "quota" in c.error.lower() or "429" in c.error.lower():
                    key = "quota"
            elif c.score < 1.0:
                key = "pytest_failed"
            else:
                continue
            summary[key] = summary.get(key, 0) + 1
        for code in codes:
            summary[code] = summary.get(code, 0) + 1
        return summary

    def _classify_failure(reason: str, codes: list[str], summary: dict[str, int]) -> str:
        reason_l = str(reason or "").lower()
        normalized_codes = [str(c).lower() for c in (codes or [])]
        if "time_budget_exceeded" in normalized_codes or "time_budget_exceeded" in reason_l:
            return "time_budget_exceeded"
        if "hyper_run_timeout" in normalized_codes or "hyper_run_timeout" in reason_l:
            return "hyper_run_timeout"
        if "stage1_no_passing_candidate" in normalized_codes:
            return "stage1_no_passing_candidate"
        if "stage1_failed" in normalized_codes:
            return "stage1_failed"
        if any(k in normalized_codes for k in ["quota", "429", "capacity"]):
            return "quota_or_capacity"
        if summary.get("syntax_error", 0) > 0:
            return "syntax_error"
        if summary.get("pytest_failed", 0) > 0:
            return "pytest_failed"
        if reason_l and reason_l != "success":
            return reason_l
        return "unknown_failure"

    def _corrective_action_for(failure_class: str) -> str:
        if "timeout" in failure_class:
            return "increase_timeout_or_reduce_scope"
        if failure_class in {"stage1_failed", "stage1_no_passing_candidate"}:
            return "improve_stage1_candidate_generation"
        if failure_class == "quota_or_capacity":
            return "fallback_to_local_or_reduce_llm_load"
        if failure_class == "syntax_error":
            return "strengthen_candidate_syntax_guard"
        if failure_class == "pytest_failed":
            return "tighten_test_aligned_patching"
        if failure_class == "time_budget_exceeded":
            return "reduce_trials_or_raise_wall_time_budget"
        return "review_failure_trace_and_refine_strategy"

    def _persist_learning(
        *,
        status: str,
        reason: str,
        winner_source: str,
        final_score: float,
        summary: dict[str, int],
        codes: list[str],
    ) -> None:
        # Learning loop (govern + write): MemPalace verify -> Findings write (LanceDB sync via repository).
        try:
            from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
            from nexus.services.mem_palace import MemPalace

            local_store = store or FindingsMemoryStore(repo_root)
            failure_class = _classify_failure(reason, codes, summary) if status != "SUCCESS" else "none"
            corrective_action = _corrective_action_for(failure_class)
            card = FindingsCard(
                kind="episodes",
                title=f"Hyper-Sprint {status}: {Path(config.target_file).name}",
                task_id=f"hs-{int(time.time())}",
                tags=["hyper_sprint", status.lower(), winner_source],
                retrieval_hints=learning_trace.get("retrieval_hints", []),
                confidence="high" if status == "SUCCESS" else "medium",
                body=(
                    f"Task: {config.task}\n"
                    f"Target: {config.target_file}\n"
                    f"Status: {status}\n"
                    f"Reason: {reason}\n"
                    f"Score: {final_score}\n"
                    f"Error Codes: {codes}\n"
                    f"Rejection Summary: {summary}\n"
                ),
                extra={
                    "winner_source": winner_source,
                    "attempt_count": len(candidates),
                    "error_codes": codes,
                    "rejection_summary": summary,
                    "failure_class": failure_class,
                    "target_file": config.target_file,
                    "task_signature": config.task,
                    "corrective_action": corrective_action,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            palace = MemPalace(str(repo_root))
            clean = palace.verify([card.to_dict()])
            if not clean:
                learning_trace["mempalace_verified"] = False
                learning_trace["memory_rejected"] = True
                return
            learning_trace["mempalace_verified"] = True
            clean_card = FindingsCard.from_dict(clean[0])
            local_store.write(clean_card)
            learning_trace["memory_written"] = True
            tx_id = palace.trigger_arweave_distillation(clean[0])
            learning_trace["arweave_tx_id"] = tx_id
        except Exception as exc:  # noqa: BLE001
            learning_trace["memory_error"] = str(exc)
        try:
            from nexus.research.learn_mode import LearnModeService

            learn_bridge = LearnModeService(repo_root).sync_phase_learning_closure(
                topic=config.task,
                metrics={
                    "coverage": 1.0 if status == "SUCCESS" else 0.5,
                    "self_question_pass_rate": 1.0 if status == "SUCCESS" else 0.4,
                    "citation_valid_ratio": 1.0 if status == "SUCCESS" else 0.8,
                    "stale_claims_count": 0,
                    "conflict_count": int(summary.get("semantic_guard_low_delta_feature", 0)),
                },
                phase_status={
                    "P": "SUCCESS",
                    "X": "SUCCESS" if learning_trace.get("retrieval_hits", 0) > 0 else "PARTIAL",
                    "D": "SUCCESS",
                    "R": "SUCCESS" if status == "SUCCESS" else "FAILED",
                    "A": "SUCCESS" if "semantic_guard" not in codes else "PARTIAL",
                    "C": "SUCCESS" if learning_trace.get("mempalace_verified") else "PARTIAL",
                },
            )
            learning_trace["learn_phase_bridge"] = {
                "status": learn_bridge.get("status", "UNKNOWN"),
                "entries_written": learn_bridge.get("entries_written", 0),
            }
        except Exception as exc:  # noqa: BLE001
            learning_trace["learn_phase_bridge_error"] = str(exc)

    for idx in range(max(1, config.candidate_count)):
        hint = policy.get_mutation_hint(
            idx % max(1, config.candidate_count),
            task_desc=config.task,
            historical_hints=historical_hints,
        )
        used_source = "local"
        try:
            if llm_generator is not None:
                try:
                    candidate_code, meta = llm_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=hint,
                        seed=idx,
                    )
                    used_source = str(meta.get("source", "llm"))
                except Exception as llm_exc:  # noqa: BLE001
                    err = str(llm_exc).lower()
                    if any(p in err for p in ["quota", "429", "rate limit", "resource exhausted", "capacity"]):
                        quota_backoffs += 1
                        error_codes.append("quota")
                        error_codes.append("llm_fallback_local")
                    else:
                        error_codes.append("llm_error")
                    candidate_code, meta = local_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=hint,
                        seed=idx,
                    )
                    used_source = str(meta.get("source", "local"))
            else:
                candidate_code, meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=hint,
                    seed=idx,
                )
                used_source = str(meta.get("source", "local"))
            model_calls += int(meta.get("model_calls", 0))
            total_tokens += int(meta.get("tokens_used", 0) or 0)
            token_capture_statuses.add(str(meta.get("token_capture_status", "unknown") or "unknown"))
            quota_backoffs += int(meta.get("quota_backoffs", 0))
            guard_ok, guard_reason = _semantic_guard(source_code, candidate_code, config.task, used_source)
            if not guard_ok:
                # R8: If LLM fails semantic guard, try one Local Candidate as a backup
                if llm_generator is not None:
                    candidate_code, meta = local_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=hint,
                        seed=idx + 1000,
                    )
                    used_source = str(meta.get("source", "local_guard_fallback"))
                    guard_ok, guard_reason = _semantic_guard(source_code, candidate_code, config.task, used_source)
                
                if not guard_ok:
                    ev = CandidateEval(seed=idx, score=0.0, hint=hint, error=guard_reason, candidate_code=candidate_code, source=used_source)
                    error_codes.append("semantic_guard")
                else:
                    ev = executor.evaluate_candidate(seed=idx, hint=hint, code=candidate_code, source=used_source)
            else:
                ev = executor.evaluate_candidate(seed=idx, hint=hint, code=candidate_code, source=used_source)
        except Exception as exc:  # noqa: BLE001
            ev = CandidateEval(seed=idx, score=0.0, hint=hint, error=str(exc), source=used_source)
        if "timed out" in (ev.error or "").lower():
            test_timeouts += 1
            error_codes.append("test_timeout")
        if "quota" in (ev.error or "").lower() or "429" in (ev.error or "").lower():
            error_codes.append("quota")
        candidates.append(ev)
        if config.safe_mode and ev.score >= 1.0:
            break

        if config.safe_mode:
            time.sleep(1.0)

# R1.1: Emergency Fallback Valve - Ensure we match baseline if all else fails
    has_success = any(c.score >= 1.0 for c in candidates)
    tried_local = any(c.source == "local" for c in candidates)
    if not has_success and not tried_local:
        # Perform one last verified local run as "local" source
        code, meta = local_generator.generate(source_code=source_code, task=config.task, mutation_hint="emergency_baseline_match", seed=0)
        if code != source_code:
            guard_ok, _ = _semantic_guard(source_code, code, config.task, meta.get("source", "local"))
            if guard_ok:
                ev = executor.evaluate_candidate(seed=999, hint="emergency_fallback", code=code, source=meta.get("source", "local"))
                candidates.append(ev)

    if not candidates:
        return SprintResult(
            status="FAILED",
            reason=SprintOutcome.GENERATION_FAIL.value,
            target_file=config.target_file,
            winner_source="unknown",
            final_score=0.0,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=0,
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            total_tokens=total_tokens,
            token_capture_status=(
                "measured"
                if total_tokens > 0
                else (
                    "missing_gateway_stats"
                    if model_calls > 0 and ("unknown" in token_capture_statuses or "ok" in token_capture_statuses)
                    else ("missing" if model_calls > 0 else "not_applicable_local_only")
                )
            ),
            error_codes=sorted(set(error_codes)),
            rejection_summary={},
            learning_trace=learning_trace,
            pytest_cmd=pytest_cmd,
        )

    best = max(candidates, key=lambda c: c.score)
    if best.score < 1.0:
        final_codes = sorted(set(error_codes + [SprintOutcome.STAGE1_FAILED.value]))
        rejection_summary = _build_rejection_summary(candidates, final_codes)
        _persist_learning(
            status="FAILED",
            reason=SprintOutcome.STAGE1_NO_PASSING_CANDIDATE.value,
            winner_source=best.source,
            final_score=best.score,
            summary=rejection_summary,
            codes=final_codes,
        )
        return SprintResult(
            status="FAILED",
            reason=SprintOutcome.STAGE1_NO_PASSING_CANDIDATE.value,
            target_file=config.target_file,
            winner_source=best.source,
            final_score=best.score,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=len(candidates),
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            total_tokens=total_tokens,
            token_capture_status=(
                "measured"
                if total_tokens > 0
                else (
                    "missing_gateway_stats"
                    if model_calls > 0 and ("unknown" in token_capture_statuses or "ok" in token_capture_statuses)
                    else ("missing" if model_calls > 0 else "not_applicable_local_only")
                )
            ),
            error_codes=final_codes,
            rejection_summary=rejection_summary,
            learning_trace=learning_trace,
            candidates=candidates,
            pytest_cmd=pytest_cmd,
            patch=best.candidate_code,
        )

    final_score = best.score
    final_patch = best.candidate_code or source_code
    final_reason = "stage1_pass"
    # Stage 2 is optional enhancement only. Core success must not depend on external quota.
    if llm_mode_effective and "quota" not in error_codes:
        swarm_dir = SwarmBroker(repo_root).acquire(timeout_sec=config.timeout_sec)
        if swarm_dir:
            try:
                optimizer = DayShiftOptimizer(
                    project_root=repo_root,
                    swarm_dir=swarm_dir,
                    target_file=config.target_file,
                    task_desc=config.task,
                    max_rounds=config.max_rounds,
                    convergence_patience=2,
                    test_timeout_sec=config.timeout_sec,
                    use_llm_scoring=not config.safe_mode,
                    min_round_delay_sec=1.5 if config.safe_mode else 0.2,
                    model_name="gemini-3-flash-preview" if config.safe_mode else "gemini-3.1-pro-preview",
                    fallback_model_name="gemini-3.1-pro-preview" if config.safe_mode else "gemini-3-flash-preview",
                )
                result = optimizer.optimize()
                if result.get("status") == "SUCCESS":
                    final_score = float(result.get("score", final_score))
                    final_patch = str(result.get("patch", final_patch))
                    final_reason = "dayshift_improved"
                else:
                    final_reason = "dayshift_no_improve"
            finally:
                SwarmBroker(repo_root).release(swarm_dir)
    elif llm_mode_effective and "quota" in error_codes:
        final_reason = "dayshift_skipped_due_quota_fallback"
    elif config.llm_mode and not llm_mode_effective:
        error_codes.append("learn_slo_block")
        final_reason = "dayshift_skipped_due_learn_slo_guard"

    final_codes = sorted(set(error_codes))
    rejection_summary = _build_rejection_summary(candidates, error_codes)
    _persist_learning(
        status="SUCCESS",
        reason=final_reason,
        winner_source=best.source,
        final_score=final_score,
        summary=rejection_summary,
        codes=final_codes,
    )
    return SprintResult(
        status="SUCCESS",
        reason=final_reason,
        target_file=config.target_file,
        winner_source=best.source,
        final_score=final_score,
        elapsed_sec=round(time.time() - start, 4),
        attempt_count=len(candidates),
        model_calls=model_calls,
        quota_backoffs=quota_backoffs,
        test_timeouts=test_timeouts,
        total_tokens=total_tokens,
        token_capture_status=(
            "measured"
            if total_tokens > 0
            else (
                "missing_gateway_stats"
                if model_calls > 0 and ("unknown" in token_capture_statuses or "ok" in token_capture_statuses)
                else ("missing" if model_calls > 0 else "not_applicable_local_only")
            )
        ),
        error_codes=final_codes,
        rejection_summary=rejection_summary,
        learning_trace=learning_trace,
        candidates=candidates,
        pytest_cmd=pytest_cmd,
        promotable=final_score >= 0.9,
        patch=final_patch,
    )
