from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

@dataclass
class PhaseResult:
    """Result of a single phase execution."""
    status: Literal["success", "skip", "escalate", "fail"]
    mutations: Dict[str, Any]
    events: List[Any] = None # Will be linked to R16 later

class ErrorAction(Enum):
    CONTINUE = "continue"
    RETRY = "retry"
    ABORT = "abort"
    ESCALATE = "escalate"

class PhasePlugin(ABC):
    """
    Abstract base class for all pipeline phases.
    Implemented as plugins for Sprint 13 R15.
    """
    def __init__(self, name: str, priority: int = 100):
        self.name = name
        self.priority = priority

    @abstractmethod
    def should_run(self, ctx: Any) -> bool:
        """Determines if this phase should be executed."""
        ...

    @abstractmethod
    def execute(self, pipeline: Any, ctx: Any) -> PhaseResult:
        """Executes the core logic of the phase."""
        ...

    def on_error(self, ctx: Any, error: Exception) -> ErrorAction:
        """Handles errors occurring during phase execution."""
        return ErrorAction.ABORT


class PhaseExecutor(Protocol):
    """Composition-first phase seam used while legacy mixins are retired."""

    name: str
    priority: int

    def should_run(self, ctx: Any) -> bool: ...

    def execute(self, pipeline: Any, ctx: Any) -> PhaseResult: ...

class PhaseRegistry:
    """Registry for managing and ordering PhasePlugins."""
    def __init__(self):
        self._plugins: Dict[str, PhasePlugin] = {}

    def register(self, plugin: PhasePlugin):
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str):
        if name in self._plugins:
            del self._plugins[name]

    def get_ordered_plugins(self) -> List[PhasePlugin]:
        """Returns plugins sorted by priority."""
        def _safe_priority(p):
            # Handle MagicMock in tests
            try:
                prio = p.priority
                if hasattr(prio, "assert_called"):
                    return 0
                return int(prio)
            except (AttributeError, TypeError, ValueError):
                return 100
        return sorted(self._plugins.values(), key=_safe_priority)
