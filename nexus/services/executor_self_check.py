"""Read-only executor self-check for the live Gateway (PR-5e).

Bootstraps the host exactly as the Gateway does (importing
``nexus.services.runtime_compat`` registers the host executor resolver with the
runtime seam ``nexus_runtime.support.services.executor_binding``), then asks the
seam, for every planner capability, whether a physical executor resolves.  A
resolver that raises is reported as ``error`` with its reason, never as missing.

Usage (in the Gateway's own venv, from its source tree)::

    python -m nexus.services.runtime_compat --check-executors [--json]
    python -m nexus.services.executor_self_check [--json] [--require NAME ...]

Exit codes:

* 0 -- the runtime seam is importable, a resolver is registered with it, no
  capability's resolver raised, and every required capability (the governance
  gates plus the seam capabilities by default) resolves.
* 1 -- the check failed: seam missing (runtime predates it), no resolver
  registered, any capability (required or not) whose resolver raised, or a
  required capability that is missing.  ``failures`` lists each reason.
* 2 -- the bootstrap or the self-check itself failed (``bootstrap_error`` /
  ``internal_error`` carry a one-line reason).

Error text is sanitized (printable ASCII, credentials and token-like blobs
redacted, truncated).  Nothing is written anywhere.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from collections.abc import Callable, Sequence
from typing import Any

# Self-contained on purpose: the module can be copied next to an older live
# checkout and run against it, so it does not import PR-5e registry helpers.
EXECUTOR_RESOLUTION_RESOLVED = "resolved"
EXECUTOR_RESOLUTION_MISSING = "missing"
EXECUTOR_RESOLUTION_ERROR = "error"
# --- resolution-text sanitizer (keep identical in capability_registry.py and
# executor_self_check.py; the self-check stays self-contained) ---
#
# The text kept is "exception type + redacted gist".  The raw text is capped
# before any scan, split once on whitespace, quotes, brackets, commas,
# semicolons and backslashes, and each token is judged on its own with
# anchored, bounded patterns (linear time).  Credentials after a sensitive key,
# auth schemes, known token prefixes, URL userinfo, PEM bodies and long
# base64/hex-like tokens become ``[REDACTED]``; a long path or SHA can be
# redacted too, which is accepted.  URLs are split on ``/ ? & #`` and every
# piece goes through the same rules.  A token cut by the raw cap is dropped.
# Then control characters are replaced, CI workflow commands neutralised, and
# the result truncated.  Identifier fields (exception type, capability name,
# registry key, executor qualname) use ``_sanitize_identifier`` instead: no
# secret rules, so ``OAuth2AuthenticationError`` stays readable.
_RESOLUTION_RAW_MAX = 2000
_RESOLUTION_TEXT_MAX = 200
_RESOLUTION_REDACTED = "[REDACTED]"
_RESOLUTION_UNSAFE_CHARS = re.compile(r"[^\x20-\x7e]")
_RESOLUTION_SPLIT = re.compile(r"(\s+|[\"'{}\[\](),;<>\\])")
_RESOLUTION_SEPARATOR = re.compile(r"\s+|[\"'{}\[\](),;<>\\]")
_RESOLUTION_URL_SPLIT = re.compile(r"([/?&#])")
_RESOLUTION_SENSITIVE_KEY = re.compile(
    r"(?i)token|secret|passw(?:or)?d|api[_-]?key|access[_-]?key|private[_-]?key"
    r"|authorization|bearer|cookie|credential"
)
_RESOLUTION_AUTH_SCHEMES = frozenset({"bearer", "basic"})
_RESOLUTION_TOKEN_PREFIX = re.compile(
    r"(?:gh[pousr]_|github_pat_|sk-|sk_live_|rk_live_|xox[abprs]-|ya29\.|AIza|eyJ)"
)
_RESOLUTION_AWS_KEY = re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")
_RESOLUTION_BLOB = re.compile(r"[A-Za-z0-9+/_=-]{20,}")
_RESOLUTION_HEX = re.compile(r"[0-9a-fA-F]{32,}")


def _resolution_secret_value(value: str) -> bool:
    if not value:
        return False
    if _RESOLUTION_TOKEN_PREFIX.match(value) or _RESOLUTION_AWS_KEY.search(value):
        return True
    if _RESOLUTION_HEX.fullmatch(value):
        return True
    return (
        _RESOLUTION_BLOB.fullmatch(value) is not None
        and any(c.isalpha() for c in value)
        and any(c.isdigit() for c in value)
    )


def _resolution_sensitive_key(key: str) -> bool:
    return bool(key) and _RESOLUTION_SENSITIVE_KEY.search(key) is not None


def _redact_resolution_token(token: str) -> tuple[str, int, bool]:
    """(replacement, values to redact after it, bare sensitive key seen)."""
    scheme_end = token.find("://")
    if scheme_end > 0:
        start = scheme_end + 3
        at = token.find("@", start)
        slash = token.find("/", start)
        rest = token[start:]
        if at > start and (slash == -1 or at < slash):
            rest = _RESOLUTION_REDACTED + token[at:]
        pieces = _RESOLUTION_URL_SPLIT.split(rest)
        cleaned = [
            piece
            if not piece or piece in "/?&#" or piece.startswith(_RESOLUTION_REDACTED)
            else _redact_resolution_token(piece)[0]
            for piece in pieces
        ]
        return token[:start] + "".join(cleaned), 0, False
    if _resolution_secret_value(token) and not _resolution_sensitive_key(token):
        return _RESOLUTION_REDACTED, 0, False
    seps = [i for i in (token.find("="), token.find(":")) if i > 0]
    if seps:
        cut = min(seps)
        key, sep, value = token[:cut], token[cut], token[cut + 1 :].lstrip("=:")
        if _resolution_sensitive_key(key):
            if value:
                return f"{key}{sep}{_RESOLUTION_REDACTED}", 0, False
            return token, 1, False
        if _resolution_secret_value(value):
            return f"{key}{sep}{_RESOLUTION_REDACTED}", 0, False
        return token, 0, False
    if token.lower() in _RESOLUTION_AUTH_SCHEMES:
        return token, 1, False
    if _resolution_secret_value(token):
        return _RESOLUTION_REDACTED, 0, False
    return token, 0, _resolution_sensitive_key(token)


def _redact_resolution_secrets(text: str) -> str:
    """Replace credentials and token-like values with ``[REDACTED]`` (linear time)."""
    pem = text.find("-----BEGIN")
    if pem >= 0:
        text = text[:pem] + _RESOLUTION_REDACTED
    out: list[str] = []
    pending = 0
    scheme_extended = False
    bare_key = False
    quote = ""
    for part in _RESOLUTION_SPLIT.split(text):
        if not part:
            continue
        if _RESOLUTION_SEPARATOR.fullmatch(part):
            if quote:
                if part == quote:
                    quote = ""
                    pending -= 1
                out.append(part)
                continue
            if pending and part in ("'", '"'):
                quote = part
            out.append(part)
            continue
        if quote:
            out.append(_RESOLUTION_REDACTED)
            continue
        if pending:
            if part in (":", "="):
                out.append(part)
                continue
            out.append(_RESOLUTION_REDACTED)
            if part.lower() in _RESOLUTION_AUTH_SCHEMES and not scheme_extended:
                scheme_extended = True
            else:
                pending -= 1
            continue
        if bare_key:
            bare_key = False
            if part in (":", "="):
                pending, scheme_extended = 1, False
                out.append(part)
                continue
        replacement, pending, bare_key = _redact_resolution_token(part)
        scheme_extended = part.lower() in _RESOLUTION_AUTH_SCHEMES
        out.append(replacement)
    return "".join(out)


def _resolution_ci_safe(text: str, limit: int) -> str:
    text = _RESOLUTION_UNSAFE_CHARS.sub("?", text)
    # Neutralise CI workflow commands (``::error::``, ``::add-mask::``, ``##[group]``).
    text = text.replace("::", ": :").replace("##[", "# #[")
    if len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text


def _sanitize_resolution_text(value: Any, limit: int = _RESOLUTION_TEXT_MAX) -> str:
    """Redacted gist: raw cap, per-token redaction, printable ASCII, CI-safe, truncated."""
    raw = str(value)
    if len(raw) > _RESOLUTION_RAW_MAX:
        raw = raw[:_RESOLUTION_RAW_MAX]
        # Drop the token the cap cut through: its remainder could escape every rule.
        cut = max((m.end() for m in _RESOLUTION_SEPARATOR.finditer(raw)), default=0)
        raw = raw[:cut] + "..."
    return _resolution_ci_safe(_redact_resolution_secrets(raw), limit)


def _sanitize_identifier(value: Any, limit: int = 120) -> str:
    """Identifier fields: printable ASCII, CI-safe, bounded; never secret-redacted."""
    return _resolution_ci_safe(str(value)[:_RESOLUTION_RAW_MAX], limit)


# --- end resolution-text sanitizer ---


def _recorded_resolution_errors() -> dict[str, Any] | None:
    """The host's recorded resolver errors, or None when the host predates PR-5e."""
    host = sys.modules.get("nexus.services.capability_registry")
    getter = getattr(host, "last_executor_resolution_errors", None)
    if not callable(getter):
        return None
    errors = getter()
    return dict(errors) if isinstance(errors, dict) else None


