from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, List, Optional


class BudgetPressure(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HistoryMode(str, Enum):
    FULL = "full"
    SUMMARIZED = "summarized"
    DROPPED = "dropped"


@dataclass(frozen=True)
class TaskCompactionReceipt:
    """任務上下文壓縮收據"""
    schema_version: str = "task_compaction_receipt.v1"
    task_id: str = ""
    previous_context_len: int = 0
    current_context_len: int = 0
    compression_ratio: float = 0.0
    history_mode: HistoryMode = HistoryMode.FULL
    compaction_reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["history_mode"] = self.history_mode.value
        return data


class BudgetGovernor:
    """Stage 4: 指令預算守衛，管理上下文壓縮與執行降級策略"""

    def calculate_pressure(self, current_rounds: int, current_tokens: int, max_rounds: int = 15) -> BudgetPressure:
        if current_rounds >= max_rounds * 0.9 or current_tokens > 100000:
            return BudgetPressure.CRITICAL
        if current_rounds >= max_rounds * 0.7 or current_tokens > 70000:
            return BudgetPressure.HIGH
        if current_rounds >= max_rounds * 0.4 or current_tokens > 40000:
            return BudgetPressure.MEDIUM
        return BudgetPressure.LOW

    def determine_compaction_strategy(self, pressure: BudgetPressure) -> dict[str, Any]:
        """根據預算壓力決定降級策略"""
        if pressure == BudgetPressure.CRITICAL:
            return {
                "history_mode": HistoryMode.DROPPED,
                "research_mode": "disabled",
                "max_rounds_delta": -2,
                "decomposition_required": True
            }
        if pressure == BudgetPressure.HIGH:
            return {
                "history_mode": HistoryMode.SUMMARIZED,
                "research_mode": "targeted",
                "max_rounds_delta": -1,
                "decomposition_required": False
            }
        if pressure == BudgetPressure.MEDIUM:
            return {
                "history_mode": HistoryMode.SUMMARIZED,
                "research_mode": "full",
                "max_rounds_delta": 0,
                "decomposition_required": False
            }
        return {
            "history_mode": HistoryMode.FULL,
            "research_mode": "full",
            "max_rounds_delta": 0,
            "decomposition_required": False
        }

    def emit_compaction_receipt(self, task_id: str, prev_len: int, curr_len: int, mode: HistoryMode, reasons: List[str]) -> TaskCompactionReceipt:
        ratio = 1.0 - (curr_len / prev_len) if prev_len > 0 else 0.0
        return TaskCompactionReceipt(
            task_id=task_id,
            previous_context_len=prev_len,
            current_context_len=curr_len,
            compression_ratio=round(ratio, 4),
            history_mode=mode,
            compaction_reason_codes=tuple(reasons)
        )
