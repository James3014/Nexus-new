from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8CRedactionAuditResult:
    audit_version: str = "1.0"
    prompt_capsule_present: bool = False
    receipt_present: bool = False
    redacted_prompt_hash_present: bool = False
    raw_prompt_absent: bool = True
    raw_response_absent: bool = True
    api_key_absent: bool = True
    secret_patterns_absent: bool = True
    provider_response_hash_present: bool = False
    redacted_response_summary_present: bool = False
    private_data_absent: bool = True
    repo_context_absent: bool = True
    redaction_audit_passed: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(secret|token|password)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(sk|pk|ak)[-_][A-Za-z0-9]{20,}"),
]


def audit_redaction(data: dict[str, Any]) -> P8CRedactionAuditResult:
    blocked = []
    has_capsule = bool(data.get("prompt_capsule"))
    has_receipt = bool(data.get("receipt"))

    all_text = str(data)
    for pat in _SECRET_PATTERNS:
        if pat.search(all_text):
            blocked.append("secret_pattern_detected")

    if data.get("raw_prompt_logged"): blocked.append("raw_prompt_logged")
    if data.get("raw_response_logged"): blocked.append("raw_response_logged")
    if data.get("api_key_logged"): blocked.append("api_key_logged")
    if data.get("repo_context_included"): blocked.append("repo_context_included")
    if data.get("private_data_included"): blocked.append("private_data_included")

    rph = bool(data.get("redacted_prompt_hash"))
    prh = bool(data.get("provider_response_hash"))
    if not rph: blocked.append("redacted_prompt_hash_missing")
    smoke_done = data.get("network_call_completed", False)
    if smoke_done and not prh: blocked.append("provider_response_hash_missing")

    return P8CRedactionAuditResult(
        prompt_capsule_present=has_capsule,
        receipt_present=has_receipt,
        redacted_prompt_hash_present=rph,
        provider_response_hash_present=prh,
        redacted_response_summary_present=bool(data.get("provider_response_redacted")),
        redaction_audit_passed=len(blocked) == 0,
        blocked_reasons=blocked,
    )
