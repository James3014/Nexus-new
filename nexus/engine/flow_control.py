from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional
import re

from nexus.engine.capability_contracts import FlowState, StateTransitionReceipt


class InteractionMode(str, Enum):
    DIRECT = "direct"
    CLARIFY_FIRST = "clarify_first"
    OUTLINE_FIRST = "outline_first"


@dataclass(frozen=True)
class IntentIntakeReceipt:
    schema_version: str = "intent_intake_receipt.v1"
    task_id: str = ""
    interaction_mode: InteractionMode = InteractionMode.DIRECT
    requires_user_confirmation: bool = False
    can_emit_final_plan: bool = True
    can_modify_files: bool = True
    confirmation_checkpoint: str = "none"
    initial_state: FlowState = FlowState.PLAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "interaction_mode": self.interaction_mode.value,
            "requires_user_confirmation": self.requires_user_confirmation,
            "can_emit_final_plan": self.can_emit_final_plan,
            "can_modify_files": self.can_modify_files,
            "confirmation_checkpoint": self.confirmation_checkpoint,
            "initial_state": self.initial_state.value,
        }


class IntentIntakeClassifier:
    """Stage 1: 意圖入口分類器，判定任務模式與初始狀態"""

    DESIGN_KEYWORDS = [r"design", r"architect", r"blueprint", r"設計", r"架構"]
    COMPLEX_KEYWORDS = [r"refactor", r"migration", r"heavy", r"重構", r"遷移"]

    def classify(self, task_desc: str, risk_score: int = 0) -> IntentIntakeReceipt:
        # 預設模式
        mode = InteractionMode.DIRECT
        initial_state = FlowState.PLAN
        requires_confirm = False
        checkpoint = "none"
        
        desc_lower = task_desc.lower()
        
        # 1. 判定是否需要先設計 (CLARIFY_FIRST)
        if any(re.search(p, desc_lower) for p in self.DESIGN_KEYWORDS) or risk_score >= 80:
            mode = InteractionMode.CLARIFY_FIRST
            initial_state = FlowState.CLARIFY
            requires_confirm = True
            checkpoint = "design"
        
        # 2. 判定是否需要先出大綱 (OUTLINE_FIRST)
        elif any(re.search(p, desc_lower) for p in self.COMPLEX_KEYWORDS) or risk_score >= 50:
            mode = InteractionMode.OUTLINE_FIRST
            initial_state = FlowState.OUTLINE
            requires_confirm = True
            checkpoint = "outline"
            
        return IntentIntakeReceipt(
            interaction_mode=mode,
            initial_state=initial_state,
            requires_user_confirmation=requires_confirm,
            confirmation_checkpoint=checkpoint,
            can_emit_final_plan=(mode == InteractionMode.DIRECT),
            can_modify_files=(mode == InteractionMode.DIRECT)
        )


class FlowStateMachine:
    """Stage 2: Rust 驅動的狀態機，強制執行合法流程轉移"""

    def __init__(self):
        from nexus.engine.governance_bridge import GovernanceBridge
        self.bridge = GovernanceBridge()

    def validate_transition(self, current: FlowState, next_state: FlowState) -> bool:
        # 將 Python 枚舉轉為字串傳遞給 Rust
        return self.bridge.can_transition(current.value, next_state.value)
