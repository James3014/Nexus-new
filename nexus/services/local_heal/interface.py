from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class PhaseResult:
    success: bool
    exit_layer: str = ""
    error_reason: str = ""

class IPhase:
    """Interface for a pipeline phase (Reproduction, Planning, etc.)"""
    def execute(self, ctx: Any) -> PhaseResult:
        raise NotImplementedError
