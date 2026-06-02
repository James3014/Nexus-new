from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import re


@dataclass(frozen=True)
class CRISPYArtifact:
    """CRISPY 階段性文件產物"""
    file_name: str
    content: str
    stage: str
    version: str = "v1.0"


class CRISPYArtifactManager:
    """Stage 2: CRISPY 文件管理器，負責模板生成與內容契約校驗"""

    TEMPLATES = {
        "Questions.md": "# ❓ CRISPY: Questions\n\n## 1. 缺失資訊 (Missing Info)\n- \n\n## 2. 限制條件 (Constraints)\n- \n\n## 3. 開放問題 (Open Questions)\n- \n",
        "Research.md": "# 🔍 CRISPY: Research\n\n## 1. 現況分析 (Current State)\n- \n\n## 2. 核心組件 (Core Components)\n- \n\n## 3. 執行流程 (Execution Flows)\n- \n",
        "Design.md": "# 🎨 CRISPY: Design\n\n## 1. 目標狀態 (Target State)\n- \n\n## 2. 核心取捨 (Trade-offs)\n- \n\n## 3. 架構決策 (Architecture Decisions)\n- \n",
        "StructureOutline.md": "# 🏗️ CRISPY: Structure Outline\n\n## 1. 執行階段 (Phases)\n- \n\n## 2. 垂直切分順序 (Vertical Slices)\n- \n\n## 3. 關鍵驗證點 (Verification Points)\n- \n",
        "Plan.md": "# 📋 CRISPY: Implementation Plan\n\n## 1. 修改檔案清單 (Target Files)\n- \n\n## 2. 施工步驟 (Execution Steps)\n- \n\n## 3. 測試與驗證 (Tests)\n- \n"
    }

    def generate_template(self, file_name: str) -> str:
        return self.TEMPLATES.get(file_name, "# Artifact")

    def validate_content(self, file_name: str, content: str) -> tuple[bool, str]:
        """執行 Stage 2 強制契約校驗"""
        if file_name == "Research.md":
            # Research 不可含施工語意
            design_keywords = ["implement", "modify", "should change", "實作", "應該改"]
            for kw in design_keywords:
                if kw in content.lower():
                    return False, f"RESEARCH_CONTAINS_DESIGN: Found design keyword '{kw}'"
        
        if file_name == "Design.md":
            # Design 不可進到逐行施工細節
            if "line " in content.lower() or "@@" in content:
                 return False, "DESIGN_CONTAINS_PLAN_LEVEL_DETAIL: Found implementation-specific details"

        return True, ""
