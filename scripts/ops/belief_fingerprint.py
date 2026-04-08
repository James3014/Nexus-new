import json
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class ConsensusPeering:
    """🛡️ Nexus v0.5 P2P Peering (Tailscale Mesh Simulation)"""
    def __init__(self, swarm_id: str, repo_root: Optional[Path] = None):
        self.swarm_id = swarm_id
        self.repo_root = repo_root or Path(__import__("pathlib").Path(__file__).resolve().parents[2])
        self.peer_dir = self.repo_root / ".nexusknowledge/peers"
        self.peer_dir.mkdir(parents=True, exist_ok=True)
        
    def broadcast_fingerprint(self, fingerprint: Dict[str, Any]):
        """將指紋寫入 P2P 共享區，模擬 gRPC 廣播"""
        file_path = self.peer_dir / f"{self.swarm_id}_fingerprint.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(fingerprint, f, ensure_ascii=False, indent=2)
        print(f"📡 [Peering] Swarm {self.swarm_id} broadcasted fingerprint.")

    def discover_peers(self) -> List[Dict[str, Any]]:
        """掃描共享區，發現其他 Swarm 的指紋"""
        peers = []
        for p_file in self.peer_dir.glob("*_fingerprint.json"):
            if self.swarm_id not in p_file.name:
                with open(p_file, 'r', encoding='utf-8') as f:
                    peers.append(json.load(f))
        return peers

class BeliefFingerprint:
    """🧪 信念指紋與漂移偵測"""
    def __init__(self, swarm_id: str, repo_root: Optional[Path] = None):
        self.swarm_id = swarm_id
        self.peering = ConsensusPeering(swarm_id, repo_root)
        self.drift_log = (repo_root or Path('.')).resolve() / ".nexusknowledge/drift_detected.jsonl"

    def calculate_drift(self, local_beliefs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stage 1: DISCOVER - 信念漂移發現"""
        drift_events = []
        
        # 1. 廣播本地指紋
        for b in local_beliefs:
            # 建立指紋
            content_str = json.dumps(b.get("content"), sort_keys=True)
            fingerprint = {
                "swarm_id": self.swarm_id,
                "belief_id": b["id"],
                "content_hash": hashlib.sha256(content_str.encode()).hexdigest(),
                "trust_tier": b.get("trust_tier", "unverified"),
                "local_weight": 0.9,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.peering.broadcast_fingerprint(fingerprint)
            
            # 2. 發現 Peers 並比對
            peers = self.peering.discover_peers()
            for peer in peers:
                if peer["belief_id"] == b["id"] and peer["content_hash"] != fingerprint["content_hash"]:
                    # 偵測到漂移
                    drift_score = 0.8 # 模擬計算結果
                    event = {
                        "belief_id": b["id"],
                        "local_swarm": self.swarm_id,
                        "peer_swarm": peer["swarm_id"],
                        "drift_score": drift_score,
                        "local_hash": fingerprint["content_hash"],
                        "peer_hash": peer["content_hash"],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    drift_events.append(event)
                    print(f"🚨 [Discover] DRIFT DETECTED on {b['id']} with Swarm {peer['swarm_id']}!")

        if drift_events:
            with open(self.drift_log, 'a', encoding='utf-8') as f:
                for e in drift_events:
                    f.write(json.dumps(e, ensure_ascii=False) + '\n')
        
        return drift_events

if __name__ == "__main__":
    # 測試腳本：模擬 Swarm A 偵測到與已存在的 Swarm B 指紋衝突
    tester = BeliefFingerprint("swarm-alpha")
    mock_beliefs = [{"id": "B-RULE-001", "content": "use_aiohttp=True"}]
    tester.calculate_drift(mock_beliefs)
