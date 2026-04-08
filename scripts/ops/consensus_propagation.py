import json
from pathlib import Path
from scripts.ops.brain_loop_closure import BrainLoopClosure

class ConsensusPropagator:
    def __init__(self, repo_root=None):
        self.repo_root = repo_root or Path(__import__("pathlib").Path(__file__).resolve().parents[2])
        self.closure = BrainLoopClosure(self.repo_root)

    def broadcast_final(self, certified_consensus):
        """Stage 5: PROPAGATE - 原子更新與傳播"""
        # 利用 v0.2 的 propagation 邏輯完成原子修訂
        self.closure.propagate_belief_revision(
            certified_consensus["belief_id"], 
            "active" # 強制重置為共識內容
        )
        print(f"🚀 [Propagate] Consensus sync complete for {certified_consensus['belief_id']}")
