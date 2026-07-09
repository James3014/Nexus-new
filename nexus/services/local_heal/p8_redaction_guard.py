from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class P8RedactionResult:
    redaction_version: str = "1.0"
    input_prompt_hash: str = ""
    redacted_prompt: str = ""
    redacted_prompt_hash: str = ""
    secrets_detected: int = 0
    secrets_redacted: int = 0
    raw_prompt_logging_allowed: bool = False
    api_key_logging_allowed: bool = False
    redaction_passed: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(secret|token|password)\s*[=:]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(sk|pk|ak)[-_][A-Za-z0-9]{20,}"),
]


def redact_prompt(prompt: str) -> P8RedactionResult:
    input_hash = hashlib.sha256(prompt.encode()).hexdigest()
    redacted = prompt
    detected = 0
    for pat in _SECRET_PATTERNS:
        matches = pat.findall(redacted)
        detected += len(matches)
        redacted = pat.sub("[REDACTED]", redacted)
    redacted_hash = hashlib.sha256(redacted.encode()).hexdigest()
    return P8RedactionResult(
        input_prompt_hash=input_hash,
        redacted_prompt=redacted,
        redacted_prompt_hash=redacted_hash,
        secrets_detected=detected,
        secrets_redacted=detected,
        redaction_passed=True,
    )
