import functools
import logging
import traceback
from typing import Any, Callable, TypeVar, Optional

logger = logging.getLogger(__name__)

class NexusError(Exception):
    """Base exception for all Nexus related errors."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}

class PhaseError(NexusError):
    """Raised when a pipeline phase fails."""
    pass

class ValidationError(NexusError):
    """Raised when data validation fails."""
    pass

class InfrastructureError(NexusError):
    """Raised when external infrastructure (DB, API, etc.) fails."""
    pass

T = TypeVar("T")

def safe_phase(phase_name: str):
    """
    Decorator to wrap pipeline phase methods, providing unified error handling,
    logging, and ensuring the phase does not crash the entire engine.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except NexusError as e:
                logger.error(f"Phase {phase_name} failed with known error: {e}")
                # Re-raise or handle based on phase importance
                raise
            except Exception as e:
                stack = traceback.format_exc()
                logger.error(f"Phase {phase_name} crashed with UNKNOWN error: {e}\n{stack}")
                raise PhaseError(f"Unexpected crash in {phase_name}: {e}", details={"stack": stack})
        return wrapper
    return decorator
