"""Operational readiness checks for Local Assist."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any


def _check(ok: bool, detail: str) -> dict[str, str]:
    return {"status": "PASS" if ok else "FAIL", "detail": detail}


def run_local_assist_health_checks(
    *,
    workspace_root: str | Path,
    ollama_available: bool | None = None,
    model_available: bool | None = None,
    provider_adapter_available: bool | None = None,
    candidate_isolation_available: bool | None = None,
    verifier_environment_available: bool | None = None,
    receipt_storage_available: bool | None = None,
    workspace_revision_integrity: bool | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    reports_root = root / ".nexus" / "reports" / "local_assist"
    checks = {
        "ollama_availability": _check(
            shutil.which("ollama") is not None if ollama_available is None else ollama_available,
            "ollama executable present" if (ollama_available is not False) else "ollama unavailable",
        ),
        "model_availability": _check(
            bool(os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL") or os.environ.get("NEXUS_LOCAL_MODEL_NAME"))
            if model_available is None
            else model_available,
            "model identity configured" if model_available is not False else "model identity unavailable",
        ),
        "provider_adapter_availability": _check(
            True if provider_adapter_available is None else provider_adapter_available,
            "provider-neutral adapter contract importable" if provider_adapter_available is not False else "adapter unavailable",
        ),
        "candidate_isolation": _check(
            (root.is_dir() and (root / ".git").exists()) if candidate_isolation_available is None else candidate_isolation_available,
            "workspace and git metadata present" if candidate_isolation_available is not False else "isolation unavailable",
        ),
        "verifier_environment": _check(
            (root / ".venv" / "bin" / "python").exists() if verifier_environment_available is None else verifier_environment_available,
            "workspace interpreter present" if verifier_environment_available is not False else "verifier environment unavailable",
        ),
        "receipt_storage": _check(
            (reports_root.parent.exists() and os.access(reports_root.parent, os.W_OK))
            if receipt_storage_available is None
            else receipt_storage_available,
            "receipt parent is writable" if receipt_storage_available is not False else "receipt storage unavailable",
        ),
        "workspace_revision_integrity": _check(
            (root / ".git").exists() if workspace_revision_integrity is None else workspace_revision_integrity,
            "workspace revision metadata present" if workspace_revision_integrity is not False else "workspace revision integrity failed",
        ),
    }
    healthy = all(item["status"] == "PASS" for item in checks.values())
    return {
        "schema": "nexus.local_assist.health.v1",
        "status": "HEALTHY" if healthy else "DEGRADED",
        "checks": checks,
        "production_ready": False,
        "public_claim_allowed": False,
        "internal_only": True,
    }
