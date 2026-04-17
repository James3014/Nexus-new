from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class SpeculativeClassifier:
    """
    🧠 Nexus Speculative Classifier (v24 Silk)
    負責在 P (Plan) 階段前進行維度掃描與「猜測性補全」。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        # 定義核心維度與感應模式
        self.DIMENSIONS = {
            "data_source": ["json", "csv", "api", "db", "lancedb", "manifest"],
            "ui_framework": ["react", "vue", "vanilla", "css", "tailwind"],
            "logic_scope": ["auth", "scaling", "repair", "optimization", "refactor"],
            "test_gate": ["acceptance", "contract", "ci", "performance"]
        }

    def analyze_and_hydrate(self, task: str) -> Dict[str, Any]:
        """分析任務並從記憶中補全維度，整合 L1 Clarify-Manager"""
        task_l = task.lower()
        found_dims = {}
        missing_dims = []

        for dim, keywords in self.DIMENSIONS.items():
            hit = [k for k in keywords if k in task_l]
            if hit:
                found_dims[dim] = hit[0]
            else:
                # 🔮 絲滑點：嘗試從 Learn 歷史中「猜測」
                guessed = self._guess_from_history(dim)
                if guessed:
                    found_dims[dim] = f"{guessed} (猜測自歷史)"
                else:
                    missing_dims.append(dim)

        # 🚀 [L1:Clarify-Manager] 信心度與補問閘門
        confidence = 0.8 if not missing_dims else (0.4 if len(missing_dims) > 2 else 0.6)
        clarify_required = confidence < 0.6
        
        clarify_suggestions = []
        if clarify_required:
            for dim in missing_dims:
                clarify_suggestions.append(f"Could you specify the preferred {dim}?")

        return {
            "task": task,
            "intent_confidence": confidence,
            "dimensions": found_dims, # 統一命名為 dimensions 供 L3 使用
            "missing_dimensions": missing_dims,
            "clarify_required": clarify_required,
            "clarify_suggestions": clarify_suggestions,
            "is_ready_for_shadow": len(found_dims) >= 2
        }


    def _guess_from_history(self, dimension: str) -> str | None:
        """
        從 Learn Registry 獲取最近偏好。
        """
        try:
            # 簡化邏輯：優先回傳與當前專案最相關的常用庫
            if dimension == "data_source": return "lancedb"
            if dimension == "test_gate": return "acceptance"
            return None
        except:
            return None
