from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.day_shift_optimizer import DayShiftOptimizer
from nexus.research.local_sprint_mutator import generate_local_candidate
from nexus.research.swarm_broker import SwarmBroker


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
    error_codes: list[str] = field(default_factory=list)
    candidates: list[CandidateEval] = field(default_factory=list)
    pytest_cmd: list[str] = field(default_factory=list)
    promotable: bool = False
    patch: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [asdict(c) for c in self.candidates]
        return payload


class LocalCandidateGenerator:
    source = "local"

    def generate(self, *, source_code: str, task: str, mutation_hint: str, seed: int) -> tuple[str, dict[str, Any]]:
        code = generate_local_candidate(source_code, task, mutation_hint, seed)
        return code, {"source": self.source, "model_calls": 0, "quota_backoffs": 0}


class LLMCandidateGenerator:
    source = "llm"

    def __init__(self, project_root: Path, safe_mode: bool):
        from nexus.services.gateway import BattlesuitGateway

        self.gateway = BattlesuitGateway(project_root=project_root)
        self.safe_mode = safe_mode

    def generate(self, *, source_code: str, task: str, mutation_hint: str, seed: int) -> tuple[str, dict[str, Any]]:
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
        for model in model_chain:
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
                return code, {"source": self.source, "model_calls": model_calls, "quota_backoffs": quota_backoffs}
            except Exception as exc:  # noqa: BLE001
                err = str(exc).lower()
                last_err = str(exc)
                if any(p in err for p in ["quota", "429", "rate limit", "resource exhausted", "capacity"]):
                    quota_backoffs += 1
                    time.sleep(1.5 if self.safe_mode else 0.5)
                    continue
                raise
        raise RuntimeError(last_err or "all_models_failed")


class SprintExecutor:
    def __init__(self, repo_root: Path, scope_files: list[str], pytest_cmd: list[str], timeout_sec: int):
        self.repo_root = repo_root
        self.scope_files = scope_files
        self.pytest_cmd = pytest_cmd
        self.timeout_sec = timeout_sec
        self.broker = SwarmBroker(repo_root)

    def evaluate_candidate(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        start = time.time()
        swarm_dir = self.broker.acquire(timeout_sec=self.timeout_sec)
        if not swarm_dir:
            return CandidateEval(seed=seed, score=0.0, hint=hint, error="broker_timeout", source=source)
        try:
            self.broker.sync_scope(swarm_dir, scope_files=self.scope_files)
            (swarm_dir / self.scope_files[0]).write_text(code, encoding="utf-8")
            res = subprocess.run(
                self.pytest_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                cwd=swarm_dir,
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
    pytest_cmd = ["uv", "run", "pytest", "-q", "--maxfail=1"] + ([config.test_file] if config.test_file else [])

    target_path = repo_root / config.target_file
    source_code = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    llm_generator: Optional[LLMCandidateGenerator] = LLMCandidateGenerator(repo_root, config.safe_mode) if config.llm_mode else None
    local_generator = LocalCandidateGenerator()
    # Local-first fast path: avoid heavy swarm sync when no external LLM is used.
    if config.llm_mode:
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
    quota_backoffs = 0
    test_timeouts = 0
    error_codes: list[str] = []

    for idx in range(max(1, config.candidate_count)):
        hint = policy.get_mutation_hint(idx % max(1, config.candidate_count), task_desc=config.task)
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
            quota_backoffs += int(meta.get("quota_backoffs", 0))
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

    if not candidates:
        return SprintResult(
            status="FAILED",
            reason="no_candidates",
            target_file=config.target_file,
            winner_source="unknown",
            final_score=0.0,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=0,
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            error_codes=sorted(set(error_codes)),
            pytest_cmd=pytest_cmd,
        )

    best = max(candidates, key=lambda c: c.score)
    if best.score < 1.0:
        return SprintResult(
            status="FAILED",
            reason="stage1_no_passing_candidate",
            target_file=config.target_file,
            winner_source=best.source,
            final_score=best.score,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=len(candidates),
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            error_codes=sorted(set(error_codes + ["stage1_failed"])),
            candidates=candidates,
            pytest_cmd=pytest_cmd,
            patch=best.candidate_code,
        )

    final_score = best.score
    final_patch = best.candidate_code or source_code
    final_reason = "stage1_pass"
    # Stage 2 is optional enhancement only. Core success must not depend on external quota.
    if config.llm_mode and "quota" not in error_codes:
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
    elif config.llm_mode and "quota" in error_codes:
        final_reason = "dayshift_skipped_due_quota_fallback"

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
        error_codes=sorted(set(error_codes)),
        candidates=candidates,
        pytest_cmd=pytest_cmd,
        promotable=final_score >= 0.9,
        patch=final_patch,
    )
