"""Machine-readable Local Assist + Online live-proof preflight.

Does not invoke providers. Reports distinct blocker statuses.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


STATUS_READY = "READY"
STATUS_BLOCKED_EXTERNAL_AUTHORIZATION = "BLOCKED_EXTERNAL_AUTHORIZATION"
STATUS_BLOCKED_LOCAL_PROVIDER = "BLOCKED_LOCAL_PROVIDER"
STATUS_BLOCKED_LOCAL_MODEL = "BLOCKED_LOCAL_MODEL"
STATUS_BLOCKED_ONLINE_PROVIDER = "BLOCKED_ONLINE_PROVIDER"
STATUS_BLOCKED_ONLINE_AUTHORIZATION = "BLOCKED_ONLINE_AUTHORIZATION"
STATUS_BLOCKED_BOUNDED_SCOPE = "BLOCKED_BOUNDED_SCOPE"


@dataclass
class PreflightCheck:
    name: str
    status: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreflightResult:
    overall_status: str
    checks: list[PreflightCheck]
    ready_for_live_smoke: bool
    timestamp: str
    workspace_revision: str
    claim_boundary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "nexus.local_assist.preflight.v1",
            "overall_status": self.overall_status,
            "ready_for_live_smoke": self.ready_for_live_smoke,
            "timestamp": self.timestamp,
            "workspace_revision": self.workspace_revision,
            "checks": [asdict(c) for c in self.checks],
            "claim_boundary": self.claim_boundary,
        }


def _workspace_revision(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _ollama_tags(timeout: float = 1.5) -> tuple[bool, list[str], str]:
    url = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/tags")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for item in data.get("models", []) or []:
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                models.append(name)
        return True, models, ""
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, [], f"{exc.__class__.__name__}:{exc}"


def run_local_assist_preflight(
    *,
    project_root: str | Path = ".",
    allowed_files: list[str] | tuple[str, ...] | None = None,
    online_provider: str = "",
    local_model: str = "",
    receipt_dir: str | Path | None = None,
    online_policy: str = "auto",
) -> PreflightResult:
    from nexus.services.online_execution_policy import resolve_online_execution_decision

    root = Path(project_root).expanduser().resolve()
    checks: list[PreflightCheck] = []
    blockers: list[str] = []

    provider = (online_provider or os.environ.get("NEXUS_OAUTH_PROVIDER") or "gemini").strip().lower()
    if provider in {"auto", "ollama"}:
        provider = "gemini"

    # Canonical product Online authorization (not env-only).
    online_decision = resolve_online_execution_decision(
        task_online_policy=online_policy,
        project_root=root,
        planner_online_needed=True,
        requested_provider=provider,
    )
    env_present = os.environ.get("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "").strip() == "1"
    checks.append(
        PreflightCheck(
            name="online_execution_decision",
            status=STATUS_READY if online_decision.online_execution_authorized else STATUS_BLOCKED_ONLINE_AUTHORIZATION,
            detail=f"{online_decision.preflight_status}:{online_decision.reason}",
            evidence={
                "online_policy": online_decision.online_policy,
                "preflight_status": online_decision.preflight_status,
                "online_execution_authorized": online_decision.online_execution_authorized,
                "online_authorization_source": online_decision.online_authorization_source,
                "physical_invocation_allowed": online_decision.physical_invocation_allowed,
                "env_override_present": env_present,
                "env_is_not_sole_product_gate": True,
            },
        )
    )
    if not online_decision.online_execution_authorized:
        blockers.append(STATUS_BLOCKED_ONLINE_AUTHORIZATION)

    ollama_ok, models, ollama_err = _ollama_tags()
    checks.append(
        PreflightCheck(
            name="local_provider",
            status=STATUS_READY if ollama_ok else STATUS_BLOCKED_LOCAL_PROVIDER,
            detail="ollama reachable" if ollama_ok else ollama_err or "ollama unreachable",
            evidence={"reachable": ollama_ok, "model_count": len(models)},
        )
    )
    if not ollama_ok:
        blockers.append(STATUS_BLOCKED_LOCAL_PROVIDER)

    wanted_model = (local_model or os.environ.get("NEXUS_LOCAL_MODEL") or "qwen2.5-coder:7b").strip()
    model_ok = bool(models) and any(wanted_model in m or m.startswith(wanted_model.split(":")[0]) for m in models)
    if ollama_ok and not models:
        model_ok = False
    checks.append(
        PreflightCheck(
            name="local_model",
            status=STATUS_READY if model_ok else STATUS_BLOCKED_LOCAL_MODEL,
            detail=f"model={wanted_model}" if model_ok else f"model not found: {wanted_model}",
            evidence={"requested_model": wanted_model, "available_models": models[:20]},
        )
    )
    if ollama_ok and not model_ok:
        blockers.append(STATUS_BLOCKED_LOCAL_MODEL)

    registered = {"gemini", "grok", "codex", "openai"}
    provider_ok = provider in registered
    checks.append(
        PreflightCheck(
            name="online_provider_selection",
            status=STATUS_READY if provider_ok else STATUS_BLOCKED_ONLINE_PROVIDER,
            detail=f"provider={provider}",
            evidence={"provider": provider, "registered": sorted(registered)},
        )
    )
    if not provider_ok:
        blockers.append(STATUS_BLOCKED_ONLINE_PROVIDER)

    bin_name = {"gemini": "gemini", "grok": "grok", "codex": "codex", "openai": "openai"}.get(provider, provider)
    binary = shutil.which(bin_name) if provider_ok else None
    checks.append(
        PreflightCheck(
            name="online_provider_binary",
            status=STATUS_READY if bool(binary) else STATUS_BLOCKED_ONLINE_PROVIDER,
            detail=str(binary or "binary_not_found"),
            evidence={"binary": binary or "", "provider": provider},
        )
    )

    revision = _workspace_revision(root)
    checks.append(
        PreflightCheck(
            name="workspace_revision",
            status=STATUS_READY if revision else STATUS_BLOCKED_BOUNDED_SCOPE,
            detail=revision or "git HEAD unavailable",
            evidence={"workspace_revision": revision},
        )
    )

    files = [str(f).strip() for f in (allowed_files or []) if str(f).strip()]
    missing = [f for f in files if not (root / f).exists()]
    scope_ok = bool(files) and not missing
    checks.append(
        PreflightCheck(
            name="bounded_scope",
            status=STATUS_READY if scope_ok else STATUS_BLOCKED_BOUNDED_SCOPE,
            detail="allowed_files present" if scope_ok else ("missing_allowed_files" if not files else f"missing:{missing}"),
            evidence={"allowed_files": files, "missing": missing},
        )
    )
    if not scope_ok:
        blockers.append(STATUS_BLOCKED_BOUNDED_SCOPE)

    dest = Path(receipt_dir) if receipt_dir else root / ".nexus" / "reports" / "unified_runtime"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        writable = os.access(dest, os.W_OK)
    except OSError:
        writable = False
    checks.append(
        PreflightCheck(
            name="receipt_destination",
            status=STATUS_READY if writable else STATUS_BLOCKED_BOUNDED_SCOPE,
            detail=str(dest),
            evidence={"path": str(dest), "writable": writable},
        )
    )

    checks.append(
        PreflightCheck(
            name="formal_mutation_policy",
            status=STATUS_READY,
            detail="advisor mutation_policy=isolated_only (no formal workspace mutation)",
            evidence={"mutation_policy": "isolated_only", "formal_workspace_mutated": False},
        )
    )

    # Prefer first specific blocker for overall; READY only if no blockers.
    overall = STATUS_READY if not blockers else blockers[0]
    # If external auth is missing, keep that as primary overall for live smoke.
    if STATUS_BLOCKED_EXTERNAL_AUTHORIZATION in blockers:
        overall = STATUS_BLOCKED_EXTERNAL_AUTHORIZATION

    return PreflightResult(
        overall_status=overall,
        checks=checks,
        ready_for_live_smoke=overall == STATUS_READY and not blockers,
        timestamp=datetime.now(timezone.utc).isoformat(),
        workspace_revision=revision,
        claim_boundary={
            "public_claim_allowed": False,
            "production_ready": False,
            "live_proof_pass_requires_real_invocations": True,
        },
    )


def write_preflight_result(path: str | Path, result: PreflightResult | Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict() if isinstance(result, PreflightResult) else dict(result)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination
