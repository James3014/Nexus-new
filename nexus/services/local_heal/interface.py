from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class PhaseResult:
    success: bool
    exit_layer: str = ""
    error_reason: str = ""
    error_metadata: dict = field(default_factory=dict)

class IPhase:
    """Interface for a pipeline phase (Reproduction, Planning, etc.)"""
    def execute(self, ctx: Any) -> PhaseResult:
        raise NotImplementedError
