#!/usr/bin/env python3
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from nexus.core.state_contracts import NexusState

class BasePhaseHandler(ABC):
    """
    🧬 BasePhaseHandler
    Nexus v9 生命週期階段處理器的基底介面。
    實作此介面以確保各階段的 I/O 與紀錄一致。
    """
    def __init__(self, project_root: Any, run_dir: Any):
        self.project_root = project_root
        self.run_dir = run_dir

    @abstractmethod
    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行階段邏輯。
        :param state: 當前的 NexusState 物件。
        :param context: 執行上下文 (Payload)。
        :return: 階段產出的數據包。
        """
        pass