SCHEMA = "nexus.executor_self_check.v1"
BOOTSTRAP_MODULE = "nexus.services.runtime_compat"
BINDING_MODULE = "nexus_runtime.support.services.executor_binding"
RUNTIME_REGISTRY_MODULE = "nexus_runtime.support.services.capability_registry"
HOST_REGISTRY_MODULE = "nexus.services.capability_registry"

# Governance gates with a physical executor.  delivery_gate is evaluated by the
# postflight evaluator (online_nexus_context), not by an executor, so it is
# reported but not required.
GOVERNANCE_GATES: tuple[str, ...] = (
    "pregate",
    "harness_preflight_sensor",
    "plan_quality_gate",
    "mempalace_gate",
    "artifact_gate",
    "claim_gate",
)
SEAM_CAPABILITIES: tuple[str, ...] = ("sandbox", "ultra_review", "file_lock")
DEFAULT_REQUIRED: tuple[str, ...] = GOVERNANCE_GATES + SEAM_CAPABILITIES

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_REQUIRED_UNRESOLVED = EXIT_CHECK_FAILED  # kept name
EXIT_BOOTSTRAP_FAILED = 2
EXIT_INTERNAL_FAILED = 2
SELF_CHECK_ORIGIN = "nexus.services.executor_self_check"


