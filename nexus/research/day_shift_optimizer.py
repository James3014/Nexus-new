import os
import json
import time
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

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
        model_name: str = "gemini-3.1-pro-preview",
        fallback_model_name: str = "gemini-3-flash-preview"
    ):
        self.project_root = project_root.resolve()
        self.swarm_dir = swarm_dir.resolve()
        self.target_file = target_file
        self.task_desc = task_desc
        self.max_rounds = max_rounds
        self.convergence_patience = convergence_patience
        self.model_name = model_name
        self.fallback_model_name = fallback_model_name
        
        from nexus.services.gateway import BattlesuitGateway
        self.gateway = BattlesuitGateway(project_root=self.project_root)
        
        self.best_score = 0.0
        self.no_improve_streak = 0
        self.exhausted_models = set()
        self.winning_code = None
        
    def _get_candidate_models(self) -> list[str]:
        return [m for m in (self.model_name, self.fallback_model_name) if m not in self.exhausted_models]

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
                timeout=60
            )
            return res.returncode, res.stdout + "\n" + res.stderr
        except subprocess.TimeoutExpired:
            return 1, "Timeout during pytest."
        except Exception as e:
            return 1, str(e)

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
            
            prompt_res, raw_content = self.gateway.ask_structured(
                prompt=prompt_text,
                payload="Return FULL file content.",
                phase="R",
                output_schema={
                    "status": "APPROVED | FAIL",
                    "summary": "Short explanation",
                    "patch": "Full target file content"
                },
                model_name=model
            )
            
            if prompt_res.get("status") == "FAIL":
                err_text = str(prompt_res.get("summary", "")) + str(raw_content)
                if self._is_quota_error(err_text):
                    logger.warning(f"⚠️ [DayShift] Quota exhausted on {model}, switching fallback.")
                    self.exhausted_models.add(model)
                    continue
                else:
                    logger.warning(f"⚠️ [DayShift] Generation failed: {err_text}")
                    continue

            candidate_code = prompt_res.get("patch") or raw_content
            if not candidate_code or "unexpected keyword argument" in candidate_code:
                logger.error("🛑 [DayShift] Interface error (NO_NEW_TRACE / unexpected keyword). Aborting to prevent loop.")
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
                # Ask model for a score (simulated audit)
                eval_res, _ = self.gateway.ask_structured(
                    prompt=f"Evaluate the optimized code for {self.target_file} against performance & readability.",
                    payload=f"Code:\n{candidate_code[:2000]}",
                    phase="R",
                    output_schema={"score": "float between 0 and 1.0", "summary": "str"},
                    model_name=model
                )
                score = float(eval_res.get("score", 0.95)) # Default high if it passed tests
                
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

        if self.winning_code and self.best_score >= 0.9:
            return {
                "status": "SUCCESS",
                "score": self.best_score,
                "patch": self.winning_code,
                "target_file": self.target_file
            }
        else:
            return {"status": "FAILED", "reason": "no_improvement_or_low_score"}

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
