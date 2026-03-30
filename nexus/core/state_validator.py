from typing import Any
import logging

logger = logging.getLogger(__name__)

class StateValidator:
    """
    🛡️ Nexus State Validator
    負責 Soul Protocols 的驗證，包括禁用轉移矩陣。
    """
    
    @staticmethod
    def validate_protocols(state: Any) -> None:
        """
        🚫 Nexus Soul Protocols: Forbidden Transitions & Guardrails
        """
        # 1. Batch Mode 預算守門員
        if state.batch_id and state.current_phase == "P":
            if state.config.budget_token <= 0:
                raise ValueError(f"Soul Protocol Violation: Batch {state.batch_id} at Phase P must have budget_token > 0")
        
        # 2. 狀態轉移禁地 (Forbidden Transitions Matrix)
        if state.steps_history:
            last_phase = state.steps_history[-1].phase
            # 案例：禁止從 P 直接跳到 R (必須經過 D)
            forbidden = {
                "P": ["R", "A", "C"],
                "D": ["A", "C"],
                "X": ["A", "C"]
            }
            if state.current_phase in forbidden.get(last_phase, []):
                raise ValueError(
                    f"Forbidden Transition: Illegal shortcut detected from {last_phase} to {state.current_phase}. "
                    "Contract v1.5.2 enforces P->D->(X)->R pipeline."
                )
