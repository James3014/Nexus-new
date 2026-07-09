from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_runtime_guard import (
    P3RuntimeGuard,
    ALLOWED_RUNTIME_STATES,
    compute_p3_runtime_guard,
    p3_runtime_guard_to_dict,
)


# ============================================================
# P3-K2-1: All states are accepted (with env guard for guarded states)
# ============================================================


def test_all_states_accepted():
    for state in ALLOWED_RUNTIME_STATES:
        if state in ("env_guarded_dry_run", "env_guarded_runtime_candidate"):
            guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=True)
            assert guard.runtime_state == state
        else:
            guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
            assert guard.runtime_state == state


# ============================================================
# P3-K2-2: Unknown state fails closed
# ============================================================


def test_unknown_state_fails_closed():
    guard = compute_p3_runtime_guard(requested_state="unknown_state")
    assert guard.runtime_state == "blocked"
    assert "unknown_state" in guard.reason


# ============================================================
# P3-K2-3: env_guarded_dry_run without env guard downgrades
# ============================================================


def test_dry_run_without_guard_downgrades():
    guard = compute_p3_runtime_guard(requested_state="env_guarded_dry_run", env_guard_override=False)
    assert guard.runtime_state == "shadow_only"
    assert "env_guard_missing" in guard.reason


# ============================================================
# P3-K2-4: env_guarded_runtime_candidate without env guard downgrades
# ============================================================


def test_runtime_candidate_without_guard_downgrades():
    guard = compute_p3_runtime_guard(requested_state="env_guarded_runtime_candidate", env_guard_override=False)
    assert guard.runtime_state == "shadow_only"
    assert "env_guard_missing" in guard.reason


# ============================================================
# P3-K2-5: default_runtime_allowed=false for all states
# ============================================================


def test_default_runtime_allowed_false():
    for state in ALLOWED_RUNTIME_STATES:
        guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
        assert guard.default_runtime_allowed is False


# ============================================================
# P3-K2-6: patch_apply_allowed=false for all states
# ============================================================


def test_patch_apply_allowed_false():
    for state in ALLOWED_RUNTIME_STATES:
        guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
        assert guard.patch_apply_allowed is False


# ============================================================
# P3-K2-7: public_claim_allowed=false for all states
# ============================================================


def test_public_claim_allowed_false():
    for state in ALLOWED_RUNTIME_STATES:
        guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
        assert guard.public_claim_allowed is False


# ============================================================
# P3-K2-8: production_ready=false for all states
# ============================================================


def test_production_ready_false():
    for state in ALLOWED_RUNTIME_STATES:
        guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
        assert guard.production_ready is False


# ============================================================
# P3-K2-9: full_verifier_required=true for all states
# ============================================================


def test_full_verifier_required_true():
    for state in ALLOWED_RUNTIME_STATES:
        guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
        assert guard.full_verifier_required is True


# ============================================================
# P3-K2-10: claim_gate_required=true for all states
# ============================================================


def test_claim_gate_required_true():
    for state in ALLOWED_RUNTIME_STATES:
        guard = compute_p3_runtime_guard(requested_state=state, env_guard_override=False)
        assert guard.claim_gate_required is True


# ============================================================
# P3-K2-11: result JSON serializable
# ============================================================


def test_result_json_serializable():
    guard = compute_p3_runtime_guard(requested_state="shadow_only")
    d = p3_runtime_guard_to_dict(guard)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)


# ============================================================
# P3-K2-12: module does not import router
# ============================================================


def test_no_router_import():
    import nexus.services.local_heal.p3_runtime_guard as mod
    source = open(mod.__file__).read()
    assert "nexus.core.router" not in source


# ============================================================
# P3-K2-13: module does not import P6 runtime hook
# ============================================================


def test_no_p6_import():
    import nexus.services.local_heal.p3_runtime_guard as mod
    source = open(mod.__file__).read()
    assert "p6_runtime_hook" not in source


# ============================================================
# P3-K2-14: module does not call cloud or local model
# ============================================================


def test_no_cloud_or_local_model():
    import nexus.services.local_heal.p3_runtime_guard as mod
    source = open(mod.__file__).read()
    assert "openai" not in source.lower()
    assert "anthropic" not in source.lower()
    assert "ollama" not in source.lower()
