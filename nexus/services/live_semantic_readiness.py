"""Live semantic readiness probe (fail-closed; never sets auth flags).

Reports lane-specific readiness without mutating process env.
Never derives live semantic complete from binary-exists alone.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Mapping


REQUIRED_FLAGS = (
    "NEXUS_LOCAL_MODEL_CALL_ALLOWED",
    "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED",
    "NEXUS_USE_COMMITTEE",
    "NEXUS_MSA_ENABLED",
    "NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR",
)

LOCAL_FLAGS = ("NEXUS_LOCAL_MODEL_CALL_ALLOWED",)
EXTERNAL_FLAGS = (
    "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED",
    "NEXUS_USE_COMMITTEE",
    "NEXUS_MSA_ENABLED",
    "NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR",
)

SIDE_EFFECT_CAPS = (
    "integration_manager",
    "registry_sync",
    "external_doc_scout",
    "ui_validator",
    "swarm",
    "multi_agent",
)

STATUS_WAITING = "WAITING_AUTHORIZATION"
STATUS_PROVIDER = "PROVIDER_UNAVAILABLE"
STATUS_READY_PROBE = "READY_FOR_LIVE_PROBE"
STATUS_VERIFIED = "LIVE_VERIFIED"


def _flag_set(name: str, env_map: Mapping[str, str] | None = None) -> bool:
    """Read flag from env_map when provided; otherwise process env. Never mutates."""
    if env_map is not None:
        return str(env_map.get(name, "")).strip() == "1"
    return os.environ.get(name, "").strip() == "1"


def _ollama_status() -> dict[str, Any]:
    binary = shutil.which("ollama") or ""
    if not binary:
        return {
            "binary": False,
            "server_up": False,
            "model_identity": "",
            "error": "ollama_binary_missing",
        }
    try:
        proc = subprocess.run(
            [binary, "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "ollama_list_failed")[:200]
            return {
                "binary": True,
                "server_up": False,
                "model_identity": "",
                "path": binary,
                "error": err,
            }
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        # Skip header row if present
        models = []
        for ln in lines[1:] if lines and lines[0].lower().startswith("name") else lines:
            name = ln.split()[0] if ln.split() else ""
            if name and name.lower() != "name":
                models.append(name)
        identity = models[0] if models else ""
        return {
            "binary": True,
            "server_up": True,
            "model_identity": identity,
            "models": models[:10],
            "path": binary,
            "error": "" if identity else "ollama_no_model_listed",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "binary": True,
            "server_up": False,
            "model_identity": "",
            "path": binary,
            "error": str(exc)[:200],
        }


def _agy_status() -> dict[str, Any]:
    binary = shutil.which("agy") or ""
    if not binary:
        return {
            "binary": False,
            "path": "",
            "authenticated": False,
            "probe_ok": False,
            "error": "agy_binary_missing",
        }
    # Binary exists ≠ ready: require a cheap non-mutating probe
    probe_ok = False
    authenticated = False
    err = ""
    try:
        proc = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        probe_ok = proc.returncode == 0 or "usage" in out.lower() or "agy" in out.lower()
        # Auth probe: look for env/session markers without calling remote models
        # Fail closed: do not claim authenticated without explicit evidence
        if os.environ.get("AGY_AUTHENTICATED", "").strip() == "1":
            authenticated = True
        elif "login" in out.lower() and proc.returncode != 0:
            authenticated = False
            err = "agy_login_required"
        else:
            # help succeeded → binary usable, still not authenticated by default
            authenticated = False
            if not err:
                err = "agy_auth_not_proven"
    except Exception as exc:  # noqa: BLE001
        err = str(exc)[:200]
        probe_ok = False
    return {
        "binary": True,
        "path": binary,
        "authenticated": authenticated,
        "probe_ok": probe_ok,
        "error": err if not (probe_ok and authenticated) else "",
    }


def _lane_status(
    *,
    flags_ok: bool,
    provider_ok: bool,
    verified: bool = False,
) -> str:
    if verified and flags_ok and provider_ok:
        return STATUS_VERIFIED
    if not flags_ok:
        return STATUS_WAITING
    if not provider_ok:
        return STATUS_PROVIDER
    return STATUS_READY_PROBE


def probe_live_semantic_readiness(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a JSON-safe readiness receipt without mutating process env.

    When ``env`` is provided, flag checks use that mapping only (no os.environ write).
    """
    # Snapshot process env once for flag defaults when env is None
    flag_state = {name: _flag_set(name, env) for name in REQUIRED_FLAGS}
    missing_flags = [n for n, ok in flag_state.items() if not ok]

    ollama = _ollama_status()
    agy = _agy_status()

    local_flags_ok = all(flag_state[f] for f in LOCAL_FLAGS)
    external_flags_ok = all(flag_state[f] for f in EXTERNAL_FLAGS)

    local_provider_ok = bool(ollama.get("server_up") and ollama.get("model_identity"))
    online_provider_ok = bool(agy.get("binary") and agy.get("probe_ok") and agy.get("authenticated"))

    local_status = _lane_status(flags_ok=local_flags_ok, provider_ok=local_provider_ok)
    online_status = _lane_status(flags_ok=external_flags_ok, provider_ok=online_provider_ok)

    blockers: list[str] = []
    if missing_flags:
        blockers.append("missing_auth_flags:" + ",".join(missing_flags))
    if not ollama.get("server_up"):
        blockers.append("ollama_server_down")
    elif not ollama.get("model_identity"):
        blockers.append("ollama_model_identity_missing")
    if not agy.get("binary"):
        blockers.append("agy_binary_missing")
    elif not agy.get("probe_ok"):
        blockers.append("agy_probe_failed")
    elif not agy.get("authenticated"):
        blockers.append("agy_auth_not_proven")

    # Overall status: worst-lane wins among waiting/provider; never LIVE_VERIFIED here
    if not local_flags_ok or not external_flags_ok:
        overall = STATUS_WAITING
    elif not local_provider_ok or not online_provider_ok:
        overall = STATUS_PROVIDER
    else:
        overall = STATUS_READY_PROBE

    return {
        "schema": "nexus.live_semantic_readiness.v1",
        "status": overall,
        "lanes": {
            "local": {
                "status": local_status,
                "flags_ok": local_flags_ok,
                "provider_ok": local_provider_ok,
            },
            "online": {
                "status": online_status,
                "flags_ok": external_flags_ok,
                "provider_ok": online_provider_ok,
            },
        },
        "public_claim_allowed": False,
        "production_ready": False,
        "routing_surface_changed": False,
        "flags": flag_state,
        "missing_flags": missing_flags,
        "providers": {
            "local": {
                "identity": "LocalAssistService→LocalModelExecutor→Ollama",
                "ollama": ollama,
                "lane_ready": local_status == STATUS_READY_PROBE,
            },
            "online": {
                "identity": "agy_cli",
                "agy": agy,
                "lane_ready": online_status == STATUS_READY_PROBE,
                "note": "Gemini CLI / API-key paths are not authorized substitutes; binary exists ≠ ready",
            },
        },
        "side_effect_caps_isolated_only": list(SIDE_EFFECT_CAPS),
        "blockers": blockers,
        "estimated_calls": {
            "local_model": "2-5",
            "online_agy": "10-20",
        },
        "next_actions_when_authorized": [
            "local live: local_model_executor + repair_loop full proof chain",
            "online live: EXTERNAL_AUTH promotable set via agy (isolated side-effects)",
            "postflight: claim_gate/delivery_gate with real verifier artifacts",
            "optional: fused_live_pilot → formal_from_pilot real B/D pairs",
            "learn_scheduler: remain OPERATIONAL_BLOCKED if slo_readiness<0.5",
        ],
        # Readiness never derives live/semantic complete
        "live_local_complete": False,
        "live_online_complete": False,
        "semantic_closure": False,
        "env_mutated": False,
    }
