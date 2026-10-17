"""#2344: record-backed EffectAuthorityPort, shadow by default, strict opt-in."""

from __future__ import annotations

import logging

import pytest
from nexus_runtime.execution_coordination import EffectAuthorization

from nexus.orchestrator import effect_authority as ea
from nexus.orchestrator import runtime_coordination_bridge as bridge


def _auth(**over):
    data = {
        "authority_id": "bootstrap_agent",
        "authority_ref": "ref-1",
        "operation_id": "op-1",
        "attempt_id": "att-1",
        "repository": "James3014/Nexus-new",
        "effects": {"filesystem.write_paths": {"paths": ["a.py"]}},
    }
    data.update(over)
    return EffectAuthorization.build(**data)


def _record(**over):
    rec = {
        "authority_id": "bootstrap_agent",
        "repository": "James3014/Nexus-new",
        "effects": {"filesystem.write_paths": {"paths": ["a.py"]}},
    }
    rec.update(over)
    return rec


def _lookup(record):
    return lambda ref: record if ref == "ref-1" else None


def test_exact_record_match_is_accepted():
    assert ea.evaluate_authorization(_auth(), _lookup(_record())) == (True, "RECORD_MATCH")


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (None, "NO_RECORD_FOR_AUTHORITY_REF"),
        (_record(authority_id="someone_else"), "AUTHORITY_ID_MISMATCH"),
        (_record(repository="James3014/other"), "REPOSITORY_MISMATCH"),
        (_record(effects={}), "EFFECT_BROADER_THAN_RECORD:filesystem.write_paths"),
        (
            _record(effects={"filesystem.write_paths": {"paths": ["b.py"]}}),
            "EFFECT_CONSTRAINTS_DIFFER_FROM_RECORD:filesystem.write_paths",
        ),
    ],
)
def test_self_signed_or_broader_authorization_is_refused(record, reason):
    accepted, got = ea.evaluate_authorization(_auth(), _lookup(record))
    assert accepted is False
    assert got == reason


def test_lookup_error_backs_nothing():
    def boom(_ref):
        raise OSError("unreadable")

    assert ea.evaluate_authorization(_auth(), boom) == (False, "RECORD_LOOKUP_FAILED:OSError")


def test_default_is_shadow_no_port_attached(monkeypatch):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    assert bridge._effect_authority_kwargs() == {}


@pytest.mark.parametrize("value", ["", "0", "true", "yes", " 2"])
def test_only_exact_one_enables_strict(monkeypatch, value):
    monkeypatch.setenv(ea.STRICT_ENV, value)
    assert bridge._effect_authority_kwargs() == {}


def test_strict_attaches_port_and_requires_authority(monkeypatch):
    monkeypatch.setenv(ea.STRICT_ENV, "1")
    kwargs = bridge._effect_authority_kwargs()
    assert kwargs["require_effect_authority"] is True
    assert kwargs["effect_authority"] is not None


def test_shadow_records_would_refuse_without_authorization(monkeypatch, caplog):
    monkeypatch.delenv(ea.STRICT_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger=bridge.logger.name):
        decision = bridge._record_effect_authority_shadow("t1", "a1", {"task": "x"})
    assert decision["decision"] == ea.DECISION_WOULD_REFUSE
    assert decision["reason"] == "NO_EFFECT_AUTHORIZATION_ON_REQUEST"
    assert decision["mode"] == "SHADOW"
    assert ea.SHADOW_FIELD in caplog.text


def test_shadow_never_raises(monkeypatch):
    def broken(_request):
        raise RuntimeError("bug in shadow path")

    monkeypatch.setattr(ea, "shadow_decision", broken)
    assert bridge._record_effect_authority_shadow("t1", "a1", {"task": "x"}) is None


def test_shadow_skips_when_no_request():
    assert bridge._record_effect_authority_shadow("t1", "a1", None) is None
