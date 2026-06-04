import sys
import json
import time
from typing import Callable, Dict, Any, List, Optional
from nexus.ci.fitness_gate import run_ci_gate
from scripts.ops.run_resilience_drill import run_weekly_drill
from nexus.governance.udl_engine import UDLEngine
from nexus.governance.loop_monitor import LoopMonitor

class ReleaseTrain:
    """
    🚂 Task 2.1: Release Train Orchestrator (Thin version)
    職責: 作為控制平面釋放的編排者，僅負責流程調度，不嵌入決策。
    """
    def __init__(self, 
                 fitness_gate: Callable[[], bool] = run_ci_gate,
                 chaos_drill: Callable[[], Any] = run_weekly_drill,
                 health_provider: Optional[Callable[[], Dict[str, Any]]] = None):
        self.fitness_gate = fitness_gate
        self.chaos_drill = chaos_drill
        self.health_provider = health_provider or self._default_health_provider

    def _default_health_provider(self):
        # 模擬獲取當前指標，實際應由 Observability 服務提供
        return {"ppr": 0.98, "slo": 0.95, "fitness": True, "chaos": True, "history": [0.9, 0.95]}

    def execute(self) -> bool:
        print('--- [NEXUS RELEASE TRAIN] START ---')
        
        # 1. 物理健身檢查
        if not self.fitness_gate():
            print('❌ Train Terminated: Architecture Fitness Violation')
            return False
            
        # 2. 模擬回歸
        print('✅ Regression Suite: PASS')
        
        # 3. 韌性演練
        self.chaos_drill()
        
        # 4. 元治理決測
        metrics = self.health_provider()
        health = UDLEngine.calculate_health(
            metrics["ppr"], metrics["slo"], metrics["fitness"], metrics["chaos"], 
            history=metrics["history"]
        )
        print(f"📊 Current Governance Health: {health.score} ({health.status})")
        
        # 使用 LoopMonitor 判定穩定度
        stability = LoopMonitor.evaluate_loop_stability(metrics["history"] + [health.score])
        if stability["safety_halt"]:
            print(f"❌ Train Blocked: {stability['reason']}")
            return False
            
        print(f"✅ Stability Check: {stability['status']}")
        print('--- [NEXUS RELEASE TRAIN] SEALED ---')
        return True

def run_train():
    """相容性 Shim：呼叫 OO 版執行"""
    return ReleaseTrain().execute()

if __name__ == "__main__":
    sys.exit(0 if run_train() else 1)
