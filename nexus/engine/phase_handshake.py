from __future__ import annotations

from typing import Any


def required_artifacts(phase: Any) -> tuple[str, ...]:
    provider = getattr(phase, "required_artifacts", None)
    if not callable(provider):
        return ()
    return tuple(str(item) for item in (provider() or ()) if str(item).strip())


def provided_artifacts(phase: Any) -> tuple[str, ...]:
    provider = getattr(phase, "provided_artifacts", None)
    if not callable(provider):
        return ()
    return tuple(str(item) for item in (provider() or ()) if str(item).strip())


def validate_required_artifacts(*, phase: Any, blackboard: Any) -> None:
    missing = [key for key in required_artifacts(phase) if not blackboard.has(key)]
    if missing:
        phase_name = str(getattr(phase, "name", "unknown"))
        raise RuntimeError(f"SEMANTIC_HANDSHAKE_MISSING_ARTIFACT:{phase_name}:{','.join(missing)}")


def record_phase_artifacts(*, phase: Any, result: Any, blackboard: Any) -> None:
    phase_name = str(getattr(phase, "name", "unknown"))
    mutations = getattr(result, "mutations", {}) or {}
    if isinstance(mutations, dict):
        for key, value in mutations.items():
            if str(key).strip():
                blackboard.append(phase_name, str(key), value)
    for key in provided_artifacts(phase):
        if isinstance(mutations, dict) and key in mutations:
            continue
        blackboard.append(phase_name, key, {"provided": True})
