from typing import Any, Dict, List, Optional, Tuple
from nexus.core.state_contracts import NexusState

class ToonRenderer:
    """👾 TOON (Trinity Output Optimization Network) 語義壓縮器 v2.0"""
    @staticmethod
    def render(state: NexusState, aggression: float = 0.7) -> str:
        """將長篇歷史、日誌壓縮為 Markdown 表格摘要 (v2.0 Bayesian Adaptive)"""
        # 🧪 [Round 20 Evolution] Dynamic Record Limiting
        # aggression 0.1 -> show 10 records
        # aggression 0.9 -> show 1 record
        limit = max(1, int(11 - (aggression * 10)))
        
        summary = ["| Phase | ID | Status | Summary |", "|---|---|---|---|"]
        
        relevant_steps = state.steps_history[-limit:]
        for step in relevant_steps:
            summary.append(f"| {step.phase} | {step.step_id} | {step.status} | {step.summary or 'none'} |")
            
        if len(state.steps_history) > limit:
            summary.append(f"| ... | ({len(state.steps_history)-limit} others) | ... | (TOON-2.0 Compressed) |")
            
        return "\n".join(summary)

class ContextScorer:
    """🎯 Trinity Context Scorer: 依階段決定檔案權重 (PHA-021)"""
    @staticmethod
    def get_relevance(phase: str, file_path: str) -> float:
        path = file_path.lower()
        if phase == "P":
            return 1.0 if any(k in path for k in ["index", "manifest", "todo"]) else 0.5
        if phase == "D":
            return 1.0 if any(k in path for k in ["test", "log", "trace"]) else 0.4
        if phase in ["R", "A"]:
            return 1.0 if path.endswith(".py") or path.endswith(".js") else 0.3
        return 0.5
