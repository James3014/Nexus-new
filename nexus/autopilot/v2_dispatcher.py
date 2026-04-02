from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import time

from nexus.engine.phases.task_predictor import TaskPredictor
from nexus.autopilot.client import NSPClient

class HighDimDispatcher:
    """
    🧮 Nexus 高維調度器 (HighDimDispatcher)
    職責: 根據任務特徵 (Features) 與節點感測數據 (Sensing Data) 進行加權評分與調度。
    """
    
    # 對齊 Phase 8.1 權重分配
    DEFAULT_WEIGHTS = {"latency": 0.4, "cap_match": 0.3, "load": 0.2, "gain": 0.1}
    
    def __init__(self, project_root: str | Path = None):
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        self.nsp = NSPClient("localhost:8516")
        self.weights_path = self.project_root / ".nexus/autopilot_weights.json"
        self.log_path = self.project_root / ".nexus/autopilot_dispatch_log.jsonl"
        self.weights = self._load_weights()
        self.predictor = TaskPredictor()

    def _load_weights(self) -> Dict:
        if not self.weights_path.exists():
            self.weights_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.weights_path, 'w') as f:
                json.dump(self.DEFAULT_WEIGHTS, f, indent=2)
            return self.DEFAULT_WEIGHTS
        try:
            with open(self.weights_path, 'r') as f:
                return json.load(f)
        except:
            return self.DEFAULT_WEIGHTS

    def score_node(self, features: Dict, node: Dict) -> float:
        """⚖️ 為節點進行四維度歸一化評分。"""
        # 1. 延遲 (Latency) - 低延遲為高分
        norm_latency = 1 - min(node.get("latency", 50) / 200, 1)
        
        # 2. 語言能力匹配 (Cap Match)
        node_langs = [l.lower() for l in node.get("lang", [])]
        task_lang = features.get("lang", "unknown").lower()
        norm_cap = 1.0 if task_lang in node_langs else 0.5
        
        # 3. 負載 (Load) - 低負載為高分
        norm_load = 1 - node.get("load", 0.1)
        
        # 4. 學習增益 (Gain) - 高增益為高分
        norm_gain = node.get("gain", 85) / 100
        
        score = (self.weights["latency"] * norm_latency +
                 self.weights["cap_match"] * norm_cap +
                 self.weights["load"] * norm_load +
                 self.weights["gain"] * norm_gain)
        return score

    def dispatch(self, task: str, codebase: str = "") -> str:
        """🚀 執行調度。"""
        features = self.predictor.analyze(task, codebase)
        nodes = list(self.nsp.sensing_stream())
        
        if not nodes:
            return "LOCAL_FALLBACK"

        best_node = max(nodes, key=lambda n: self.score_node(features, n))
        node_id = best_node["id"]
        
        # 🧪 第一筆高維調度 Log 驗證
        self._log_dispatch(task, node_id, features, best_node)
        return node_id

    def _log_dispatch(self, task: str, node_id: str, features: Dict, node_info: Dict):
        log_entry = {
            "timestamp": int(time.time()),
            "task": task[:50],
            "node_id": node_id,
            "features": features,
            "node_metrics": node_info,
            "weights": self.weights,
            "success": True # 初始預設為成功，後續由 Tuner 更新
        }
        with open(self.log_path, 'a') as f:
            f.write(json.dump_string(log_entry) + "\n") if hasattr(json, "dump_string") else f.write(json.dumps(log_entry) + "\n")

if __name__ == "__main__":
    dispatcher = HighDimDispatcher()
    result = dispatcher.dispatch("Python bugfix for timezone alignment", "1000 LOC")
    print(f"✅ [Dispatcher] First high-dim dispatch completed: {result}")
