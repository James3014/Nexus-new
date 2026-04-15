from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List

class EvalErrorCode(str, Enum):
    BROKER_TIMEOUT = "broker_timeout"
    NO_CHANGE = "no_change_candidate"
    SYNTAX_ERROR = "syntax_error"
    TEST_TIMEOUT = "test_timeout"
    TEST_FAILED = "test_failed"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class CandidateEvalResult:
    seed: int = 0
    score: float = 0.0
    hint: str = ""
    source: str = ""
    ok: bool = False
    status: str = "FAILED"
    error: Optional[str] = None
    error_codes: List[str] = field(default_factory=list)
    candidate_code: str = ""
    stdout: str = ""
    stderr: str = ""
    elapsed_sec: float = 0.0
