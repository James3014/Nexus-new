"""P6-D2: Mainline Boundary Contract Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_mainline_boundary import P6MainlineBoundary, build_mainline_boundary


def test_p6_cannot_mark_solved():
    b = build_mainline_boundary()
    assert b.p6_can_mark_solved is False


def test_p6_cannot_mark_claim_eligible():
    b = build_mainline_boundary()
    assert b.p6_can_mark_claim_eligible is False


def test_p6_cannot_set_public_claim():
    b = build_mainline_boundary()
    assert b.p6_can_set_public_claim_allowed is False


def test_p6_cannot_override_p4():
    b = build_mainline_boundary()
    assert b.p6_can_override_p4_verifier is False


def test_p6_cannot_override_p3():
    b = build_mainline_boundary()
    assert b.p6_can_override_p3_topology is False


def test_p6_cannot_override_p5():
    b = build_mainline_boundary()
    assert b.p6_can_override_p5_selection is False


def test_env_guard_required():
    b = build_mainline_boundary()
    assert b.p6_requires_env_guard is True


def test_json_serializable():
    b = build_mainline_boundary()
    d = {"p6_can_mark_solved": b.p6_can_mark_solved, "p6_requires_env_guard": b.p6_requires_env_guard}
    json_str = json.dumps(d)
    assert len(json_str) > 0
