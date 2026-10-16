"""Read-only executor self-check for the live Gateway (PR-5e).

Bootstraps the host exactly as the Gateway does (importing
``nexus.services.runtime_compat`` registers the host executor resolver with the
runtime seam ``nexus_runtime.support.services.executor_binding``), then asks the
seam, for every planner capability, whether a physical executor resolves.  A
resolver that raises is reported as ``error`` with its reason, never as missing.

Usage (in the Gateway's own venv, from its source tree)::

    python -m nexus.services.runtime_compat --check-executors [--json]
    python -m nexus.services.executor_self_check [--json] [--require NAME ...]

Exit 0 only when the seam has a resolver and every required capability (the
governance gates plus the seam capabilities by default) resolves; 1 when one
does not; 2 when the bootstrap itself fails.  Nothing is written anywhere.
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
_UNSAFE_CHARS = re.compile(r"[^\x20-\x7e]")


def _sanitize_resolution_text(value: Any, limit: int = 200) -> str:
    text = _UNSAFE_CHARS.sub("?", str(value))
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."


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
EXIT_REQUIRED_UNRESOLVED = 1
EXIT_BOOTSTRAP_FAILED = 2


def _error_reason(name: str, key: str, exc: BaseException, origin: str) -> dict[str, str]:
    return {
        "capability": _sanitize_resolution_text(name, 120),
        "registry_key": _sanitize_resolution_text(key, 120),
        "error_type": _sanitize_resolution_text(type(exc).__qualname__, 120),
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

    binding: Any | None
    try:
        binding = importlib.import_module(BINDING_MODULE)
        registry: Any = importlib.import_module(RUNTIME_REGISTRY_MODULE)
    except ImportError:
        binding, registry = None, None
    resolver_registered = (
        getattr(binding, "_resolver", None) is not None if binding is not None else None
    )
    origin, resolve, key_of, names = _seam(binding, registry)

    rows: list[dict[str, Any]] = []
    for name in sorted(set(names) | set(required)):
        key = str(key_of(name))
        row: dict[str, Any] = {"capability": name, "registry_key": key}
        try:
            executor = resolve(key)
        except Exception as exc:
            row["status"] = EXECUTOR_RESOLUTION_ERROR
            row["error"] = _error_reason(name, key, exc, origin)
        else:
            if executor is None:
                row["status"] = EXECUTOR_RESOLUTION_MISSING
            else:
                row["status"] = EXECUTOR_RESOLUTION_RESOLVED
                row["executor"] = _sanitize_resolution_text(
                    getattr(executor, "__qualname__", None) or type(executor).__qualname__
                )
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
    ok = resolver_registered is not False and not unresolved_required
    import nexus

    report.update(
        ok=ok,
        exit_code=EXIT_OK if ok else EXIT_REQUIRED_UNRESOLVED,
        resolver_origin=origin,
        resolver_registered=resolver_registered,
        nexus_package=str(getattr(nexus, "__file__", "") or ""),
        nexus_runtime_commit=_runtime_commit(),
        capability_count=len(rows),
        status_counts=counts,
        unresolved_required=unresolved_required,
        recorded_resolution_errors=_recorded_resolution_errors(),
        capabilities=rows,
    )
    return report


def _render_text(report: dict[str, Any]) -> str:
    if "bootstrap_error" in report:
        err = report["bootstrap_error"]
        return f"BOOTSTRAP_FAILED {err['error_type']}: {err['error_message']}"
    lines = [
        f"ok={report['ok']} resolver_registered={report['resolver_registered']}"
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
    if report["unresolved_required"]:
        lines.append("unresolved_required=" + ",".join(report["unresolved_required"]))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="executor_self_check", description="Read-only executor self-check for the live Gateway."
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
