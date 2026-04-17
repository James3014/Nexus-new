import json
from pathlib import Path
from typing import Dict, Any

class BeliefEngine:
    """維護當前的邏輯假設與信心度 (Subjective Trust)。"""
    def __init__(self, state_file: Path = Path(".nexus/belief_state.json")):
        self.state_file = state_file
        self.beliefs = {}
        self._load()

    def _load(self):
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                self.beliefs = json.load(f)

    def assess_confidence(self, task_id: str, assumption: str) -> float:
        """根據歷史證據評估信心。"""
        # 簡單模型：若有歷史相同假設則提高，否則基準為 0.7
        return self.beliefs.get(assumption, {}).get("confidence", 0.7)

    def update_belief(self, task_id: str, assumption: str, confidence: float, evidence_id: str):
        self.beliefs[assumption] = {
            "confidence": confidence,
            "evidence": evidence_id,
            "task_id": task_id
        }
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.beliefs, f, indent=2)
