import json
import os
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class DirichletBeliefEncoder:
    """🛡️ Nexus v0.6 Quantum Belief Encoder"""
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__import__("pathlib").Path(__file__).resolve().parents[2])
        self.knowledge_dir = self.repo_root / ".nexusknowledge"
        self.dist_path = self.knowledge_dir / "belief_distributions.jsonl"
        self.beliefs_path = self.knowledge_dir / "beliefs.jsonl"

    def load_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists(): return []
        with open(path, 'r', encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    def encode_to_quantum(self, belief_id: str, choices: List[str], alphas: Optional[List[float]] = None):
        """將單點信念轉換為 Dirichlet 概率分佈"""
        # 如果未提供 alphas，預設使用均勻先驗
        if alphas is None:
            alphas = [1.0] * len(choices)
        
        # 採樣 Dirichlet 分佈
        probabilities = np.random.dirichlet(alphas).tolist()
        
        distribution = {
            "belief_id": belief_id,
            "universes": [
                {"choice": c, "prob": round(p, 4), "status": "simulated"}
                for c, p in zip(choices, probabilities)
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": "Dirichlet-Prior-v1"
        }
        
        with open(self.dist_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(distribution, ensure_ascii=False) + '\n')
        
        print(f"🌀 [Quantum] Encoded {belief_id} into {len(choices)} universes.")
        return distribution

if __name__ == "__main__":
    encoder = DirichletBeliefEncoder()
    # 範例：將 IO 標準信念編碼為 aiohttp, requests, custom 三個宇宙
    encoder.encode_to_quantum(
        "B-IO-001", 
        ["aiohttp", "requests", "custom_socket"],
        alphas=[10.0, 2.0, 0.5] # 強烈偏好 aiohttp
    )
