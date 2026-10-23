"""Account-level Agy failure signals, read only from agy's own error channels (#2415).

The Gateway Agy worker route (``nexus/executors/worker_registry.py``) and
``scripts/ops/nexus-agy-dispatch`` decide from a failed agy run whether to retire
the account (quota: model-family cooldown; auth / unavailable: account-wide
mark-bad) and rotate to the next one.  Both used to match substrings of
stdout + stderr.  stdout carries the model's reply, so a reply mentioning
"401" or "quota" retired a healthy account, and a host-wide outage
("UNAVAILABLE (code 503)") retired every account in turn.

This module reads, in order of trust:

1. ``AGY_ERROR: {...}`` lines on stderr: agy's structured error with ``status``
   (gRPC-style name) and ``error_code`` (HTTP code when ``code_kind`` is
   ``http``).  Real samples (Mac mini operation logs, 2026-10):

   * ``{"status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http",...}``
     ("Individual quota reached ... Resets in 7h1m27s.")
   * ``{"status":"UNAVAILABLE","error_code":503,"code_kind":"http",...}``
     ("No capacity available for model ... on the server")
   * ``{"status":"UNKNOWN","error_code":2,"code_kind":"grpc",...}``
     (network read timeout: not an account failure)
   * ``{"short_error":"Your previous response contained an improperly formatted
     function call ...","retryable":false}`` (no status: not an account failure)

2. In ``--output-format json`` mode only, the result envelope's ``error`` field
   when ``status`` is ``ERROR`` (agy's message, never the model's ``response``),
   e.g. ``"authentication failed or timed out"`` or ``"Individual quota
   reached ..."``.

3. Headless tool permission denials are work failures, never account failures.
   Their tool/path diagnostics come only from stderr or result envelopes.

4. Only when neither exists: agy's stderr text (agy's diagnostics channel; the
   model's reply never goes there).  stdout is never scanned.

A structured error decides alone: when one is present, stderr prose is not
consulted.  Only the last ``AGY_ERROR`` line decides (#2433 N3): agy prints
its terminal error last, so an earlier RESOURCE_EXHAUSTED followed by a
final UNKNOWN is deliberately not treated as quota (no retirement).  The caps on
account-wide retirements per run live with the callers;
``max_account_retirements`` is the shared limit.

The two callers treat ``RATE_LIMITED`` differently, on purpose (#2433 N2):
``nexus-agy-dispatch`` retires the account through the pool
(``retire_failed_claim``: account-global cooldown) and counts it toward the
cap; the Gateway worker route only skips it for the current run.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from nexus.services.external_account_pool import AccountFailureKind

AGY_UPSTREAM_UNAVAILABLE = "agy_upstream_unavailable"
DEFAULT_MAX_ACCOUNT_RETIREMENTS = 3

_AGY_ERROR_LINE_RE = re.compile(r"(?m)^AGY_ERROR:\s*(?P<payload>\{.*\})\s*$")

# #2403: agy without usable credentials prints an interactive OAuth login
# prompt on stderr, waits 60 s for a pasted code and exits 1.
AGY_LOGIN_PROMPT_MARKERS = (
    "Authentication required. Please visit the URL to log in",
    "Waiting for authentication",
    "authentication failed or timed out",
)

_QUOTA_MARKERS = (
    "resource_exhausted",
    "individual quota reached",
    "exhausted your capacity",
    "exceeded your current quota",
    "insufficient_quota",
    "quota exhausted",
    "quota_exhausted",
    "quota exceeded",
    "quota limit reached",
    "quota limit exceeded",
)
_RATE_LIMIT_MARKERS = ("429", "rate limit", "ratelimit")
_AUTH_MARKERS = (
    "unauthorized",
    "unauthenticated",
    "authenticated",
    "authentication",
    "not logged into",
    "invalid api key",
    "invalid_api_key",
    "401",
    "token expired",
    "invalid token",
    "login required",
)
_REFRESH_MARKERS = ("refresh failed", "token refresh")
_FORBIDDEN_MARKERS = ("403", "forbidden", "permission_denied")
_UNAVAILABLE_MARKERS = ("unavailable", "503", "service unavailable")
_DISABLED_MARKERS = ("disabled",)

_HTTP_CODE_KINDS = (None, "", "http")


HEADLESS_TOOL_PERMISSION_DENIED = "HEADLESS_TOOL_PERMISSION_DENIED"
_HEADLESS_TOOL_RE = re.compile(
    r'a tool required the "([^"]+)" permission that headless mode cannot prompt for'
)


@dataclass(frozen=True)
class AgyHeadlessDenial:
    tool: str
    path: Optional[str]
    source: str

    def describe(self) -> str:
        return f"tool={self.tool} path={self.path or 'unknown'}"


# Exact argument names that carry a path. A substring match ("file" in
# "file_content", "dir" in "direction") would copy file bodies or free text
# into receipts and journals, so only these names count.
_TARGET_ARG_KEYS = frozenset({
    "path", "paths", "file", "filepath", "file_path", "dir", "directory",
    "dirpath", "dir_path", "directory_path", "target", "target_path",
    "target_file", "target_dir", "cwd", "absolutepath", "absolute_path",
    "abs_path", "source_path", "dest_path", "destination_path",
})
_TARGET_ARG_MAX_LEN = 1024


def _path_like(value: Any, *, absolute: bool) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _TARGET_ARG_MAX_LEN
        and not any(ch in value for ch in "\n\r\x00")
        and (not absolute or value.startswith("/"))
    )


def _target_arg(args: dict[str, Any], *, absolute: bool) -> Optional[str]:
    for key, value in args.items():
        if key.lower() in _TARGET_ARG_KEYS and _path_like(value, absolute=absolute):
            return value
    return None


def agy_headless_denial(
    stdout: str, stderr: str, *, stdout_is_envelope: bool
) -> Optional[AgyHeadlessDenial]:
    """Read only agy's diagnostics, never its model response prose."""
    from nexus.executors.agy_write_admission import (
        _AGY_HEADLESS_PERMISSION_DENIAL_MARKERS,
        top_level_json_objects,
    )

    match = _HEADLESS_TOOL_RE.search(stderr or "")
    denial = None
    if match or any(marker in (stderr or "") for marker in _AGY_HEADLESS_PERMISSION_DENIAL_MARKERS):
        denial = AgyHeadlessDenial(match.group(1) if match else "unknown", None, "stderr")
    if stdout_is_envelope:
        for value in top_level_json_objects(stdout or ""):
            if "conversation_id" not in value or "status" not in value:
                continue
            actions = value.get("denied_actions")
            if not isinstance(actions, list) or not actions:
                continue
            action = actions[-1] if isinstance(actions[-1], dict) else {}
            tool = action.get("action") or action.get("display_name")
            tool = tool if isinstance(tool, str) and tool else "unknown"
            return AgyHeadlessDenial(
                denial.tool if denial and denial.tool != "unknown" else tool,
                _target_arg(action, absolute=False),
                "envelope",
            )
    return denial


