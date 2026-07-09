"""P7-A3: Synthetic Trace Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p7_armor_synthetic_trace import build_armor_trace_rows


def test_trace_has_at_least_24_rows():
    rows = build_armor_trace_rows()
    assert len(rows) >= 24


def test_happy_path_passes_invariants():
    rows = build_armor_trace_rows()
    happy = [r for r in rows if r["trace_id"] in ("P7-01", "P7-02")]
    for r in happy:
        assert r["invariant_passed"] is True


def test_unsafe_real_provider_fails():
    rows = build_armor_trace_rows()
    r = [x for x in rows if x["trace_id"] == "P7-08"][0]
    assert r["p3_real_provider_invoked"] is True
    assert r["invariant_passed"] is False
    assert "real_provider_invoked" in r["blocked_reasons"]


def test_unsafe_network_fails():
    rows = build_armor_trace_rows()
    r = [x for x in rows if x["trace_id"] == "P7-09"][0]
    assert r["p3_network_invoked"] is True
    assert r["invariant_passed"] is False


def test_unsafe_public_claim_fails():
    rows = build_armor_trace_rows()
    r = [x for x in rows if x["trace_id"] == "P7-15"][0]
    assert r["public_claim_allowed"] is True
    assert r["invariant_passed"] is False


def test_unsafe_production_ready_fails():
    rows = build_armor_trace_rows()
    r = [x for x in rows if x["trace_id"] == "P7-16"][0]
    assert r["production_ready"] is True
    assert r["invariant_passed"] is False


def test_all_required_scenarios_present():
    rows = build_armor_trace_rows()
    ids = {r["trace_id"] for r in rows}
    assert "P7-01" in ids  # happy path
    assert "P7-08" in ids  # real provider
    assert "P7-15" in ids  # public claim


def test_json_serializable():
    rows = build_armor_trace_rows()
    json.dumps(rows[0])
