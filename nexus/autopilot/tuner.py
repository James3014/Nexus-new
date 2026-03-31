import json
import os
from pathlib import Path
from typing import Dict, List, Any

class RoutingTuner:
    """
    🧮 Nexus 調度自動調律器 (RoutingTuner)
    職責: 離線/定時分析調度日誌，動態優化分發權重矩陣。
    對齊 Phase 8.2 實施方案。
    """
    
    def __init__(self, project_root: str | Path = None, window: int = 200):
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        self.log_path = self.project_root / ".nexus/autopilot_dispatch_log.jsonl"
        self.weights_path = self.project_root / ".nexus/autopilot_weights.json"
        self.window = window
        self.weights = self._load_weights()

    def _load_weights(self) -> Dict:
        if not self.weights_path.exists():
            return {"latency": 0.4, "cap_match": 0.3, "load": 0.2, "gain": 0.1}
        try:
            with open(self.weights_path, 'r') as f:
                return json.load(f)
        except:
            return {"latency": 0.4, "cap_match": 0.3, "load": 0.2, "gain": 0.1}

    def tune_weights(self):
        """⚡ [P8.2] 執行權重微調循環。"""
        if not self.log_path.exists():
            print("⚠️ [Tuner] No dispatch logs found. Skipping tuning.")
            return

        logs = []
        with open(self.log_path, 'r') as f:
            for line in f:
                try:
                    logs.append(json.loads(line))
                except:
                    continue
        
        # 採樣最近 200 筆 (對位 P8.2 穩健參數)
        sample = logs[-self.window:]
        if not sample:
            return

        print(f"📊 [Tuner] Tuning weights based on {len(sample)} samples...")
        
        # 簡單的梯度補償邏輯
        adjustments = {"latency": 0.0, "cap_match": 0.0, "load": 0.0, "gain": 0.0}
        
        for entry in sample:
            success = entry.get("success", False)
            # 識別該次調度的主要貢獻維度 (簡化邏輯: 取得分最高的維度作為 dominant_dim)
            metrics = entry.get("node_metrics", {})
            features = entry.get("features", {})
            
            # 重新計算各維度得分
            scores = {
                "latency": (1 - min(metrics.get("latency", 50) / 200, 1)),
                "cap_match": 1.0 if features.get("lang", "").capitalize() in metrics.get("lang", []) else 0.5,
                "load": 1 - metrics.get("load", 0.1),
                "gain": metrics.get("gain", 85) / 100
            }
            
            dominant_dim = max(scores, key=scores.get)
            
            if success:
                adjustments[dominant_dim] += 0.01
            else:
                adjustments[dominant_dim] -= 0.02

        # 應用調整並歸一化
        new_weights = {}
        for dim, adj in adjustments.items():
            new_weights[dim] = max(0.05, self.weights[dim] + adj) # 設置 0.05 為下限防止維度歸零
            
        total = sum(new_weights.values())
        for dim in new_weights:
            new_weights[dim] = round(new_weights[dim] / total, 3)

        self.weights = new_weights
        self._persist_weights()
        print(f"✅ [Tuner] Weights optimized: {self.weights}")

    def _persist_weights(self):
        self.weights_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.weights_path, 'w') as f:
            json.dump(self.weights, f, indent=2)

if __name__ == "__main__":
    tuner = RoutingTuner()
    tuner.tune_weights()
