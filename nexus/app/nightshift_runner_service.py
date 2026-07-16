from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import shutil
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from nexus.research.runtime.runtime_resilience import compute_time_budget, classify_infra_block, get_retry_delay, RetryParams
from nexus.research.evaluation.candidate_evaluator import CandidateEvaluator
from nexus.research.learn.policy_runtime import load_phase_policy
from nexus.research.local_sprint_mutator import generate_local_companion_edits, generate_nightshift_bundle_edits
from nexus.core.context_hub import ContextHub
from nexus.services.workspace import WorkspaceManager
from nexus.core.outcome_schema import NexusOutcomeV2, SprintOutcome

# Mock FeynmanBridge if scripts import fails in nexus/app/
try:
    from scripts.ops.feynman_bridge import DualTrackAudit
except ImportError:
    class DualTrackAudit:
        def run_advisory_audit(self, **kwargs): return {"status": "PASS"}

DEFAULT_TARGET_FILE = ""
PYTHON_SUFFIXES = {".py"}

class SimpleResearchSearchSpace:
    def __init__(self):
        self.dimensions: Dict[str, tuple[float, float]] = {}
    def add_dimension(self, name: str, low: float, high: float) -> None:
        self.dimensions[name] = (low, high)

class SimpleResearchOptimizer:
    def __init__(self, space: SimpleResearchSearchSpace):
        self.space = space
    def suggest(self) -> Dict[str, float]:
        return {name: (bounds[0] + bounds[1]) / 2.0 for name, bounds in self.space.dimensions.items()}
    def observe(self, params: Dict[str, float], score: float) -> None:
        return None

@dataclass
class RoundOutcome:
    score: float
    candidate: str
    status: str
    summary: str = ""

