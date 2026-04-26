import logging
from dataclasses import dataclass

logger = logging.getLogger("nexus.core.onebit")

@dataclass
class Decision:
    verdict: bool
    confidence: float
    reasoning: str

class OneBitGate:
    """[P0] 1-bit Core: The lowest atomic decision unit for Nexus."""
    def __init__(self, base_threshold: float = 0.5):
        self.base_threshold = base_threshold

    def evaluate(self, belief_score: float, context: str = "", task_complexity: float = 1.0) -> Decision:
        """Evaluate the final condition with context-adaptive thresholding."""
        # 適應性門檻：依據任務複雜度調整，最高上限可達 0.95
        dynamic_threshold = min(0.95, self.base_threshold * max(1.0, task_complexity))
        
        verdict = belief_score > dynamic_threshold
        reasoning = f"Belief score {belief_score:.2f} is {'above' if verdict else 'below or equal to'} adaptive threshold {dynamic_threshold:.2f} (base: {self.base_threshold:.2f}, complexity: {task_complexity:.1f})."
        if context:
            reasoning += f" Context: {context}"
        return Decision(verdict=verdict, confidence=belief_score, reasoning=reasoning)
