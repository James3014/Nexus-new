from enum import Enum
from typing import Any, Dict, Optional

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
    def __init__(self, code: ErrorCode, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.code,
            "message": self.message,
            "context": self.context,
            "severity": "CRITICAL" if self.code.startswith("SYS") else "WARNING"
        }