def _error_reason(name: str, key: str, exc: BaseException, origin: str) -> dict[str, str]:
    return {
        "capability": _sanitize_identifier(name),
        "registry_key": _sanitize_identifier(key),
        "error_type": _sanitize_identifier(type(exc).__qualname__),
        "error_message": _sanitize_resolution_text(exc),
        "resolver_origin": origin,
    }


def _runtime_commit() -> str:
    try:
        from importlib.metadata import distribution

        raw = distribution("nexus-runtime").read_text("direct_url.json") or ""
        info = json.loads(raw) if raw else {}
        return str((info.get("vcs_info") or {}).get("commit_id") or "")
    except Exception:
        return ""


def _seam(
    binding: Any | None, registry: Any
) -> tuple[str, Callable[[str], Any], Callable[[str], str], Sequence[str]]:
    """(origin, resolve(key), key_of(name), names) for the live path, else the host path."""
    if binding is not None:
        names = tuple(registry.list_planner_capability_names())
        return (
            BINDING_MODULE,
            binding.resolve_executor,
            registry._resolve_executor_registry_key,
            names,
        )
    host = importlib.import_module(HOST_REGISTRY_MODULE)
    from nexus.core.capability_executor_registry import get_executor

    return (
        "nexus.core.capability_executor_registry.get_executor",
        get_executor,
        host._resolve_executor_registry_key,
        tuple(host.list_planner_capability_names()),
    )


def collect(required: Sequence[str] = DEFAULT_REQUIRED) -> dict[str, Any]:
    """Resolve every planner capability through the seam the Gateway uses; read-only."""
    report: dict[str, Any] = {"schema": SCHEMA, "required": list(required)}
    try:
        importlib.import_module(BOOTSTRAP_MODULE)
    except Exception as exc:
        report.update(
            ok=False,
            exit_code=EXIT_BOOTSTRAP_FAILED,
            bootstrap_error=_error_reason(BOOTSTRAP_MODULE, "", exc, BOOTSTRAP_MODULE),
        )
        return report
    try:
        _resolve_all(report, required)
    except Exception as exc:
        # Listing names or mapping keys failed: an internal failure, not "unresolved".
        report.update(
            ok=False,
            exit_code=EXIT_INTERNAL_FAILED,
            internal_error=_error_reason(SELF_CHECK_ORIGIN, "", exc, SELF_CHECK_ORIGIN),
        )
    return report


