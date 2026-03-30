#!/usr/bin/env python3
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pathlib import Path
from nexus.core.state_contracts import NexusState
from nexus.engine.phase_plugin import PhasePlugin, PhaseResult

class BasePhaseHandler(PhasePlugin, ABC):
    """
    🧬 BasePhaseHandler
    Nexus v9 生命週期階段處理器的基底介面。
    已升級為 PhasePlugin (Sprint 13 R15)。
    """

    def __init__(self, project_root: Any, run_dir: Any, name: str = "UnknownPhase", priority: int = 100):
        super().__init__(name=name, priority=priority)
        self.project_root = Path(project_root) if project_root else None
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None

    def should_run(self, ctx: Any) -> bool:
        """Default implementation: Always run unless skipping requested in config."""
        if hasattr(ctx, 'kwargs') and ctx.kwargs.get("skip_phases"):
            if self.name in ctx.kwargs["skip_phases"]:
                return False
        return True

    def execute(self, pipeline: Any, ctx: Any) -> PhaseResult:
        """Adapts PhasePlugin.execute to legacy BasePhaseHandler.run.
        pipeline 參數保留供未來擴展，目前不使用。"""
        # ctx is usually PipelineContext
        legacy_result = self.run(ctx.state, ctx.pack)
        
        status = "success"
        if legacy_result.get("escalate"):
            status = "escalate"
        elif legacy_result.get("fail"):
            status = "fail"
            
        return PhaseResult(
            status=status,
            mutations=legacy_result,
            events=[] # Implementation for R16
        )

    @abstractmethod
    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行階段邏輯（舊版介面）。
        :param state: 當前的 NexusState 物件。
        :param context: 執行上下文 (Payload)。
        :return: 階段產出的數據包。
        """
        pass
