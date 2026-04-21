import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class HookResult:
    """⚓ 鉤子執行結果"""
    def __init__(self, status: str, message: str = "", metadata: Optional[Dict] = None):
        self.status = status # "OK", "WARN", "BLOCKED"
        self.message = message
        self.metadata = metadata or {}

class BaseHook(ABC):
    """⚓ Nexus ToolHook 基類"""
    @abstractmethod
    def pre_execute(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> HookResult:
        pass

    def post_execute(self, tool_name: str, result: Any, context: Dict[str, Any]) -> None:
        pass

class HarnessDirector:
    """🛡️ Nexus Harness 協調器：統一工具執行管線"""
    def __init__(self):
        self.hooks: List[BaseHook] = []

    def register_hook(self, hook: BaseHook):
        self.hooks.append(hook)

    def run_pre_execute(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> Tuple[str, List[str]]:
        """執行所有預檢鉤子"""
        overall_status = "OK"
        messages = []
        
        for hook in self.hooks:
            res = hook.pre_execute(tool_name, args, context)
            if res.status == "BLOCKED":
                return "BLOCKED", [f"[{hook.__class__.__name__}] {res.message}"]
            
            if res.status == "WARN":
                overall_status = "WARN"
                messages.append(f"[{hook.__class__.__name__}] {res.message}")
                
        return overall_status, messages

    def run_post_execute(self, tool_name: str, result: Any, context: Dict[str, Any]):
        """執行所有收尾鉤子"""
        for hook in self.hooks:
            try:
                hook.post_execute(tool_name, result, context)
            except Exception as e:
                logger.warning(f"⚠️ [Harness] Post-execute hook failed ({hook.__class__.__name__}): {e}")

# --- 具體 Hook 適配器 (Phase 10 精華) ---

class CapabilityHook(BaseHook):
    """🛡️ 權限鉤器 (Hard-Fail)"""
    def pre_execute(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> HookResult:
        from nexus.governance.capability_gate import CapabilityGate
        gate = CapabilityGate()
        phase = context.get("phase", "P")
        allowed_tools = gate.get_tools(phase)
        
        if tool_name not in allowed_tools:
            return HookResult("BLOCKED", f"Tool '{tool_name}' forbidden in Phase {phase}.")
        return HookResult("OK")

class CostAwareHook(BaseHook):
    """💰 成本鉤器 (Threshold / Hard-Fail)"""
    def pre_execute(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> HookResult:
        from nexus.core.cost_hook import CostHook
        hook = CostHook()
        
        predicted = hook.predict_cost(tool_name, args)
        remaining = context.get("budget_remaining", 5000)
        
        status = hook.budget_check(predicted, remaining)
        if status == "BLOCKED":
            return HookResult("BLOCKED", f"Budget Exceeded! Predicted {predicted} > Remaining {remaining}")
        
        if status == "WARN_OPTIMIZE":
            return HookResult("WARN", f"High Cost Alert! {predicted} will consume >70% of budget.")
        
        return HookResult("OK")

class CritiqueHook(BaseHook):
    """🛡️ 美學意圖鉤器 (Warning)"""
    def pre_execute(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> HookResult:
        from scripts.engine.critique_engine import CritiqueEngine
        engine = CritiqueEngine()
        
        # 僅掃描與計畫相關的文字欄位
        plan_text = args.get("plan", args.get("instruction", ""))
        try:
            engine.prescan(plan_text)
            return HookResult("OK")
        except Exception as e:
            # 依據 Hybrid 建議：美學僅作警告，不阻塞執行
            return HookResult("WARN", str(e))

# --- Singleton Director Configuration ---

def get_default_director() -> HarnessDirector:
    director = HarnessDirector()
    director.register_hook(CapabilityHook())
    director.register_hook(CostAwareHook())
    director.register_hook(CritiqueHook())
    return director

default_director = get_default_director()