def _resolve_all(report: dict[str, Any], required: Sequence[str]) -> None:
    binding: Any | None
    try:
        binding = importlib.import_module(BINDING_MODULE)
        registry: Any = importlib.import_module(RUNTIME_REGISTRY_MODULE)
    except ImportError:
        binding, registry = None, None
    seam_available = binding is not None
    resolver_registered = seam_available and getattr(binding, "_resolver", None) is not None
    origin, resolve, key_of, names = _seam(binding, registry)

    rows: list[dict[str, Any]] = []
    for name in sorted(set(names) | set(required)):
        key = str(key_of(name))
        row: dict[str, Any] = {"capability": name, "registry_key": key}
        try:
            executor = resolve(key)
            executor_name = (
                None
                if executor is None
                else _sanitize_identifier(
                    getattr(executor, "__qualname__", None) or type(executor).__qualname__, 200
                )
            )
        except Exception as exc:
            row["status"] = EXECUTOR_RESOLUTION_ERROR
            row["error"] = _error_reason(name, key, exc, origin)
        else:
            if executor is None:
                row["status"] = EXECUTOR_RESOLUTION_MISSING
            else:
                row["status"] = EXECUTOR_RESOLUTION_RESOLVED
                row["executor"] = executor_name
        row["planner_node"] = name in names
        row["required"] = name in required
        rows.append(row)

    counts = {
        status: sum(1 for row in rows if row["status"] == status)
        for status in (
            EXECUTOR_RESOLUTION_RESOLVED,
            EXECUTOR_RESOLUTION_MISSING,
            EXECUTOR_RESOLUTION_ERROR,
        )
    }
    unresolved_required = [
        row["capability"]
        for row in rows
        if row["required"] and row["status"] != EXECUTOR_RESOLUTION_RESOLVED
    ]
    error_capabilities = [
        row["capability"] for row in rows if row["status"] == EXECUTOR_RESOLUTION_ERROR
    ]
    failures: list[str] = []
    if not seam_available:
        failures.append(
            f"runtime executor seam unavailable ({BINDING_MODULE} not importable);"
            " rows come from the host registry for reference only"
        )
    elif not resolver_registered:
        failures.append("no resolver registered with the runtime executor seam")
    if error_capabilities:
        failures.append("resolver raised for: " + ",".join(error_capabilities))
    if unresolved_required:
        failures.append("required capabilities unresolved: " + ",".join(unresolved_required))
    ok = not failures
    import nexus

    report.update(
        ok=ok,
        exit_code=EXIT_OK if ok else EXIT_CHECK_FAILED,
        failures=failures,
        resolver_origin=origin,
        seam_available=seam_available,
        resolver_registered=resolver_registered,
        nexus_package=str(getattr(nexus, "__file__", "") or ""),
        nexus_runtime_commit=_runtime_commit(),
        capability_count=len(rows),
        status_counts=counts,
        unresolved_required=unresolved_required,
        error_capabilities=error_capabilities,
        recorded_resolution_errors=_recorded_resolution_errors(),
        capabilities=rows,
    )


TEXT_LINE_PREFIX = "executor-self-check| "


def _render_text(report: dict[str, Any]) -> str:
    """Every line starts with ``TEXT_LINE_PREFIX`` so no value can begin a CI command line."""
    return "\n".join(TEXT_LINE_PREFIX + line for line in _text_lines(report))


def _text_lines(report: dict[str, Any]) -> list[str]:
    for failure_key, label in (
        ("bootstrap_error", "BOOTSTRAP_FAILED"),
        ("internal_error", "INTERNAL_FAILED"),
    ):
        if failure_key in report:
            err = report[failure_key]
            return [f"{label} {err['error_type']}: {err['error_message']}"]
    lines = [
        f"ok={report['ok']} seam_available={report['seam_available']}"
        f" resolver_registered={report['resolver_registered']}"
        f" origin={report['resolver_origin']}",
        f"nexus_runtime_commit={report['nexus_runtime_commit'] or 'unknown'}"
        f" nexus_package={report['nexus_package']}",
        "counts "
        + " ".join(f"{k}={v}" for k, v in report["status_counts"].items())
        + f" total={report['capability_count']}",
    ]
    for row in report["capabilities"]:
        if row["status"] == EXECUTOR_RESOLUTION_RESOLVED and not row["required"]:
            continue
        mark = "REQUIRED " if row["required"] else ""
        detail = ""
        if row["status"] == EXECUTOR_RESOLUTION_ERROR:
            detail = f" {row['error']['error_type']}: {row['error']['error_message']}"
        lines.append(
            f"  {mark}{row['capability']} ({row['registry_key']}): {row['status']}{detail}"
        )
    lines.extend(f"FAIL: {failure}" for failure in report["failures"])
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="executor_self_check",
        description="Read-only executor self-check for the live Gateway.",
    )
    parser.add_argument(
        "--check-executors", action="store_true", help="accepted for runtime_compat"
    )
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument(
        "--require",
        action="append",
        metavar="NAME",
        help="required capability (repeatable; replaces the default gates + seam set)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    required = tuple(args.require) if args.require else DEFAULT_REQUIRED
    report = collect(required)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render_text(report))
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
