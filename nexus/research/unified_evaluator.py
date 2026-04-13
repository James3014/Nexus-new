import logging
import time
from typing import Dict, List, Any, Callable, Optional
import random

logger = logging.getLogger(__name__)

class UnifiedEvaluator:
    """
    🧬 AutoResearch 統一評估器 (v1.2 Zero-Overshoot)
    強制執行嚴格預算與多框架固定 Seeds。
    """
    FIXED_SEEDS = [42, 1337, 2026]

    def __init__(self, budget_limit: float = 100.0, min_score_threshold: float = 0.5):
        self.budget_limit = budget_limit
        self.min_score_threshold = min_score_threshold
        self.scoreboard: Dict[str, Dict[str, Any]] = {}

    def _set_deterministic_seeds(self, seed: int):
        random.seed(seed)
        try:
            import numpy as np
            np.random.seed(seed)
        except ImportError: pass
        try:
            import torch
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
        except ImportError: pass

    def evaluate(self, candidate_id: str, test_fn: Callable[[int], Dict[str, Any]], estimated_cost_per_round: float = 1.0) -> Dict[str, Any]:
        """
        執行評估。落實 No-Overshoot 契約：
        若執行下一輪可能導致 total_cost > budget_limit，則立即終止。
        """
        results = []
        total_score = 0.0
        total_cost = 0.0
        start_time = time.time()

        for seed in self.FIXED_SEEDS:
            # 零超支契約：預判下一輪成本
            if total_cost + estimated_cost_per_round > self.budget_limit:
                logger.warning("⚠️ [Evaluator] Budget limit guard activated for %s (Cost: %.2f)", candidate_id, total_cost)
                break
            
            self._set_deterministic_seeds(seed)
            try:
                res = test_fn(seed)
                score = res.get("score", 0.0)
                cost = res.get("cost", estimated_cost_per_round)
                
                # 執行後二次核驗，確保單輪不超巨大
                if total_cost + cost > self.budget_limit:
                    logger.error("🛑 [Evaluator] Single round cost spike! Stopping to prevent overshoot.")
                    break

                results.append({"seed": seed, "score": score, "cost": cost})
                total_score += score
                total_cost += cost
            except Exception as e:
                logger.error("❌ [Evaluator] Seed %d failed: %s", seed, e)
                results.append({"seed": seed, "error": str(e)})

        avg_score = total_score / len(results) if results else 0.0
        report = {
            "candidate_id": candidate_id,
            "average_score": avg_score,
            "total_cost": total_cost,
            "passed_gate": avg_score >= self.min_score_threshold,
            "seed_details": results
        }
        self.scoreboard[candidate_id] = report
        return report

    def get_best_candidate(self) -> Optional[str]:
        if not self.scoreboard: return None
        return max(self.scoreboard, key=lambda k: self.scoreboard[k]["average_score"])
