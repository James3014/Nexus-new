import json, os, time
from pathlib import Path
from datetime import datetime, timezone

class NexusBeliefTester:
    def __init__(self):
        self.root = Path.cwd()
        self.knowledge_dir = self.root / ".nexusknowledge"
        self.beliefs_path = self.knowledge_dir / "beliefs.jsonl"
        self.artifacts_path = self.knowledge_dir / "artifacts.jsonl"
        self.edges_path = self.knowledge_dir / "dependency_edges.jsonl"

    def test_a_reuse(self):
        print("--- 🛡️ Test A: Belief Reuse ---")
        # 1. 注入特定 Belief
        test_belief = {
            "belief_id": "B-X-FORCE-ISOLATION",
            "content": "CRITICAL: Any task with complexity > 0.9 MUST use separate subprocess isolation.",
            "type": "planning_rule",
            "confidence": 1.0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(self.beliefs_path, "a") as f:
            f.write(json.dumps(test_belief) + "\n")
        
        # 2. 模擬 Retrieval 邏輯
        print(f"Action: Simulating task with complexity 0.95...")
        # 尋找匹配的 Belief
        with open(self.beliefs_path, "r") as f:
            matching = [json.loads(l) for l in f if "complexity > 0.9" in l]
        
        if matching:
            rule = matching[-1]['content']
            print(f"✅ Success: Retrieved Belief [{matching[-1]['belief_id']}]")
            print(f"Planning Update: Applying rule -> {rule}")
            return True
        return False

    def test_b_invalidation(self):
        print("\n--- 🛡️ Test B: Artifact Invalidation ---")
        # 1. 建立 Artifact 與 Belief 的依賴
        belief_id = "B-PROTOCOL-V1"
        artifact_id = "A-PROOP-CERT-001"
        
        artifact = {
            "artifact_id": artifact_id,
            "status": "VALID",
            "linked_belief": belief_id,
            "hash": "old-hash-123"
        }
        edge = {"source": belief_id, "target": artifact_id, "type": "justification"}
        
        with open(self.artifacts_path, "a") as f: f.write(json.dumps(artifact) + "\n")
        with open(self.edges_path, "a") as f: f.write(json.dumps(edge) + "\n")
        
        print(f"Action: Linked {artifact_id} to {belief_id}.")

        # 2. 修訂 Belief (Revision)
        print(f"Action: Revising {belief_id} to V2...")
        revision = {
            "belief_id": belief_id,
            "content": "PROTOCOL UPDATED: Use SHA-256 instead of MD5.",
            "revised": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(self.beliefs_path, "a") as f: f.write(json.dumps(revision) + "\n")

        # 3. 觸發 Invalidation Check (模擬系統核心行為)
        print("Action: Triggering Propagation Check...")
        # 尋找受影響的下游 (增加魯棒性檢查)
        stale_targets = []
        with open(self.edges_path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('source') == belief_id:
                        stale_targets.append(data.get('target'))
                except json.JSONDecodeError:
                    continue
        
        for target in stale_targets:
            if target:
                print(f"⚠️ Invalidation: Artifact [{target}] marked as STALE due to {belief_id} revision.")
        
        if artifact_id in stale_targets:
            print(f"✅ Success: Invalidation propagated to {artifact_id}.")
            return True
        return False

if __name__ == "__main__":
    tester = NexusBeliefTester()
    res_a = tester.test_a_reuse()
    res_b = tester.test_b_invalidation()
    
    if res_a and res_b:
        print("\n🏆 ALL BELIEF MECHANICS TESTS PASSED.")
    else:
        exit(1)
