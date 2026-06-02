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
    """Stage 1: 程式化狀態機，強制執行合法流程轉移"""

    VALID_TRANSITIONS = {
        FlowState.INTAKE: [FlowState.CLARIFY, FlowState.OUTLINE, FlowState.PLAN],
        FlowState.CLARIFY: [FlowState.OUTLINE, FlowState.RESEARCH, FlowState.ESCALATE],
        FlowState.OUTLINE: [FlowState.PLAN, FlowState.RESEARCH, FlowState.REPLAN],
        FlowState.RESEARCH: [FlowState.DESIGN, FlowState.OUTLINE, FlowState.PLAN], # Note: DESIGN will be added in Stage 2
        FlowState.PLAN: [FlowState.EXECUTE, FlowState.REPLAN, FlowState.HUMAN_REVIEW],
        FlowState.EXECUTE: [FlowState.VERIFY, FlowState.ESCALATE],
        FlowState.VERIFY: [FlowState.CLOSE, FlowState.REPLAN],
        FlowState.REPLAN: [FlowState.PLAN, FlowState.OUTLINE],
        FlowState.HUMAN_REVIEW: [FlowState.PLAN, FlowState.CLOSE, FlowState.BLOCKED_POLICY],
    }

    def validate_transition(self, current: FlowState, next_state: FlowState) -> bool:
        if current == next_state:
            return True
        return next_state in self.VALID_TRANSITIONS.get(current, [])
