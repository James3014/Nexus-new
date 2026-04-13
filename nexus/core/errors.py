from enum import Enum
from functools import wraps
from typing import Any, Dict, Optional, Callable

class ErrorCode(str, Enum):
    # Validation Errors
    VAL_001 = "VAL_001"  # Invalid Implementation Pack
    VAL_002 = "VAL_002"  # Schema Mismatch
    
    # System Errors
    SYS_001 = "SYS_001"  # Core Engine Crash
    SYS_002 = "SYS_002"  # Infrastructure Unavailable
    
    # Governance Errors
    GOV_001 = "GOV_001"  # Policy Drift Detected
    GOV_002 = "GOV_002"  # Audit Veto

class NexusError(Exception):
    """
    🛡️ Nexus Standardized Error
    Follows Clean Code principles for error reporting and observability.
    """
    def __init__(self, code_or_message: Any, message: Optional[str] = None, context: Optional[Dict[str, Any]] = None, details: Optional[Dict[str, Any]] = None):
        # Backward compatible path: NexusError("msg", details={...})
        if message is None:
            self.code = ErrorCode.SYS_001
            self.message = str(code_or_message)
            self.context = details or context or {}
            super().__init__(self.message)
            return

        self.code = code_or_message if isinstance(code_or_message, ErrorCode) else ErrorCode.SYS_001
        self.message = str(message)
        self.context = context or details or {}
        super().__init__(f"[{self.code}] {self.message}")

    @property
    def details(self) -> Dict[str, Any]:
        return self.context

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.code,
            "message": self.message,
            "context": self.context,
            "severity": "CRITICAL" if str(self.code).startswith("SYS") else "WARNING"
        }


class ValidationError(NexusError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.VAL_001, message, context=details)


class InfrastructureError(NexusError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.SYS_002, message, context=details)


class PhaseError(NexusError):
    def __init__(self, phase: str, message: str, details: Optional[Dict[str, Any]] = None):
        merged = {"phase": phase}
        if details:
            merged.update(details)
        super().__init__(ErrorCode.SYS_001, message, context=merged)


def safe_phase(phase: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that standardizes unknown exceptions into PhaseError."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except NexusError:
                raise
            except Exception as exc:
                raise PhaseError(phase, f"Unexpected crash in {phase}: {exc}") from exc
        return wrapper
    return decorator
