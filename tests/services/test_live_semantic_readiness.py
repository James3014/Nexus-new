"""Fail-closed live readiness probe — never sets flags; claim stays false."""
from __future__ import annotations

import os

from nexus.services.live_semantic_readiness import (
    REQUIRED_FLAGS,
    STATUS_PROVIDER,
    STATUS_READY_PROBE,
    STATUS_WAITING,
    probe_live_semantic_readiness,
)


def test_probe_without_flags_is_waiting_authorization():
    empty = {k: "" for k in REQUIRED_FLAGS}
    report = probe_live_semantic_readiness(env=empty)
    assert report["status"] == STATUS_WAITING
    assert report["public_claim_allowed"] is False
    assert report["production_ready"] is False
    assert report["live_local_complete"] is False
    assert report["live_online_complete"] is False
    assert report["semantic_closure"] is False
    assert report["missing_flags"]
    assert report.get("env_mutated") is False
    assert "missing_auth_flags" in " ".join(report["blockers"]) or report["missing_flags"]
    # lane-specific, not all-or-nothing only
    assert report["lanes"]["local"]["status"] == STATUS_WAITING
    assert report["lanes"]["online"]["status"] == STATUS_WAITING


def test_probe_never_mutates_os_environ():
    key = "NEXUS_LOCAL_MODEL_CALL_ALLOWED"
    before = os.environ.get(key)
    try:
        os.environ.pop(key, None)
        probe_live_semantic_readiness(env={key: "1", **{k: "" for k in REQUIRED_FLAGS if k != key}})
        # overlay must not leave flag set on process env
        assert os.environ.get(key) is None
    finally:
        if before is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = before


def test_probe_never_unlocks_claim_even_if_flags_present():
    full = {k: "1" for k in REQUIRED_FLAGS}
    report = probe_live_semantic_readiness(env=full)
    assert report["public_claim_allowed"] is False
    assert report["production_ready"] is False
    assert report["routing_surface_changed"] is False
    assert report["live_local_complete"] is False
    assert report["semantic_closure"] is False
    # With flags set, status is PROVIDER or READY_FOR_LIVE_PROBE — never LIVE_VERIFIED here
    assert report["status"] in {STATUS_PROVIDER, STATUS_READY_PROBE, STATUS_WAITING}
    assert report["status"] != "LIVE_VERIFIED"
    assert "agy" in report["providers"]["online"]["identity"] or report["providers"]["online"]["identity"] == "agy_cli"


def test_probe_json_safe_and_side_effect_list_present():
    import json

    report = probe_live_semantic_readiness(env={k: "" for k in REQUIRED_FLAGS})
    json.dumps(report)
    assert "integration_manager" in report["side_effect_caps_isolated_only"]
    # binary exists alone does not mark online ready without auth
    agy = report["providers"]["online"]["agy"]
    if agy.get("binary") and not agy.get("authenticated"):
        assert report["lanes"]["online"]["provider_ok"] is False
