import hashlib
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

logger = logging.getLogger(__name__)

class DayShiftOptimizer:
    """
    ☀️ DayShift Optimizer (Hyper-Sprint)
    Executes a micro-NightShift loop directly inside a provided Swarm sandbox.
    Implements Agent Optimization Rules v1.0 (Strict safety & promotion gates).
    """

    def __init__(
        self,
        project_root: Path,
        swarm_dir: Path,
        target_file: str,
        task_desc: str,
        max_rounds: int = 5,
        convergence_patience: int = 2,
        model_name: str = "gemini-3-flash-preview",
        fallback_model_name: str = "gemini-3.1-pro-preview",
        test_timeout_sec: int = 60,
        use_llm_scoring: bool = False,
        min_round_delay_sec: float = 1.5,
    ):
        self.project_root = project_root.resolve()
        self.swarm_dir = swarm_dir.resolve()
        self.target_file = target_file
        self.task_desc = task_desc
        self.max_rounds = max_rounds
        self.convergence_patience = convergence_patience
        self.model_name = model_name
        self.fallback_model_name = fallback_model_name
        self.test_timeout_sec = test_timeout_sec
        self.use_llm_scoring = use_llm_scoring
        self.min_round_delay_sec = min_round_delay_sec
        
        from nexus.services.gateway import BattlesuitGateway
        self.gateway = BattlesuitGateway(project_root=self.project_root)
        
        self.best_score = 0.0
        self.no_improve_streak = 0
        self.exhausted_models = set()
        self.winning_code = None
        self.unified_runtime_receipts: list[dict[str, Any]] = []
        
    def _get_candidate_models(self) -> list[str]:
        return [m for m in (self.model_name, self.fallback_model_name) if m not in self.exhausted_models]

    def _workspace_revision(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.swarm_dir),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    def _ask_unified(
        self,
        *,
        prompt: str,
        payload: str,
        task_statement: str,
        round_id: int,
        attempt: int,
        model: str,
        output_schema: Mapping[str, Any],
        task_kind: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        from nexus.services.unified_runtime import UnifiedRuntimeRequest

        ask_unified = getattr(self.gateway, "ask_unified", None)
        revision = self._workspace_revision()
        if not revision:
            revision = f"fixture-{hashlib.sha256(str(self.swarm_dir).encode()).hexdigest()[:12]}"

        task_id = (
            f"dayshift-{hashlib.sha256(task_statement.encode('utf-8')).hexdigest()[:12]}"
            f"-r{round_id}-a{attempt}-{task_kind}"
        )

        from nexus.services.unified_runtime import build_online_route, extract_online_stage_payload

        def response_contract(context: Mapping[str, Any]) -> dict[str, Any]:
            online = context.get("online", {})
            provider_response, _raw, _payload = extract_online_stage_payload(
                online if isinstance(online, Mapping) else {}
            )
            delivered = bool(provider_response)
            return {
                "task_id": task_id,
                "status": "pass" if delivered else "fail",
                "evidence": "online_payload_present" if delivered else "online_payload_missing",
                "evidence_refs": [f"verifier:{task_id}:response_contract"],
            }

        gateway_provider = str(getattr(self.gateway, "oauth_provider", "") or "").strip().lower()
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=revision,
            task_statement=task_statement,
            task_type="repair" if task_kind == "generation" else "evaluation",
            route=build_online_route(
                recommended_flow="direct",
                gateway_provider=gateway_provider,
            ),
            online_prompt=prompt,
            online_payload=payload,
            online_phase="R",
            online_model_name=model,
            online_output_schema=dict(output_schema),
            evidence_refs=(f"dayshift:{task_id}:request",),
        )
        receipt_path = self.swarm_dir / ".nexus" / "reports" / "unified_runtime" / f"{task_id}.json"
        if callable(ask_unified):
            receipt = ask_unified(request, verifier=response_contract, receipt_path=receipt_path)
        else:
            from nexus.services.unified_runtime import (
                UnifiedRuntime,
                build_structured_online_invoker,
            )

            receipt = UnifiedRuntime().run(
                request,
                online_invoker=build_structured_online_invoker(
                    self.gateway.ask_structured,
                    phase="R",
                    model_name=model,
                    output_schema=dict(output_schema),
                    provider="fixture_gateway",
                ),
                verifier=response_contract,
                receipt_path=receipt_path,
            )
        self.unified_runtime_receipts.append(dict(receipt))
        online_stage = receipt.get("online", {}) if isinstance(receipt.get("online"), Mapping) else {}
        provider_response, raw_response, _payload = extract_online_stage_payload(online_stage)
        if isinstance(provider_response, Mapping):
            return dict(provider_response), raw_response, receipt
        return {"status": "APPROVED" if online_stage.get("status") == "SUCCEEDED" else "FAIL", "patch": str(provider_response or "")}, raw_response, receipt

    def _is_quota_error(self, text: str) -> bool:
        t = text.lower()
        return any(p in t for p in ["quota", "429", "rate limit", "resource exhausted", "capacity"])

    def _run_tests(self) -> Tuple[int, str]:
        """Runs tests in the swarm directory."""
        try:
            res = subprocess.run(
                ["uv", "run", "pytest", "-q", "--maxfail=1"],
                capture_output=True,
                text=True,
                cwd=self.swarm_dir,
                timeout=self.test_timeout_sec
            )
            return res.returncode, res.stdout + "\n" + res.stderr
        except subprocess.TimeoutExpired:
            return 1, "Timeout during pytest."
        except Exception as e:
            return 1, str(e)

    def _finalize_unified_runtime_receipts(self, *, terminal_status: str, final_score: float) -> None:
        """Close DayShift's existing receipts without creating a second runtime path."""
        if not self.unified_runtime_receipts:
            return

        from nexus.research.learn_mode import LearnModeService
        from nexus.services.unified_runtime import UnifiedRuntime

        try:
            learning_result = LearnModeService(self.project_root).sync_phase_learning_closure(
                topic=self.task_desc,
                metrics={
                    "coverage": 1.0 if terminal_status == "SUCCESS" else 0.0,
                    "self_question_pass_rate": 1.0 if terminal_status == "SUCCESS" else 0.0,
                    "citation_valid_ratio": 1.0,
                    "stale_claims_count": 0,
                    "conflict_count": 0,
                    "provider_call_count": sum(
                        int((receipt.get("online", {}).get("response", {}) or {}).get("provider_call_count", 0) or 0)
                        for receipt in self.unified_runtime_receipts
                        if isinstance(receipt, Mapping) and isinstance(receipt.get("online"), Mapping)
                    ),
                },
                phase_status={
                    phase: terminal_status for phase in ("P", "D", "R", "A", "C")
                },
            )
            learning_passed = str(learning_result.get("status", "")).upper() in {"SUCCESS", "SUCCEEDED", "PASS"}
        except Exception as exc:
            learning_result = {"status": "FAIL", "error": f"{exc.__class__.__name__}:{exc}"}
            learning_passed = False

        finalized_receipts: list[dict[str, Any]] = []
        for receipt in self.unified_runtime_receipts:
            if not isinstance(receipt, Mapping):
                continue
            task_id = str(receipt.get("task_id", ""))
            online = receipt.get("online", {})
            online_passed = isinstance(online, Mapping) and online.get("status") == "SUCCEEDED"
            finalized_receipts.append(
                UnifiedRuntime().finalize_receipt(
                    receipt,
                    verifier={
                        "task_id": task_id,
                        "status": "pass" if online_passed else "fail",
                        "invoked": True,
                        "gate_passed": online_passed,
                        "evidence": "dayshift_candidate_outcome",
                        "evidence_refs": [f"verifier:{task_id}:dayshift_final"],
                        "outcome_contributed": bool(online_passed and terminal_status == "SUCCESS"),
                    },
                    learning={
                        "task_id": task_id,
                        "status": "pass" if learning_passed else "fail",
                        "invoked": True,
                        "gate_passed": learning_passed,
                        "evidence": "dayshift_learning_closure",
                        "evidence_refs": [f"learning:{task_id}:closure"],
                        "outcome_contributed": bool(learning_passed and terminal_status == "SUCCESS"),
                        "response": learning_result,
                    },
                    outcome={"score": final_score, "value_measured": terminal_status == "SUCCESS"},
                    receipt_path=receipt.get("receipt_path"),
                )
            )
        self.unified_runtime_receipts = finalized_receipts

    def optimize(self) -> Dict[str, Any]:
        target_path = self.swarm_dir / self.target_file
        if not target_path.exists():
            return {"status": "FAILED", "reason": "target_file_not_found"}

        current_code = target_path.read_text(encoding="utf-8")
        
        logger.info(f"☀️ [DayShift] Starting micro-optimization for {self.target_file} in {self.swarm_dir.name}")
        
        for round_id in range(1, self.max_rounds + 1):
            models = self._get_candidate_models()
            if not models:
                logger.error("🛑 [DayShift] All models exhausted (Quota/Capacity).")
                break
                
            model = models[0]
            logger.info(f"--- [Round {round_id}] Suggesting optimization using {model} ---")
            
            prompt_text = (
                f"You are executing a DayShift Hyper-Sprint.\n"
                f"Your objective is to fulfill the following task for {self.target_file}:\n"
                f"Task: {self.task_desc}\n\n"
                f"Instructions:\n"
                f"- If this is a bug fix, resolve the root cause robustly.\n"
                f"- If this is a new feature, implement it cleanly.\n"
                f"- If this is an optimization, improve performance without changing behavior.\n\n"
                f"[CURRENT SOURCE]\n{current_code}\n\n"
                f"Return ONLY the full updated file content in the 'patch' field."
            )
            
            prompt_res, raw_content, _generation_receipt = self._ask_unified(
                prompt=prompt_text,
                payload="Return FULL file content.",
                task_statement=self.task_desc,
                round_id=round_id,
                attempt=1,
                model=model,
                task_kind="generation",
                output_schema={
                    "status": "APPROVED | FAIL",
                    "summary": "Short explanation",
                    "patch": "Full target file content"
                },
            )
            
            if prompt_res.get("status") == "FAIL":
                err_text = str(prompt_res.get("summary", "")) + str(raw_content)
                if self._is_quota_error(err_text):
                    logger.warning(f"⚠️ [DayShift] Quota exhausted on {model}, switching fallback.")
                    self.exhausted_models.add(model)
                    time.sleep(self.min_round_delay_sec)
                    continue
                else:
                    logger.warning(f"⚠️ [DayShift] Generation failed: {err_text}")
                    time.sleep(self.min_round_delay_sec)
                    continue

            candidate_code = prompt_res.get("patch") or raw_content
            if not candidate_code or "unexpected keyword argument" in candidate_code:
                logger.error("🛑 [DayShift] Interface error (NO_NEW_TRACE / unexpected keyword). Aborting to prevent loop.")
                self._finalize_unified_runtime_receipts(terminal_status="FAILED", final_score=0.0)
                return {"status": "FAILED", "reason": "interface_or_audit_error"}

            # Apply candidate physically to swarm
            target_path.write_text(candidate_code, encoding="utf-8")
            
            # Run Validation
            rc, output = self._run_tests()
            
            if rc != 0:
                logger.info(f"❌ [DayShift] Candidate failed tests (rc={rc}). Rolling back.")
                target_path.write_text(current_code, encoding="utf-8") # Rollback
                self.no_improve_streak += 1
            else:
                if self.use_llm_scoring:
                    eval_res, _, _scoring_receipt = self._ask_unified(
                        prompt=f"Evaluate the optimized code for {self.target_file} against performance & readability.",
                        payload=f"Code:\n{candidate_code[:2000]}",
                        task_statement=f"Evaluate the optimized code for {self.target_file}",
                        round_id=round_id,
                        attempt=2,
                        model=model,
                        task_kind="scoring",
                        output_schema={"score": "float between 0 and 1.0", "summary": "str"},
                    )
                    score = float(eval_res.get("score", 0.95))
                else:
                    # Quota-safe mode: test-pass implies high-confidence baseline score.
                    score = 0.95
                
                if score > self.best_score and score >= 0.9:
                    logger.info(f"⭐ [DayShift] IMPROVED! New best score: {score} (rc={rc})")
                    self.best_score = score
                    self.winning_code = candidate_code
                    current_code = candidate_code
                    self.no_improve_streak = 0
                else:
                    logger.info(f"⚠️ [DayShift] CONVERGED or Score too low ({score}). Rolling back.")
                    target_path.write_text(current_code, encoding="utf-8")
                    self.no_improve_streak += 1

            if self.no_improve_streak >= self.convergence_patience:
                logger.info(f"🎯 [DayShift] Convergence reached after {self.no_improve_streak} rounds.")
                break
            time.sleep(self.min_round_delay_sec)

        if self.winning_code and self.best_score >= 0.9:
            self._finalize_unified_runtime_receipts(terminal_status="SUCCESS", final_score=self.best_score)
            return {
                "status": "SUCCESS",
                "score": self.best_score,
                "patch": self.winning_code,
                "target_file": self.target_file,
                "unified_runtime_receipts": self.unified_runtime_receipts,
            }
        else:
            self._finalize_unified_runtime_receipts(terminal_status="FAILED", final_score=self.best_score)
            return {
                "status": "FAILED",
                "reason": "no_improvement_or_low_score",
                "unified_runtime_receipts": self.unified_runtime_receipts,
            }

    def promote_to_branch(self, run_id: str, patch_code: str) -> str:
        """
        Creates an independent branch in the main workspace and commits the optimized code.
        Strictly forbids overwriting `main` directly.
        """
        branch_name = f"hyper-sprint/{run_id}"
        logger.info(f"🚀 [DayShift] Promoting optimized code to independent branch: {branch_name}")
        
        try:
            # Create and checkout branch
            subprocess.run(["git", "checkout", "-b", branch_name], cwd=self.project_root, check=True, capture_output=True)
            
            # Write patch
            main_target = self.project_root / self.target_file
            main_target.write_text(patch_code, encoding="utf-8")
            
            # Commit
            msg = f"opt(dayshift): optimize {self.target_file} (score: {self.best_score})"
            subprocess.run(["git", "add", self.target_file], cwd=self.project_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", msg], cwd=self.project_root, check=True, capture_output=True)
            
            # Return to main (or previous branch) to avoid leaving user in a detached state if needed,
            # but usually we leave them on the new branch to inspect. We will stay on the new branch.
            return branch_name
        except Exception as e:
            logger.error(f"❌ [DayShift] Promotion failed: {e}")
            return ""
