from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional
import re


class SliceType(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True)
class VerticalSlice:
    """垂直切分單元契約"""
    id: str
    description: str
    cross_layer_coverage: tuple[str, ...]  # e.g. ("ui", "api", "data")
    verify_command: str
    rollback_hint: str
    user_visible_increment: bool = True


@dataclass(frozen=True)
class VerticalSliceContract:
    schema_version: str = "vertical_slice_contract.v1"
    task_id: str = ""
    slices: List[VerticalSlice] = field(default_factory=list)
    total_slices: int = 0


class VerticalSlicePlanner:
    """Stage 3: 垂直切規劃器，強制執行垂直增量實作契約"""

    def validate_outline(self, outline_text: str) -> tuple[bool, str]:
        """判定大綱是否符合垂直切分原則"""
        
        # 1. 偵測水平切分特徵 (Horizontal Patterns)
        horizontal_patterns = [
            r"all api", r"all database", r"全介面", r"全資料庫",
            r"finish backend first", r"先做後端",
            r"refactor all services", r"一次重構所有服務"
        ]
        
        for p in horizontal_patterns:
            if re.search(p, outline_text, re.IGNORECASE):
                return False, f"HORIZONTAL_SLICE_DETECTED: Found forbidden horizontal pattern '{p}'"

        # 2. 檢查是否包含必要的垂直要素 (Vertical Signals)
        # 垂直切通常會包含多層組件與驗證指令
        if "verify" not in outline_text.lower() and "測試" not in outline_text:
            return False, "NO_VERIFY_COMMAND: Outline must specify verification for each slice"
            
        if "rollback" not in outline_text.lower() and "回滾" not in outline_text:
            return False, "NO_ROLLBACK_HINT: Outline must specify rollback/safe-point for each slice"

        return True, ""

    def plan_slices(self, task_id: str, outline_text: str) -> VerticalSliceContract:
        """從大綱中提取結構化垂直切分單元 (實作切片)"""
        # 這裡未來會接 LLM 進行精確解析，目前先做 Schema 結構化
        return VerticalSliceContract(
            task_id=task_id,
            slices=[],
            total_slices=0
        )