def last_tool_call_target(transcript_text: str) -> tuple[Optional[str], Optional[str]]:
    """Best-effort last tool call in transcript_full.jsonl, including malformed logs."""
    last: tuple[Optional[str], Optional[str]] = (None, None)
    for line in transcript_text.splitlines():
        try:
            step = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(step, dict) or not isinstance(step.get("tool_calls"), list):
            continue
        for call in step["tool_calls"]:
            if not isinstance(call, dict):
                continue
            name = call.get("name")
            args = call.get("args")
            last = (
                name if isinstance(name, str) else None,
                _target_arg(args, absolute=True) if isinstance(args, dict) else None,
            )
    return last


def format_headless_denial_reason(denial: AgyHeadlessDenial) -> str:
    return f"agy_permission_denied: {denial.describe()}"


def max_account_retirements() -> int:
    """Account-wide retirements one run may make before it calls the failure host-wide."""
    raw = os.getenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS")
    try:
        value = int(raw) if raw is not None else DEFAULT_MAX_ACCOUNT_RETIREMENTS
    except ValueError:
        value = DEFAULT_MAX_ACCOUNT_RETIREMENTS
    return max(1, value)


def is_account_global_retirement(kind: AccountFailureKind, model_family: Optional[str]) -> bool:
    """Whether retiring ``kind`` marks the whole account bad (not one model family).

    Quota exhaustion with a known model family is a family cooldown, which is
    safe to rotate through; every other account-failover kind is account-wide.
    """
    from nexus.services.external_account_pool import is_account_failover_failure

    if not is_account_failover_failure(kind):
        return False
    return not (kind is AccountFailureKind.QUOTA_EXHAUSTED and model_family)


def agy_error_payloads(stderr: str) -> list[dict[str, Any]]:
    """Every ``AGY_ERROR: {...}`` JSON object on its own stderr line."""
    found: list[dict[str, Any]] = []
    for match in _AGY_ERROR_LINE_RE.finditer(stderr or ""):
        try:
            payload = json.loads(match.group("payload"))
        except ValueError:
            continue
        if isinstance(payload, dict):
            found.append(payload)
    return found


def agy_envelope_errors(stdout: str) -> list[str]:
    """``error`` of each ``--output-format json`` result envelope whose status is ERROR.

    Only top-level objects carrying ``conversation_id`` and ``status`` count;
    the model's ``response`` string is never read.
    """
    # #2433: one top-level JSON scanner (local import: no import cycle).
    from nexus.executors.agy_write_admission import top_level_json_objects

    return [
        value["error"]
        for value in top_level_json_objects(stdout or "")
        if "conversation_id" in value
        and value.get("status") == "ERROR"
        and isinstance(value.get("error"), str)
        and value["error"].strip()
    ]


