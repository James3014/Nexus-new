#!/usr/bin/env python3
from abc import ABC, abstractmethod
from typing import Any, Dict
from nexus.core.state_contracts import NexusState


class BasePhaseHandler(ABC):
    """
    🧬 BasePhaseHandler
    Nexus v9 生命週期階段處理器的基底介面。
    實作此介面以確保各階段的 I/O 與紀錄一致。
    """

    def __init__(self, project_root: Any, run_dir: Any):
        from pathlib import Path

        self.project_root = Path(project_root) if project_root else None
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None

    @abstractmethod
    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行階段邏輯。
        :param state: 當前的 NexusState 物件。
        :param context: 執行上下文 (Payload)。
        :return: 階段產出的數據包。
        """
        pass