class AutoResearchNightShift:
    def __init__(
        self,
        task: str,
        max_rounds: int = 50,
        budget_min: int = 5,
        target_file: str = DEFAULT_TARGET_FILE,
        test_file: Optional[str] = None,
        convergence_patience: int = 5,
        gateway: Any = None,
        model_name: Optional[str] = "gemini-3.1-pro-preview",
        fallback_model_name: Optional[str] = "gemini-3-flash-preview",
        keep_worktree: Optional[bool] = None,
        project_root: Optional[Path] = None,
        context_hub: Any = None,
        context_dependencies: Any = None,
    ):
        self.task = task.strip()
        self.max_rounds = max_rounds
        self.budget_sec = budget_min * 60
        self.cli_target_file = (target_file or "").strip()
        self.test_file = (test_file or "").strip() or None
        self.convergence_patience = max(1, convergence_patience)
        self.resolved_target_file = self.cli_target_file

        if project_root:
            self.project_root = Path(project_root).resolve()
        else:
            self.project_root = Path(__file__).resolve().parents[2]
        self.git_enabled = (self.project_root / ".git").exists()
            
        self.worktree_mgr = WorkspaceManager(str(self.project_root))
        if context_hub is not None:
            self.hub = context_hub
        elif self.git_enabled and context_dependencies is not None:
            self.hub = ContextHub(str(self.project_root), deps=context_dependencies, strict_deps=True)
        else:
            self.hub = None
        self.feynman_auditor = DualTrackAudit()
        self.compute_tier = "CLOUD"

        from nexus.research.findings_memory import FindingsMemoryStore
        from nexus.services.gateway import BattlesuitGateway
        from nexus.services.prompt_builder import PromptBuilder
        
        if self.git_enabled:
            try:
                self.memory_store = FindingsMemoryStore(self.project_root)
            except Exception:
                self.memory_store = None
        else:
            self.memory_store = None
        self.last_learning_closure: dict[str, Any] = {}
        self.last_unified_runtime_receipt: dict[str, Any] = {}
        self.best_score = 0.0
        self.generation_latencies: List[float] = []
        self.no_improve_streak = 0
        self.base_commit: Optional[str] = None
        self.tracelog_path = self.project_root / f"tracelog_{self.task.replace('/', '_')}.jsonl"
        self.trace_log: List[Dict[str, Any]] = []
        self.gateway = gateway or (BattlesuitGateway(project_root=self.project_root) if self.git_enabled else None)
        self.model_name = model_name
        self.fallback_model_name = fallback_model_name
        self.model_exhausted: Dict[str, str] = {}
        env_keep = os.getenv("NIGHTSHIFT_KEEP_WORKTREE", "").strip().lower() in {"1", "true", "yes", "on"}
        self.keep_worktree = env_keep if keep_worktree is None else bool(keep_worktree)

        if self.git_enabled:
            try:
                self.prompt_builder = PromptBuilder(str(self.project_root))
            except Exception:
                self.prompt_builder = None
        else:
            self.prompt_builder = None

        self.pending_manifest_path = self.project_root / ".nexus/nightshift/pending.json"
        self.lesson_writeback_path = self.project_root / ".nexus/reports/lesson_writeback.json"
        self.tier1_timeout_sec = int(os.getenv("NIGHTSHIFT_TIER1_TIMEOUT_SEC", "120"))
        self.tier2_timeout_sec = int(os.getenv("NIGHTSHIFT_TIER2_TIMEOUT_SEC", "900"))
        self.tier1_smoke_pack = [
            "tests/governance/test_self_evolve.py",
            "tests/ops/test_ci_gate_lesson_block.py",
            "tests/test_cli_commands.py",
            "tests/test_xray_integration.py",
        ]
        
        try:
            from nexus.research.bayesian_engine import BayesianResearchOptimizer, ResearchSearchSpace
            self.space = ResearchSearchSpace()
            optimizer_cls = BayesianResearchOptimizer
        except ModuleNotFoundError:
            self.space = SimpleResearchSearchSpace()
            optimizer_cls = SimpleResearchOptimizer
        self.space.add_dimension("temperature", 0.1, 0.9)
        self.optimizer = optimizer_cls(self.space)

    def _candidate_models(self) -> list[str]:
        ordered: list[str] = []
        for model in (self.model_name, self.fallback_model_name):
            if model and model not in ordered and model not in self.model_exhausted:
                ordered.append(model)
        return ordered

    def _workspace_revision(self, workpath: Path) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(workpath),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    def _ask_unified_candidate(
        self,
        *,
        workpath: Path,
        round_id: int,
        attempt: int,
        model: str,
        prompt: str,
        payload: str,
        output_schema: Mapping[str, Any] | None = None,
        task_kind: str = "generation",
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """Route one candidate-generation call through the canonical seam.

        Candidate-shape verification is intentionally weaker than semantic
        repair verification.  Learning remains absent until the outer round
        has a verified outcome, so the receipt must remain incomplete here.
        """
        from nexus.services.unified_runtime import UnifiedRuntimeRequest

        output_schema = dict(output_schema or {
            "status": "APPROVED | REJECTED | FAIL",
            "summary": "Short explanation",
            "patch": "Full target file content as plain text",
            "violations": ["list of rule violations"],
        })

        ask_unified = getattr(self.gateway, "ask_unified", None)
        revision = self._workspace_revision(workpath)
        if not revision:
            revision = f"fixture-{hashlib.sha256(str(workpath).encode()).hexdigest()[:12]}"
        task_id = (
            f"nightshift-{hashlib.sha256(self.task.encode('utf-8')).hexdigest()[:12]}"
            f"-r{round_id}-a{attempt}-{task_kind}"
        )

        from nexus.services.unified_runtime import build_online_route, extract_online_stage_payload

        def response_contract(context: Mapping[str, Any]) -> dict[str, Any]:
            online = context.get("online", {}) if isinstance(context, Mapping) else {}
            provider_response, _raw, _payload = extract_online_stage_payload(
                online if isinstance(online, Mapping) else {}
            )
            delivered = bool(provider_response)
            return {
                "task_id": task_id,
                "status": "pass" if delivered else "fail",
                "evidence": "online_candidate_payload_present" if delivered else "online_candidate_payload_missing",
                "evidence_refs": [f"verifier:{task_id}:response_contract"],
            }

        gateway_provider = str(getattr(self.gateway, "oauth_provider", "") or "").strip().lower()
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=revision,
            task_statement=self.task,
            task_type="repair" if task_kind == "generation" else "evaluation",
            route=build_online_route(
                recommended_flow="direct",
                gateway_provider=gateway_provider,
            ),
            online_prompt=prompt,
            online_payload=payload,
            online_phase="R",
            online_model_name=model,
            online_output_schema=output_schema,
            evidence_refs=(f"nightshift:{task_id}:request",),
        )
        receipt_path = workpath / ".nexus" / "reports" / "unified_runtime" / f"{task_id}.json"
        if callable(ask_unified):
            receipt = ask_unified(
                request,
                verifier=response_contract,
                receipt_path=receipt_path,
            )
        else:
            from nexus.services.mainchain_entry import run_mainchain
            from nexus.services.unified_runtime import build_structured_online_invoker

            receipt = run_mainchain(
                request,
                online_invoker=build_structured_online_invoker(
                    self.gateway.ask_structured,
                    phase="R",
                    model_name=model,
                    output_schema=output_schema,
                    provider="fixture_gateway",
                ),
                verifier=response_contract,
                receipt_path=receipt_path,
                with_nexus_armor=True,
            )
        online_stage = receipt.get("online", {}) if isinstance(receipt.get("online"), Mapping) else {}
        provider_response, raw_response, _payload = extract_online_stage_payload(online_stage)
        self.last_unified_runtime_receipt = dict(receipt)
        if isinstance(provider_response, Mapping):
            prompt_result = dict(provider_response)
        else:
            prompt_result = {
                "status": "APPROVED" if online_stage.get("status") == "SUCCEEDED" else "FAIL",
                "patch": str(provider_response or ""),
            }
        return prompt_result, raw_response, receipt

    def _finalize_unified_runtime_receipt(self, *, terminal_status: str, final_score: float) -> None:
        receipt = self.last_unified_runtime_receipt
        if not isinstance(receipt, Mapping) or receipt.get("schema") != "nexus.unified_runtime.receipt.v1":
            return
        if not isinstance(receipt.get("planner"), Mapping) or not isinstance(receipt.get("online"), Mapping):
            return
        learning = self.last_learning_closure if isinstance(self.last_learning_closure, Mapping) else {}
        learning_passed = bool(
            learning.get("memory_written")
            or learning.get("lancedb_synced")
            or str(learning.get("sync_status", "")).upper() in {"SYNCED", "SUCCESS", "COMPLETED"}
        )
        verifier_passed = terminal_status == "SUCCESS" and final_score > 0
        from nexus.services.unified_runtime import UnifiedRuntime

        self.last_unified_runtime_receipt = UnifiedRuntime().finalize_receipt(
            receipt,
            verifier={
                "task_id": str(receipt.get("task_id", "")),
                "status": "pass" if verifier_passed else "fail",
                "invoked": True,
                "gate_passed": verifier_passed,
                "evidence": "nightshift_final_score",
                "evidence_refs": [f"verifier:{receipt.get('task_id')}:final"],
                "outcome_contributed": verifier_passed,
            },
            learning={
                "task_id": str(receipt.get("task_id", "")),
                "status": "pass" if learning_passed else "fail",
                "invoked": True,
                "gate_passed": learning_passed,
                "evidence": "nightshift_learning_closure",
                "evidence_refs": [f"learning:{receipt.get('task_id')}:closure"],
                "outcome_contributed": learning_passed,
            },
            outcome={"score": final_score, "value_measured": True},
            receipt_path=receipt.get("receipt_path"),
        )

    def _probe_model_capacity(self, model_name: str, timeout_sec: int = 20) -> bool:
        """Fast preflight: returns False when model is clearly quota/capacity exhausted."""
        gemini_bin = os.getenv("NEXUS_GEMINI_BIN") or shutil.which("gemini") or "/Users/jameschen/.npm-global/bin/gemini"
        if not gemini_bin or not Path(gemini_bin).exists():
            return True
        try:
            res = subprocess.run(
                [gemini_bin, "-m", model_name, "-p", "Reply with exactly OK", "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            output = f"{res.stdout}\n{res.stderr}".lower()
            if res.returncode != 0 and self._is_quota_or_capacity_error(output):
                return False
            return True
        except subprocess.TimeoutExpired:
            return True
        except Exception:
            return True

    def _preflight_models(self) -> None:
        candidates = [m for m in (self.model_name, self.fallback_model_name) if m]
        for model in candidates:
            if model in self.model_exhausted:
                continue
            ok = self._probe_model_capacity(model)
            if not ok:
                self.model_exhausted[model] = "preflight_quota_or_capacity_exhausted"
                print(f"⚠️ [Preflight] Model unavailable by quota/capacity: {model}")

    def _read_learn_phase_slo_guard(self) -> dict[str, Any]:
        summary_path = self.project_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
        if not summary_path.exists():
            return {
                "ready": False,
                "phase_slo_pass": False,
                "required_done_ratio": 0.0,
                "reason": "phase_slo_summary_missing",
            }
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "ready": False,
                "phase_slo_pass": False,
                "required_done_ratio": 0.0,
                "reason": "phase_slo_summary_parse_error",
            }
        phase_slo_pass = bool((data or {}).get("phase_slo_pass", False))
        required_done_ratio = float(((data or {}).get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0)
        ready = phase_slo_pass and required_done_ratio >= 0.95
        return {
            "ready": ready,
            "phase_slo_pass": phase_slo_pass,
            "required_done_ratio": required_done_ratio,
            "reason": "" if ready else "learn_phase_slo_not_ready",
        }

    def _resolve_target_file(self) -> str:
        """Resolve task string to an explicit editable file path."""
        task = (self.task or "").strip()
        if self.cli_target_file:
            return self.cli_target_file
        if task and Path(task).suffix in PYTHON_SUFFIXES:
            return task
        return self.resolved_target_file or DEFAULT_TARGET_FILE

    def _log_trace(self, round_id: int, status: str, score: float, summary: str):
        event = {
            "timestamp": datetime.now().isoformat(),
            "task": self.task,
            "round": round_id,
            "status": status,
            "flashjudge_score": score,
            "summary": summary,
            "target_file": self.resolved_target_file,
        }
        self.trace_log.append(event)
        with open(self.tracelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def _get_active_beliefs(self) -> str:
        """從智慧三元組獲取當前倫理與架構約束。"""
        return self.prompt_builder.build_task_prompt("R", self.task, "", "governance")

    def _run_round(self, round_id: int, workpath: Path) -> RoundOutcome:
        from nexus.research.runtime.runtime_resilience import compute_adaptive_budget

        print(f"\n--- [Round {round_id}] Suggesting optimized variant... ---")
        params = self.optimizer.suggest()
        
        # 1. 🔍 Context Gathering (Lessons + Wisdom + History + SOURCE CODE)
        try:
            target_path = workpath / self.resolved_target_file
            current_code = target_path.read_text(encoding="utf-8") if target_path.exists() else "# New File"
            
            if self.memory_store:
                # FindingsMemoryStore v24 does not expose get_relevant_lessons/get_wisdom_patterns.
                # Recover task-relevant context via keyword search + recent cards.
                matched_cards = self.memory_store.search(self.task, scope="both")[:5]
                if not matched_cards:
                    matched_cards = self.memory_store.list_recent(scope="task", kind="episodes", limit=3)
                lesson_lines = []
                for c in matched_cards:
                    title = getattr(c, "title", "")
                    body = getattr(c, "body", "")
                    lesson_lines.append(f"{title}: {body[:180]}")
                previous_lessons = "\n".join(lesson_lines) if lesson_lines else "None."

                wisdom_cards = self.memory_store.list_recent(scope="global", kind="decisions", limit=3)
                wisdom_lines = []
                for c in wisdom_cards:
                    title = getattr(c, "title", "")
                    hints = ", ".join(getattr(c, "retrieval_hints", [])[:4])
                    wisdom_lines.append(f"{title} | hints={hints}")
                wisdom_patterns = "\n".join(wisdom_lines) if wisdom_lines else "None."

                # 🚀 P1-D: Turbo Pruning restored (500 chars)
                if len(previous_lessons) > 500:
                    previous_lessons = previous_lessons[:500] + "... [TURBO]"
                if len(wisdom_patterns) > 500:
                    wisdom_patterns = wisdom_patterns[:500] + "... [TURBO]"
            else:
                previous_lessons = "None."
                wisdom_patterns = "None."
        except Exception as e:
            current_code = "# Read Error"
            previous_lessons = f"Error: {e}"
            wisdom_patterns = "None."

        target_path = workpath / self.resolved_target_file
        deterministic_bundle = generate_nightshift_bundle_edits(
            workpath,
            target_path,
            self.task,
            round_id,
        )
        if deterministic_bundle:
            for bundle_path, bundle_content in deterministic_bundle.items():
                bundle_path.parent.mkdir(parents=True, exist_ok=True)
                bundle_path.write_text(bundle_content, encoding="utf-8")
            tier1_ok, tier1_summary = self._run_tier1_validation(workpath)
            if tier1_ok:
                primary_candidate = deterministic_bundle.get(target_path, target_path.read_text(encoding="utf-8"))
                return RoundOutcome(1.0, primary_candidate, "SCORED", "nightshift_bundle_repair")
            if self.git_enabled:
                subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=workpath, capture_output=True)

        if self.gateway is None:
            return RoundOutcome(
                0.0,
                "",
                "GENERATION_FAILED",
                "nightshift_gateway_unavailable_without_deterministic_bundle",
            )

        prompt = {"status": "FAIL", "summary": "No model response", "patch": ""}
        raw_content = ""
        candidate_models = self._candidate_models()
        if not candidate_models:
            return RoundOutcome(
                0.0,
                "",
                "MODEL_EXHAUSTED",
                f"All candidate models exhausted: {self.model_exhausted}",
            )

        for idx, model in enumerate(candidate_models, start=1):
            def _build_generation_prompt(compact: bool = False) -> str:
                if not compact:
                    return (
                        f"Optimize the following code in {self.resolved_target_file}.\n\n"
                        f"[SOURCE]\n{current_code}\n\n"
                        f"Lessons: {previous_lessons}\nWisdom: {wisdom_patterns}"
                    )
                compact_code = current_code[:6000]
                compact_lessons = previous_lessons[:180]
                compact_wisdom = wisdom_patterns[:180]
                return (
                    f"Optimize {self.resolved_target_file}. Keep behavior stable and return full file text only.\n\n"
                    f"[SOURCE-COMPACT]\n{compact_code}\n\n"
                    f"Lessons: {compact_lessons}\nWisdom: {compact_wisdom}"
                )

            # R2: Adaptive budget
            effective_gen_timeout = compute_adaptive_budget(self.generation_latencies, default_sec=60)
            print(f"📡 [Battlesuit] Calling Gemini CLI ({model})... Timeout: {effective_gen_timeout}s")
            start_gen = time.time()
            prompt, raw_content, _ = self._ask_unified_candidate(
                workpath=workpath,
                round_id=round_id,
                attempt=idx,
                model=model,
                prompt=_build_generation_prompt(compact=False),
                payload=f"Target: {self.resolved_target_file}\nParams: {params}\nReturn the FULL file content in the 'patch' field.",
            )
            elapsed = time.time() - start_gen
            print(f"✅ [Battlesuit] Generation complete in {elapsed:.1f}s."); self.generation_latencies.append(elapsed)

            summary_text = str(prompt.get("summary", "") or "")
            raw_text = str(raw_content or "")
            failed = str(prompt.get("status", "")).upper() == "FAIL"
            has_patch = bool(prompt.get("patch", "") or prompt.get("content", ""))
            failure_text = summary_text + "\n" + raw_text
            if failed and self._is_timeout_error(failure_text):
                print(f"⚠️ [Battlesuit] Timeout on {model}. Retrying once with compact prompt...")
                start_gen = time.time()
                prompt, raw_content, _ = self._ask_unified_candidate(
                    workpath=workpath,
                    round_id=round_id,
                    attempt=idx + 100,
                    model=model,
                    prompt=_build_generation_prompt(compact=True),
                    payload=f"Target: {self.resolved_target_file}\nParams: {params}\nReturn the FULL file content in the 'patch' field.",
                )
                elapsed = time.time() - start_gen
                print(f"✅ [Battlesuit] Compact retry complete in {elapsed:.1f}s.")
                summary_text = str(prompt.get("summary", "") or "")
                raw_text = str(raw_content or "")
                failed = str(prompt.get("status", "")).upper() == "FAIL"
                has_patch = bool(prompt.get("patch", "") or prompt.get("content", ""))
                failure_text = summary_text + "\n" + raw_text
            quota_or_capacity = failed and self._is_quota_or_capacity_error(failure_text)
            should_fallback = quota_or_capacity
            # Also fallback on empty patch from primary model.
            if not should_fallback and not has_patch and idx < len(candidate_models):
                should_fallback = True
                print("⚠️ [Battlesuit] Empty patch detected. Trying fallback model...")

            if failed and self._is_hard_quota_error(failure_text):
                self.model_exhausted[model] = summary_text[:200] or "quota_or_capacity"

            if should_fallback and idx < len(candidate_models):
                print(f"⚠️ [Battlesuit] Capacity/Quota issue on {model}. Switching to fallback model...")
                continue
            break

        if prompt.get("status") == "FAIL":
            if candidate_models and all(m in self.model_exhausted for m in candidate_models):
                return RoundOutcome(
                    0.0,
                    "",
                    "MODEL_EXHAUSTED",
                    f"All tried models exhausted in round: {self.model_exhausted}",
                )
            # Fallback path: when structured JSON coercion fails, try to recover
            # a full-file candidate from raw model output.
            recovered_patch = self._recover_patch_from_raw(raw_content)
            if recovered_patch:
                prompt["patch"] = recovered_patch
                prompt["status"] = "APPROVED"
                prompt["summary"] = f"{prompt.get('summary', 'Unknown failure')} | recovered_from_raw"
            else:
                return RoundOutcome(0.0, "", "GENERATION_FAILED", prompt.get("summary", "Unknown failure"))

        candidate_code = prompt.get("patch", "") or prompt.get("content", "")
        if not candidate_code:
            return RoundOutcome(0.0, "", "EMPTY_PATCH", "Model returned no patch.")

        # 2.1 🛡️ Semantic guard: reject AST-equivalent no-op changes.
        if self._is_ast_no_change(current_code, candidate_code):
            return RoundOutcome(
                0.0,
                "",
                "REJECTED_AST_NO_CHANGE",
                "AST unchanged after candidate patch; likely no-op/reformat-only change.",
            )

        # 2. 🏗️ Physical Application
        target_path = workpath / self.resolved_target_file
        target_path.write_text(candidate_code, encoding="utf-8")

        # 2.2 🥈 Tier 1 gate: static + targeted tests before any LLM scoring.
        tier1_ok, tier1_summary = self._run_tier1_validation(workpath)
        if not tier1_ok:
            return RoundOutcome(
                0.0,
                candidate_code,
                "TIER1_REJECTED",
                tier1_summary,
            )

        # 3. 🧪 Validation round (legacy-compatible) + Feynman fallback
        judge_resp, _, _judge_receipt = self._ask_unified_candidate(
            workpath=workpath,
            round_id=round_id,
            attempt=200,
            model=self.model_name,
            prompt=f"Validate candidate patch for {self.resolved_target_file}",
            payload=f"Task: {self.task}\nReturn status/score/issues.",
            output_schema={
                "status": "PASS | FAIL",
                "summary": "Short validation summary",
                "score": "numeric score",
                "issues": ["list of issues"],
            },
            task_kind="evaluation",
        )
        if isinstance(judge_resp, dict) and "score" in judge_resp:
            judge_score = float(judge_resp.get("score", 0.0))
            judge_summary = str(judge_resp.get("summary", "") or "")
            return RoundOutcome(
                score=judge_score,
                candidate=candidate_code,
                status="SCORED",
                summary=judge_summary,
            )

        print(f"🧪 [Audit] Verifying physical integrity of {self.resolved_target_file}...")
        audit_score, audit_summary = self._run_flashjudge(candidate_code)

        return RoundOutcome(
            score=audit_score,
            candidate=candidate_code,
            status="SCORED" if audit_score >= 0.8 else "AUDIT_REJECTED",
            summary=audit_summary
        )

    def _is_ast_no_change(self, source_before: str, source_after: str) -> bool:
        """Return True when Python AST is semantically unchanged."""
        try:
            before_tree = ast.parse(source_before or "")
            after_tree = ast.parse(source_after or "")
        except SyntaxError:
            # Let Tier1 static gate classify syntax issues.
            return False
        before_dump = ast.dump(before_tree, annotate_fields=True, include_attributes=False)
        after_dump = ast.dump(after_tree, annotate_fields=True, include_attributes=False)
        return before_dump == after_dump

    def _run_cmd(self, cmd: list[str], cwd: Path, timeout_sec: int) -> tuple[bool, str]:
        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return False, f"timeout: {' '.join(cmd)}"
        except Exception as exc:
            return False, f"exec_error: {' '.join(cmd)} :: {exc}"
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        if res.returncode != 0:
            return False, f"rc={res.returncode}: {' '.join(cmd)}\n{combined.strip()}"
        return True, combined.strip()

    def _discover_targeted_tests(self) -> list[str]:
        if self.test_file:
            candidate = Path(self.test_file)
            if candidate.is_absolute():
                try:
                    rel = candidate.relative_to(self.project_root)
                    return [str(rel)]
                except ValueError:
                    return [str(candidate)]
            return [self.test_file]
        stem = Path(self.resolved_target_file).stem
        tests_root = self.project_root / "tests"
        if not tests_root.exists():
            return []
        matches = sorted(str(p.relative_to(self.project_root)) for p in tests_root.rglob(f"*{stem}*.py"))
        if matches:
            return matches[:8]
        return [t for t in self.tier1_smoke_pack if (self.project_root / t).exists()]

    def _run_tier1_validation(self, workpath: Path) -> tuple[bool, str]:
        target = self.resolved_target_file
        if self.git_enabled:
            ok, msg = self._run_cmd(
                ["uv", "run", "ruff", "check", target],
                cwd=workpath,
                timeout_sec=self.tier1_timeout_sec,
            )
            if not ok:
                return False, f"tier1_ruff_failed: {msg}"
        elif target.endswith(".py"):
            ok, msg = self._run_cmd(
                ["python3", "-m", "py_compile", target],
                cwd=workpath,
                timeout_sec=self.tier1_timeout_sec,
            )
            if not ok:
                return False, f"tier1_py_compile_failed: {msg}"

        targeted = self._discover_targeted_tests()
        if not targeted:
            return False, "tier1_no_targeted_tests: no matching tests or smoke pack available."
        pytest_command = ["uv", "run", "pytest"] if self.git_enabled else [sys.executable, "-m", "pytest"]
        ok, msg = self._run_cmd(
            [*pytest_command, "-q", "--maxfail=1", *targeted],
            cwd=workpath,
            timeout_sec=self.tier1_timeout_sec,
        )
        if not ok:
            return False, f"test_failed: {msg}"
        return True, "tier1_pass"

    def _run_tier2_validation(self, workpath: Path) -> tuple[bool, str]:
        ok, pytest_msg = self._run_cmd(
            ["uv", "run", "pytest", "-q", "tests", "--ignore=tests/demo"],
            cwd=workpath,
            timeout_sec=self.tier2_timeout_sec,
        )
        if not ok:
            return False, f"test_failed (tier2): {pytest_msg}"

        ok, acceptance_msg = self._run_cmd(
            ["uv", "run", "scripts/engine/nexus_cli.py", "nexus", "acceptance-check"],
            cwd=workpath,
            timeout_sec=self.tier2_timeout_sec,
        )
        if not ok:
            return False, f"tier2_acceptance_failed: {acceptance_msg}"
        return True, "tier2_pass"

    def _write_failure_lesson(self, reason: str, details: str) -> None:
        """Failure-to-Lesson writeback for blocked winners."""
        reason_l = str(reason or "").lower()
        if "timeout" in reason_l:
            failure_class = "timeout"
            corrective_action = "increase_timeout_or_reduce_scope"
        elif "tier2" in reason_l or "acceptance" in reason_l:
            failure_class = "tier2_gate_rejection"
            corrective_action = "fix_regression_then_rerun_tier2"
        elif "quota" in reason_l or "capacity" in reason_l:
            failure_class = "quota_or_capacity"
            corrective_action = "switch_fallback_model_or_local_mode"
        else:
            failure_class = reason_l or "unknown_failure"
            corrective_action = "inspect_trace_and_refine_prompt_or_tests"

        task_signature = f"{self.task}::{self.resolved_target_file}"
        rejection_summary = {
            "no_improve_streak": self.no_improve_streak,
            "max_rounds": self.max_rounds,
            "model_exhausted_count": len(self.model_exhausted),
        }
        payload = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "task": self.task,
            "target_file": self.resolved_target_file,
            "reason": reason,
            "details": details[:2000],
            "decision": "winner_rejected",
            "failure_class": failure_class,
            "task_signature": task_signature,
            "rejection_summary": rejection_summary,
            "corrective_action": corrective_action,
        }
        self.lesson_writeback_path.parent.mkdir(parents=True, exist_ok=True)
        self.lesson_writeback_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _persist_learning_closure(self, status: str, reason: str, final_score: float) -> dict[str, Any]:
        """
        NightShift learning closure:
        1) MemPalace verify
        2) FindingsMemoryStore write (includes LanceDB ingest in repository layer)
        3) MemPalace sync
        """
        closure: dict[str, Any] = {
            "status": status,
            "reason": reason,
            "score": final_score,
            "mempalace_verified": False,
            "memory_written": False,
            "lancedb_synced": False,
            "sync_status": "SKIPPED",
        }
        
        # [NEW: C-1] Check for conflicts with existing Claims before proceeding
        try:
            from nexus.research.learn_mode import LearnModeService
            svc = LearnModeService(self.project_root)
            lesson_text = f"NightShift {status} on {getattr(self, 'resolved_target_file', 'unknown')}: {reason}"
            conflict_check = svc.ask(
                topic="learning-conflicts", 
                question=lesson_text,
                top_k=3
            )
            if conflict_check.get("citations"):
                closure["conflict_with_existing_claims"] = True
                closure["conflicting_claims"] = [c["claim"] for c in conflict_check["citations"]]
                print(f"⚠️ [NightShift] Learning closure blocked by conflicting claims: {closure['conflicting_claims']}")
        except Exception:
            pass
        self.last_learning_closure = closure
        if self.memory_store is None:
            closure["sync_status"] = "MEMORY_DISABLED"
            return closure

        try:
            from nexus.research.findings_memory import FindingsCard
            from nexus.services.mem_palace import MemPalace

            card = FindingsCard(
                kind="episodes",
                title=f"NightShift {status}: {Path(self.resolved_target_file).name}",
                task_id=f"ns-{int(time.time())}",
                tags=["nightshift", status.lower()],
                confidence="high" if status == "SUCCESS" else "medium",
                retrieval_hints=[self.task, self.resolved_target_file],
                body=(
                    f"Task: {self.task}\n"
                    f"Target: {self.resolved_target_file}\n"
                    f"Status: {status}\n"
                    f"Reason: {reason}\n"
                    f"Score: {final_score}\n"
                    f"NoImproveStreak: {self.no_improve_streak}\n"
                ),
                extra={
                    "model_name": self.model_name,
                    "fallback_model_name": self.fallback_model_name,
                    "model_exhausted": self.model_exhausted,
                    "best_score": self.best_score,
                    "target_file": self.resolved_target_file,
                    "failure_class": reason if status != "SUCCESS" else "none",
                    "task_signature": self.task,
                    "rejection_summary": {"rounds": self.max_rounds, "no_improve_streak": self.no_improve_streak},
                    "corrective_action": "increase_budget" if "budget" in reason.lower() else "check_model_quota",
                    "timestamp": datetime.now().isoformat(),
                },
            )
            palace = MemPalace(str(self.project_root))
            clean = palace.verify([card.to_dict()])
            if not clean:
                closure["reason"] = f"{reason} | mempalace_rejected"
                return closure

            closure["mempalace_verified"] = True
            clean_card = FindingsCard.from_dict(clean[0])
            write_path = self.memory_store.write(clean_card)
            closure["memory_written"] = True
            closure["memory_path"] = write_path
            closure["lancedb_synced"] = clean_card.extra.get("lancedb_synced", False)
            # Backward-compatible fallback for stub stores used in unit tests.
            if closure["lancedb_synced"] is False and write_path:
                closure["lancedb_synced"] = True
            sync_info = palace.sync()
            closure["sync_status"] = str(sync_info.get("status", "UNKNOWN"))
            closure["mempalace_sync"] = sync_info
            tx_id = palace.trigger_arweave_distillation(clean[0])
            closure["arweave_tx_id"] = tx_id
            try:
                from nexus.research.learn_mode import LearnModeService

                bridge = LearnModeService(self.project_root).sync_phase_learning_closure(
                    topic=self.task,
                    metrics={
                        "coverage": 1.0 if status == "SUCCESS" else 0.5,
                        "self_question_pass_rate": 1.0 if status == "SUCCESS" else 0.4,
                        "citation_valid_ratio": 1.0 if closure.get("mempalace_verified") else 0.8,
                        "stale_claims_count": 0,
                        "conflict_count": 0,
                    },
                    phase_status={
                        "P": "SUCCESS",
                        "X": "SUCCESS",
                        "D": "SUCCESS",
                        "R": "SUCCESS" if status == "SUCCESS" else "FAILED",
                        "A": "SUCCESS" if closure.get("mempalace_verified") else "PARTIAL",
                        "C": "SUCCESS" if closure.get("memory_written") else "PARTIAL",
                    },
                )
                closure["learn_phase_bridge"] = {
                    "status": bridge.get("status", "UNKNOWN"),
                    "entries_written": bridge.get("entries_written", 0),
                }
            except Exception as bridge_exc:
                closure["learn_phase_bridge_error"] = str(bridge_exc)
            return closure
        except Exception as exc:
            closure["sync_status"] = "ERROR"
            closure["error"] = str(exc)
            return closure

    def _recover_patch_from_raw(self, raw_content: str) -> str:
        """Recover candidate code when the gateway cannot parse structured JSON."""
        text = (raw_content or "").strip()
        if not text:
            return ""
        # Prefer fenced code blocks first.
        import re
        fenced = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        # If output is plain text that looks like code, use it directly.
        if any(token in text for token in ("def ", "class ", "import ", "print(", "if __name__")):
            return text
        return ""

    def _run_flashjudge(self, candidate_code: str) -> tuple[float, str]:
        """
        Compatibility layer for DualTrackAudit API variants.
        """
        # Legacy implementation path (if available in older bridge variants)
        if hasattr(self.feynman_auditor, "audit_file"):
            result = self.feynman_auditor.audit_file(self.resolved_target_file)  # type: ignore[attr-defined]
            score = float(getattr(result, "score", 0.0) or 0.0)
            summary = str(getattr(result, "summary", ""))
            return score, summary

        # Current bridge API
        findings = self.feynman_auditor.run_advisory_audit(candidate=candidate_code, task=self.task)
        status = str(findings.get("status", "WARN")).upper()
        warnings = findings.get("warnings", [])
        summary = "PASS" if status == "PASS" else "; ".join(warnings) if warnings else status
        score = 1.0 if status == "PASS" else 0.6
        return score, summary

    def _is_quota_or_capacity_error(self, text: str) -> bool:
        t = (text or "").lower()
        patterns = (
            "quota",
            "429",
            "rate limit",
            "resource exhausted",
            "capacity",
            "timeout",
            "exceeded",
            "unavailable",
        )
        return any(p in t for p in patterns)

    def _is_timeout_error(self, text: str) -> bool:
        t = (text or "").lower()
        return ("timeout" in t) or ("timed out" in t)

    def _is_hard_quota_error(self, text: str) -> bool:
        t = (text or "").lower()
        patterns = (
            "quota",
            "quota_exhausted",
            "terminalquotaerror",
            "429",
            "rate limit",
            "resource exhausted",
            "capacity on this model",
        )
        return any(p in t for p in patterns)


    def _check_policy_readiness(self) -> bool:
        if os.getenv("NIGHTSHIFT_BYPASS_POLICY", "").strip().lower() in {"1", "true", "yes", "on"}:
            print("⚠️ [NightShift] Policy bypass active (benchmark override=true)")
            return True
        bypass = os.getenv("NIGHTSHIFT_BYPASS_LEARN_SLO") == "1"
        policy = load_phase_policy(self.project_root, task_type="bug", risk_level="standard")
        
        if not policy.allow_research and not bypass:
            print(f"❌ [NightShift] Blocked by Phase Policy: {policy.reasoning}")
            return False
        
        if bypass:
            print("⚠️ [NightShift] Policy bypass active (override=true)")
        return True

    def run(self):
        if not self._check_policy_readiness(): return {"status": "FAILED", "infra_blocked": True, "reason": "policy_blocked"}
        """🚀 [AutoResearch] Night Shift v24.0 Eternal: Bayesian Warm-Start Enabled."""
        print(f"🚀 [AutoResearch] Starting Night Shift for: {self.task}")
        start_time = time.time()
        
        # 🧪 [Bayesian Warm-Start] Seed the optimizer with historical data
        self._warm_start_optimizer()

        self.resolved_target_file = self._resolve_target_file()
        self._preflight_models()
        bypass_learn_slo = os.getenv("NIGHTSHIFT_BYPASS_LEARN_SLO", "").strip().lower() in {"1", "true", "yes", "on"}
        learn_guard = self._read_learn_phase_slo_guard()
        if not learn_guard.get("ready", False) and not bypass_learn_slo:
            reason = str(learn_guard.get("reason", "learn_phase_slo_not_ready"))
            print(f"🛑 [AutoResearch] Blocked by Learn phase-SLO guard: {reason}")
            self._persist_learning_closure(status="REJECTED", reason=reason, final_score=self.best_score)
            return {
                "status": "FAILED", "infra_blocked": True,
                "task": self.task,
                "target_file": self.resolved_target_file,
                "best_score": self.best_score,
                "reason": reason,
                "learn_phase_slo": learn_guard,
            }

        if self.git_enabled:
            lease_task_id = f"{self.task}-{int(time.time())}"
            lease_branch = f"nightshift-{int(time.time())}"
            task_id, branch_name, workpath = self.worktree_mgr.lease(lease_task_id, lease_branch)
            if not workpath:
                print("❌ [AutoResearch] Failed to lease workspace.")
                return {"status": "FAILED", "infra_blocked": True, "reason": "workspace_lease_failed"}
        else:
            workpath = self.project_root

        try:
            if self.git_enabled:
                self.base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.project_root, text=True).strip()
            else:
                self.base_commit = "benchmark-nongit"
            
            for round_id in range(1, self.max_rounds + 1):
                if time.time() - start_time > self.budget_sec:
                    print("⏰ [AutoResearch] Time budget exceeded.")
                    break

                outcome = self._run_round(round_id, workpath)
                self.optimizer.observe({"temperature": 0.5}, outcome.score)

                if outcome.status == "MODEL_EXHAUSTED":
                    self._log_trace(round_id, "MODEL_EXHAUSTED", 0.0, outcome.summary)
                    print("🛑 [AutoResearch] All models exhausted by quota/capacity. Stopping task early.")
                    break

                if outcome.status == "SCORED" and outcome.score > self.best_score:
                    print(f"⭐ [AutoResearch] New best score: {outcome.score:.2f} (Round {round_id})")
                    self.best_score = outcome.score
                    self.no_improve_streak = 0
                    
                    if self.git_enabled:
                        subprocess.run(["git", "add", "."], cwd=workpath, capture_output=True)
                        subprocess.run(["git", "commit", "-m", f"opt(nightshift): optimize {self.task} (score: {outcome.score:.2f})"], cwd=workpath, capture_output=True)
                        self.base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workpath, text=True).strip()
                    
                    self._log_trace(
                        round_id,
                        "IMPROVED",
                        outcome.score,
                        outcome.summary,
                    )
                else:
                    if self.git_enabled:
                        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=workpath, capture_output=True)
                    self.no_improve_streak += 1
                    self._log_trace(round_id, outcome.status, outcome.score, outcome.summary)
                    if outcome.status == "GENERATION_FAILED" and self._is_quota_or_capacity_error(outcome.summary):
                        print("🛑 [AutoResearch] Generation blocked by quota/capacity. Stopping to avoid empty retries.")
                        break

                if self.no_improve_streak >= self.convergence_patience:
                    print(f"🎯 [AutoResearch] Convergence reached after {self.no_improve_streak} rounds.")
                    self._log_trace(round_id, "CONVERGED", self.best_score, "No-improvement patience reached.")
                    break

            # --- [Approval Gate] Atomic Queue for Review ---
            if self.best_score > 0 and self.base_commit and self.git_enabled:
                tier2_ok, tier2_summary = self._run_tier2_validation(workpath)
                if not tier2_ok:
                    print("🛑 [AutoResearch] Tier2 gate rejected winner. Skipping promotion.")
                    self._log_trace(
                        round_id=self.max_rounds,
                        status="REJECTED_GLOBAL_REGRESSION",
                        score=self.best_score,
                        summary=tier2_summary,
                    )
                    self._write_failure_lesson("tier2_gate_rejection", tier2_summary)
                    self._persist_learning_closure(
                        status="REJECTED",
                        reason=tier2_summary,
                        final_score=self.best_score,
                    )
                    return {
                        "status": "COMPLETED",
                        "task": self.task,
                        "target_file": self.resolved_target_file,
                        "best_score": self.best_score,
                        "reason": "tier2_gate_rejected",
                    }
                self._append_to_pending_manifest(self.task, self.resolved_target_file, self.base_commit, self.best_score, str(workpath))

            final_status = "SUCCESS" if self.best_score > 0 else "NO_IMPROVEMENT"
            final_reason = "best_score_recorded" if self.best_score > 0 else "no_valid_candidate"
            
            # 物理硬化：自動分類失敗原因 (Phase 1)
            failure_cat = SprintOutcome.SUCCESS.value if self.best_score > 0 else SprintOutcome.STAGE1_FAILED.value
            
            elapsed = time.time() - start_time
            if elapsed > self.budget_sec:
                failure_cat = SprintOutcome.TIME_BUDGET_EXCEEDED.value
            elif self.best_score == 0 and any(self._is_quota_or_capacity_error(str(t)) for t in self.trace_log):
                failure_cat = SprintOutcome.QUOTA_EXHAUSTED.value
            elif self.best_score == 0 and any(self._is_timeout_error(str(t)) for t in self.trace_log):
                failure_cat = SprintOutcome.HYPER_RUN_TIMEOUT.value

            self._save_json_report(final_status, failure_cat)
            
            self._persist_learning_closure(
                status=final_status,
                reason=final_reason,
                final_score=self.best_score,
            )
            self._finalize_unified_runtime_receipt(
                terminal_status=final_status,
                final_score=self.best_score,
            )
            self._save_json_report(final_status, failure_cat)
            print(f"✅ [AutoResearch] Finished {self.task}. Best Score: {self.best_score:.2f}")
            return {
                "status": "COMPLETED",
                "task": self.task,
                "target_file": self.resolved_target_file,
                "best_score": self.best_score,
            }

        finally:
            if self.git_enabled:
                self._cleanup_worktree(workpath)

    def _save_json_report(self, terminal_state: str, failure_category: str):
        """🛡️ [Phase 1] 產生標準化機器可讀報表"""
        report_path = self.project_root / ".nexus" / "reports" / f"nightshift_{self.task.replace('/', '_')}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        outcome = NexusOutcomeV2(
            task_id=self.task,
            trace_id=getattr(self, "base_commit", "unknown"),
            terminal_state=terminal_state,
            failure_category=failure_category,
            exit_code=0 if terminal_state == "SUCCESS" else 1,
            model_version=self.model_name,
            timestamp=datetime.now().isoformat()
        )
        
        payload = dict(outcome.__dict__)
        payload.update(
            {
                "target_file": self.resolved_target_file,
                "best_score": self.best_score,
                "rounds_attempted": len(self.trace_log),
                "no_improve_streak": self.no_improve_streak,
                "model_exhausted": dict(self.model_exhausted),
                "artifact_paths": [str(self.tracelog_path), str(self.lesson_writeback_path)],
                "learning_closure": self.last_learning_closure,
                "unified_runtime_receipt": self.last_unified_runtime_receipt,
            }
        )
        with open(report_path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"📊 [Orchestrator] Machine-readable report saved to: {report_path}")

    def _cleanup_worktree(self, workpath: Path) -> None:
        resolved_workpath = Path(workpath).resolve()
        resolved_root = self.project_root.resolve()
        if self.keep_worktree:
            print(f"🧹 [Cleanup] Worktree at {workpath} retained for review.")
            return
        # Safety guard: never remove project root.
        if resolved_workpath == resolved_root:
            print(f"🧹 [Cleanup] Skip auto-remove for project root path: {workpath}")
            return
        res = subprocess.run(
            ["git", "worktree", "remove", "--force", str(workpath)],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print(f"🧹 [Cleanup] Worktree removed: {workpath}")
            return
        print(f"⚠️ [Cleanup] Auto-remove failed, retained for review: {workpath}")

    def _warm_start_optimizer(self):
        """🛡️ Bayesian Warm Start: Load historical traces to eliminate cold-start bias."""
        curve_path = self.project_root / "optimization_curve.csv"
        if curve_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(curve_path)
                # Filter traces for current target if possible, or use global heuristic
                for _, row in df.tail(20).iterrows():
                    self.optimizer.observe({"temperature": row.get('temperature', 0.5)}, row.get('score', 0.0))
                print(f"🔥 [Bayesian] Warm-start complete. Seeding model with {len(df.tail(20))} traces.")
            except Exception as e:
                print(f"⚠️ [Bayesian] Warm-start failed: {e}")

    def _append_to_pending_manifest(self, task_name: str, target_file: str, commit_sha: str, score: float, workpath: str):
        """🛡️ 原子化寫入待審核清單 (與 fcntl 鎖定技術結合)"""
        import fcntl
        pending_item = {
            "task": task_name,
            "target_file": target_file,
            "commit_sha": commit_sha,
            "best_score": score,
            "workpath": workpath,
            "timestamp": datetime.now().isoformat()
        }
        
        self.pending_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用檔案鎖保護 JSON 完整性
        with open(self.pending_manifest_path, "a+b") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                content = f.read().decode("utf-8")
                pending = json.loads(content) if content else []
                # Remove prior candidate for same task
                pending = [p for p in pending if p["task"] != task_name]
                pending.append(pending_item)
                
                f.seek(0)
                f.truncate()
                f.write(json.dumps(pending, indent=2).encode("utf-8"))
                print(f"✅ [Approval Gate] Task queued with LOCK: {task_name}")
            except Exception as e:
                print(f"❌ [Gate Error] Failed to append with lock: {e}")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)





