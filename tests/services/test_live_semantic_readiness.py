"""Fail-closed live readiness probe — never sets flags; claim stays false."""
from __future__ import annotations

from nexus.services.live_semantic_readiness import (
    REQUIRED_FLAGS,
    probe_live_semantic_readiness,
)


def test_probe_without_flags_is_waiting_authorization():
    # Force all flags unset via overlay env
    empty = {k: "" for k in REQUIRED_FLAGS}
    report = probe_live_semantic_readiness(env=empty)
    assert report["status"] == "WAITING_AUTHORIZATION"
    assert report["public_claim_allowed"] is False
    assert report["production_ready"] is False
    assert report["live_local_complete"] is False
    assert report["live_online_complete"] is False
    assert report["semantic_closure"] is False
    assert report["missing_flags"]
    assert "missing_auth_flags" in " ".join(report["blockers"]) or report["missing_flags"]


def test_probe_never_unlocks_claim_even_if_flags_present():
    full = {k: "1" for k in REQUIRED_FLAGS}
    report = probe_live_semantic_readiness(env=full)
    # May still be WAITING if ollama down — either way claim false
    assert report["public_claim_allowed"] is False
    assert report["production_ready"] is False
    assert report["routing_surface_changed"] is False
    assert "agy" in report["providers"]["online"]["identity"] or report["providers"]["online"]["identity"] == "agy_cli"


def test_probe_json_safe_and_side_effect_list_present():
    import json

    report = probe_live_semantic_readiness(env={k: "" for k in REQUIRED_FLAGS})
    json.dumps(report)
    assert "integration_manager" in report["side_effect_caps_isolated_only"]
