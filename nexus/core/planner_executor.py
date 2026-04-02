from typing import Any, Dict, List, Optional, Tuple
import logging
from nexus.core.state_contracts import NexusState
from nexus.core.capability_gate import CapabilityGate

logger = logging.getLogger(__name__)

class Planner:
    """
    🧠 Nexus 規劃器 (Composio P1)
    負責純思維、研究與方案制定，物理隔離工具執行以防止意外變更。
    """
    def __init__(self, state: NexusState):
        self.state = state
        self.gate = CapabilityGate()

    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        """🎯 僅使用讀取/搜尋工具生成具現化計畫"""
        logger.info("🧠 [Planner] Generating decoupled plan (Thinking phase)...")
        # 模擬 Plan 生成
        return {
            "steps": ["Read source", "Diagnose error", "Apply patch"],
            "tools_needed": ["read_file", "multi_replace"],
            "intent": "Repair CI failure in core.py"
        }

class Executor:
    """
    ⚡ Nexus 執行器 (Composio P1)
    負責接收計畫並透過 JIT 注入的工具集進行物理具現化。
    """
    def __init__(self, state: NexusState):
        self.state = state
        self.gate = CapabilityGate()

    def execute_plan(self, plan: Dict[str, Any]):
        """🎯 基於 JIT 工具集執行規劃內容"""
        phase = self.state.current_phase
        tools = self.gate.managed_toolsets(phase)
        
        logger.info(f"⚡ [Executor] Executing plan in phase {phase} with {len(tools)} tools...")
        for step in plan.get("steps", []):
            logger.info(f"  -> Action: {step}")
        
        return {"status": "SUCCESS", "executed_steps": len(plan.get("steps", 0))}
