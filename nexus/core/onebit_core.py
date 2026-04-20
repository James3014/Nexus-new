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
    def __init__(self, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold

    def evaluate(self, belief_score: float, context: str = "") -> Decision:
        """Evaluate the final condition and return a hard YES/NO decision."""
        verdict = belief_score > self.confidence_threshold
        reasoning = f"Belief score {belief_score:.2f} is {'above' if verdict else 'below or equal to'} threshold {self.confidence_threshold:.2f}."
        if context:
            reasoning += f" Context: {context}"
        return Decision(verdict=verdict, confidence=belief_score, reasoning=reasoning)
