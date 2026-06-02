import time
from typing import List, Dict, Any
from nexus.optimize.capability_assembler import CapabilityAssembler
from nexus.optimize.optional_chain_rules import OptionalChainRules

class LazyExecutor:
    """
    ⚡ Nexus Lazy Executor (v2.5)
    職責: 將能力執行延後到必要時才啟動。
    """
    def __init__(self, flow: str, risk_score: int):
        self.flow = flow
        self.risk_score = risk_score
        self.chains = CapabilityAssembler.assemble_chain(flow)
        self.executed = []
        self.wall_time_saved = 0.0

    def run_core_chain(self):
        """執行核心鏈，這是必跑的最小開銷"""
        print(f"Running Core Chain: {self.chains['core']}")
        for cap in self.chains['core']:
            self.executed.append(cap)
        return True

    def run_optional_if_needed(self, context: Dict[str, Any]):
        """
        [NEXUS v2.5 Optimization]
        根據 Rule 引擎判斷是否需要追加執行 Optional 鏈。
        """
        upgrades = OptionalChainRules.evaluate_upgrades(context)
        if not upgrades:
            # 計算節省的時間 (Mock CodeIntel=4.0s, MemPalace=0.3s)
            saved = 0.0
            if "codeintel" in self.chains['optional']: saved += 4.0
            if "mempalace_gate" in self.chains['optional']: saved += 0.3
            self.wall_time_saved = saved
            print(f"⚡ [Lazy] Optional chain skipped. Estimated time saved: {saved}s")
            return False
            
        print(f"🚀 [Upgrade] Triggering optional capabilities: {upgrades}")
        for cap in upgrades:
            self.executed.append(cap)
        return True

if __name__ == "__main__":
    # 模擬高成本案例：nexus-value-gov-001 (Risk 55)
    executor = LazyExecutor(flow="hyper_sprint", risk_score=55)
    executor.run_core_chain()
    
    # 模擬證據充足的場景 (跳過 Optional)
    executor.run_optional_if_needed({"evidence_density": 0.9, "risk_flag": False})
    
    # 驗證結果
    print(f"Final Executed Chain: {executor.executed}")
    print(f"Total Time Saved: {executor.wall_time_saved}s")