def _int_code(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _kind_from_payload(payload: dict[str, Any]) -> Optional[AccountFailureKind]:
    status = str(payload.get("status") or "").strip().upper()
    code_kind = payload.get("code_kind")
    code = _int_code(payload.get("error_code")) if code_kind in _HTTP_CODE_KINDS else None
    detail = str(payload.get("short_error") or "").lower()
    if status == "RESOURCE_EXHAUSTED" or code == 429:
        return AccountFailureKind.QUOTA_EXHAUSTED
    if status == "UNAUTHENTICATED" or code == 401:
        if "expired" in detail:
            return AccountFailureKind.TOKEN_EXPIRED
        return AccountFailureKind.AUTH_OR_SESSION_INVALID
    if status == "PERMISSION_DENIED" or code == 403:
        return AccountFailureKind.PERMISSION_OR_SCOPE_ERROR
    if status == "UNAVAILABLE" or code == 503:
        return AccountFailureKind.ACCOUNT_UNAVAILABLE
    return None


def _kind_from_agy_text(text: str) -> Optional[AccountFailureKind]:
    """The legacy keyword ladder, applied only to agy's own error text."""
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in AGY_LOGIN_PROMPT_MARKERS):
        return AccountFailureKind.AUTH_OR_SESSION_INVALID
    if any(marker in lowered for marker in _QUOTA_MARKERS):
        return AccountFailureKind.QUOTA_EXHAUSTED
    if any(marker in lowered for marker in _RATE_LIMIT_MARKERS):
        return AccountFailureKind.RATE_LIMITED
    if any(marker in lowered for marker in _AUTH_MARKERS):
        if "expired" in lowered:
            return AccountFailureKind.TOKEN_EXPIRED
        return AccountFailureKind.AUTH_OR_SESSION_INVALID
    if any(marker in lowered for marker in _REFRESH_MARKERS):
        return AccountFailureKind.TOKEN_REFRESH_FAILED
    if any(marker in lowered for marker in _FORBIDDEN_MARKERS):
        return AccountFailureKind.PERMISSION_OR_SCOPE_ERROR
    if any(marker in lowered for marker in _UNAVAILABLE_MARKERS):
        return AccountFailureKind.ACCOUNT_UNAVAILABLE
    if any(marker in lowered for marker in _DISABLED_MARKERS):
        return AccountFailureKind.ACCOUNT_DISABLED
    return None


def agy_structured_failure(
    stdout: str, stderr: str, *, stdout_is_envelope: bool
) -> tuple[bool, Optional[AccountFailureKind]]:
    """``(structured_error_present, account_kind)`` from AGY_ERROR / the envelope only.

    The last ``AGY_ERROR`` line decides (agy prints its terminal error last);
    without one, the envelope ``error`` field decides.  ``account_kind`` is
    ``None`` when the structured error is not an account failure.
    """
    payloads = agy_error_payloads(stderr)
    if payloads:
        return True, _kind_from_payload(payloads[-1])
    if stdout_is_envelope:
        errors = agy_envelope_errors(stdout)
        if errors:
            return True, _kind_from_agy_text(errors[-1])
    return False, None


def agy_stderr_account_failure(stderr: str) -> Optional[AccountFailureKind]:
    """Fallback for agy output without a structured error: agy's stderr text only."""
    return _kind_from_agy_text(stderr or "")


def classify_agy_account_failure(
    stdout: str, stderr: str, *, stdout_is_envelope: bool
) -> Optional[AccountFailureKind]:
    """The account-level failure kind of a failed agy run, or ``None``.

    Never reads model text: stdout only through the JSON envelope's ``error``
    field (and only when ``stdout_is_envelope``); stderr prose only when agy
    printed no structured error at all.
    """
    structured, kind = agy_structured_failure(stdout, stderr, stdout_is_envelope=stdout_is_envelope)
    if structured:
        return kind
    if agy_headless_denial(stdout, stderr, stdout_is_envelope=stdout_is_envelope) is not None:
        # A denial is a work failure. The stderr marker classifier below is
        # substring matching, and agy echoes the denied path next to the
        # denial (a path can contain "401" or "authentication"), so it is
        # not consulted here; a real account failure still arrives as a
        # structured AGY_ERROR or envelope error and is decided above.
        return None
    return agy_stderr_account_failure(stderr)


def agy_error_text(stdout: str, stderr: str, *, stdout_is_envelope: bool) -> str:
    """agy's own error text (AGY_ERROR short errors, envelope errors, stderr), no model reply."""
    parts = [str(payload.get("short_error") or "") for payload in agy_error_payloads(stderr)]
    if stdout_is_envelope:
        parts.extend(agy_envelope_errors(stdout))
    parts.append(stderr or "")
    return "\n".join(part for part in parts if part)


def agy_login_required(stdout: str, stderr: str, *, stdout_is_envelope: bool) -> bool:
    """agy printed its interactive OAuth login prompt (or failed it), per agy's own text."""
    text = agy_error_text(stdout, stderr, stdout_is_envelope=stdout_is_envelope)
    return any(marker in text for marker in AGY_LOGIN_PROMPT_MARKERS)
