from __future__ import annotations

from nexus.engine.dynamic_replan import should_replan, ReplanTrigger


def test_replan_acceptance_reject():
    should, trigger = should_replan({}, reason="acceptance_reject")
    assert should is True
    assert trigger == ReplanTrigger.ACCEPTANCE_REJECT


def test_replan_timeout():
    should, trigger = should_replan({}, reason="timeout")
    assert should is True
    assert trigger == ReplanTrigger.TIMEOUT


def test_replan_low_belief_by_reason():
    should, trigger = should_replan({}, reason="low_belief")
    assert should is True
    assert trigger == ReplanTrigger.LOW_BELIEF


def test_replan_low_belief_by_state():
    should, trigger = should_replan({"belief_confidence": 0.2})
    assert should is True
    assert trigger == ReplanTrigger.LOW_BELIEF


def test_replan_no_trigger():
    should, trigger = should_replan({"belief_confidence": 1.0})
    assert should is False
    assert trigger == ReplanTrigger.NONE


def test_replan_trust_mismatch():
    should, trigger = should_replan({}, reason="trust_mismatch")
    assert should is True
    assert trigger == ReplanTrigger.TRUST_MISMATCH
