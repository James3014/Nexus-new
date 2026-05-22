from __future__ import annotations

from typing import Any

from nexus.services.gemini_cli import has_invalid_session_identifier


def direct_model_retryable_infra_failure(out: dict[str, Any], raw: str) -> tuple[bool, str]:
    error_category = str(out.get("error_category") or "").strip()
    token_count = int(out.get("tokens_used", 0) or 0)
    token_status = str(out.get("token_capture_status") or "").strip().lower()
    combined = f"{error_category}\n{raw}".lower()
    if error_category == "parse_failure" and token_status not in {"measured", "ok"}:
        return True, "parse_failure_without_measured_tokens"
    if token_count > 0:
        return False, ""
    if any(marker in combined for marker in ("quota", "resource exhausted", "rate limit", "usage limit", "429")):
        return False, "quota_or_rate_limit"
    if any(marker in combined for marker in ("oauth", "login required", "permission denied", "auth_confirmation_required")):
        return False, "auth_or_permission"
    if has_invalid_session_identifier(combined):
        return True, "gemini_invalid_session_identifier"
    if error_category in {"cli_error", "parse_failure"}:
        return True, f"{error_category}_without_tokens"
    return False, ""
