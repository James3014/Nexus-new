from typing import Dict, Any, List
from nexus.core.state_contracts import NexusState

class ToonRenderer:
    """👾 TOON (Trinity Output Optimization Network) 語義壓縮器 (PHA-020)"""
    @staticmethod
    def render(state: NexusState) -> str:
        """將長篇歷史、日誌壓縮為 Markdown 表格摘要"""
        summary = ["| Phase | ID | Status | Summary |", "|---|---|---|---|"]
        
        # 只取最後 3 筆詳細記錄
        for step in state.steps_history[-3:]:
            summary.append(f"| {step.phase} | {step.step_id} | {step.status} | {step.summary or 'none'} |")
            
        # 其他補上計數
        if len(state.steps_history) > 3:
            summary.append(f"| ... | ({len(state.steps_history)-3} others) | ... | (Compressed) |")
            
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
