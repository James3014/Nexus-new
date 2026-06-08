import logging
from typing import Dict, Any, Optional
class EscalationRouter:
    def __init__(self, threshold: int = 1): self.threshold = threshold
    def determine_lane(self, task_id: str, rejection: Any, history: list) -> str:
        if not rejection: return "standard_7b"
        if rejection.rejection_class == "semantic_reasoning_ceiling": return "14b_plan_lane"
        if len(history) >= self.threshold: return "governed_swarm_lane"
        return "standard_7b_retry"
