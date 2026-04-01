import threading
import time
import json
from pathlib import Path
from typing import Dict, Any
from nexus.core.swarm import PeerSwarmOrchestrator

# 模擬環境內容。
PROJECT_ROOT = Path(__file__).parent.parent.parent
MANIFEST_PATH = PROJECT_ROOT / ".nexus" / "swarm" / "manifest.json"

def simulate_peer_node(peer_id: str, results: Dict):
    """模擬 Peer 節點在高併發環境下的競爭行內容分組。"""
    print(f"🧩 [{peer_id}] Node starting...")
    # 注入隨機延遲內容。
    time.sleep(0.1) 
    
    # 模擬引擎與任務內容分組。
    class MockEngine: project_root = PROJECT_ROOT
    task = "重構 auth/login.py"
    
    swarm = PeerSwarmOrchestrator(MockEngine(), task, peer_id=peer_id)
    # 覆蓋歷史記錄以進行核驗
    swarm.history = []
    
    # 執行 _repair 衝突偵測內容分組。
    # 這裡會觸發 check_manifest_lock
    outcome = swarm._repair("apply fix for race condition")
    results[peer_id] = outcome

def test_swarm_race_condition():
    """🛡️ v28.3 實戰測試：高併發環境下的資源競爭與避讓"""
    print("⚔️  Starting Real-Combat: Swarm-Race-Condition")
    
    # 1. 導通 Manifest 真值 (Peer-01 已鎖定內容內容)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump({
            "active_peers": [{"peer_id": "Peer-01"}],
            "decisions": [{"peer_id": "Peer-01", "target": "nexus/core/swarm.py", "type": "REPAIR_INTENT"}]
        }, f)

    # 2. 模擬 Peer-02 爭搶內容分組。
    results = {}
    simulate_peer_node("Peer-02", results)
    
    # 3. 核驗結果內容分組內容分組。
    outcome = results["Peer-02"]
    print(f"📊 Peer-02 Result State: {outcome.get('status')}")
    
    # 預期：Peer-02 應偵測到 Peer-01 的鎖定並自動避讓到 Memory 節點內容。
    assert outcome["status"] == "CONFLICT_DETECTED"
    assert "conflict_wait" in outcome["history"]
    
    print("✅ Combat Test: SUCCESS. Peer-02 performed defensive redirect.")

if __name__ == "__main__":
    test_swarm_race_condition()
