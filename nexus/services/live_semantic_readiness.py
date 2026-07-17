"""Live semantic readiness probe (fail-closed; never sets auth flags).

Reports WAITING_AUTHORIZATION when external/local flags or providers are
missing. Does **not** unlock public_claim_allowed. Used to re-anchor live
lanes without painting false green.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any


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


def _flag_set(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def _ollama_status() -> dict[str, Any]:
    binary = shutil.which("ollama") or ""
    if not binary:
        return {"binary": False, "server_up": False, "error": "ollama_binary_missing"}
    try:
        proc = subprocess.run(
            [binary, "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            return {"binary": True, "server_up": True, "path": binary, "error": ""}
        err = (proc.stderr or proc.stdout or "ollama_list_failed")[:200]
        return {"binary": True, "server_up": False, "path": binary, "error": err}
    except Exception as exc:  # noqa: BLE001
        return {"binary": True, "server_up": False, "path": binary, "error": str(exc)[:200]}


def _agy_status() -> dict[str, Any]:
    binary = shutil.which("agy") or ""
    if not binary:
        return {"binary": False, "path": "", "error": "agy_binary_missing"}
    return {"binary": True, "path": binary, "error": ""}


def probe_live_semantic_readiness(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a JSON-safe readiness receipt without mutating process env.

    When ``env`` is provided, flag checks use that mapping (for tests); providers
    are still probed from the real system.
    """
    # Temporarily overlay env for flag reads only
    saved: dict[str, str | None] = {}
    if env is not None:
        for k in REQUIRED_FLAGS:
            saved[k] = os.environ.get(k)
            if k in env:
                os.environ[k] = env[k]
            elif k in os.environ:
                del os.environ[k]

    try:
        flag_state = {name: _flag_set(name) for name in REQUIRED_FLAGS}
        missing_flags = [n for n, ok in flag_state.items() if not ok]
        ollama = _ollama_status()
        agy = _agy_status()

        local_ready = all(flag_state[f] for f in LOCAL_FLAGS) and bool(ollama.get("server_up"))
        external_ready = all(flag_state[f] for f in EXTERNAL_FLAGS) and bool(agy.get("binary"))

        blockers: list[str] = []
        if missing_flags:
            blockers.append("missing_auth_flags:" + ",".join(missing_flags))
        if not ollama.get("server_up"):
            blockers.append("ollama_server_down")
        if not agy.get("binary"):
            blockers.append("agy_binary_missing")

        status = "READY" if (local_ready and external_ready and not blockers) else "WAITING_AUTHORIZATION"

        return {
            "schema": "nexus.live_semantic_readiness.v1",
            "status": status,
            "public_claim_allowed": False,
            "production_ready": False,
            "routing_surface_changed": False,
            "flags": flag_state,
            "missing_flags": missing_flags,
            "providers": {
                "local": {
                    "identity": "LocalAssistService→LocalModelExecutor→Ollama",
                    "ollama": ollama,
                    "lane_ready": local_ready,
                },
                "online": {
                    "identity": "agy_cli",
                    "agy": agy,
                    "lane_ready": external_ready,
                    "note": "Gemini CLI / API-key paths are not authorized substitutes",
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
            "live_local_complete": False,
            "live_online_complete": False,
            "semantic_closure": False,
        }
    finally:
        if env is not None:
            for k, old in saved.items():
                if old is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old