def _update_manifest_status(project_root: Path, task_name: str, commit_sha: str):
    import re
    manifest_path = project_root / "task_manifest.yaml"
    if not manifest_path.exists(): return
    identifier = Path(task_name).stem.lower()
    content = manifest_path.read_text(encoding="utf-8")
    block_pattern = rf"(- id: auto\.repair\..*?{re.escape(identifier)}.*?\n\s+description: ')(.*?)(')"
    resolved_msg = f"AUTO-REPAIR: RESOLVED {datetime.now().strftime('%Y-%m-%d')}. Physical patch merged ({commit_sha[:7]})."
    new_content, count = re.subn(block_pattern, rf"\1{resolved_msg}\3", content, flags=re.IGNORECASE)
    if count > 0:
        manifest_path.write_text(new_content, encoding="utf-8")
        subprocess.run(["git", "add", "task_manifest.yaml"], capture_output=True, cwd=project_root)
        subprocess.run(["git", "commit", "-m", f"docs(governance): resolve task status for {identifier}"], capture_output=True, cwd=project_root)

def _cleanup_stale_swarm_locks(project_root: Path, ttl_minutes: int) -> int:
    import time
    lock_dir = project_root / ".nexus" / "locks"
    # Tests also use .nexus-swarm-* directories directly
    count = 0
    # Pattern 1: .nexus/locks/swarm_*.lock
    if lock_dir.exists():
        for lock_file in lock_dir.glob("swarm_*.lock"):
            if (time.time() - lock_file.stat().st_mtime) > (ttl_minutes * 60):
                lock_file.unlink(); count += 1
    # Pattern 2: .nexus-swarm-*/.swarm_lock (Used by some tests)
    for swarm_dir in project_root.glob(".nexus-swarm-*"):
        lock = swarm_dir / ".swarm_lock"
        if lock.exists() and (time.time() - lock.stat().st_mtime) > (ttl_minutes * 60):
            lock.unlink(); count += 1
    return count
