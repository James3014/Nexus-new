"""RC-3: R5 parity/loss + no synthetic measured telemetry."""
from __future__ import annotations

from nexus.engine.capability_contracts import CapabilityReceipt as EngineReceipt
from nexus.engine.capability_receipt_adapters import (
    honest_unavailable_telemetries,
    merge_capability_receipt,
)
from nexus.engine.capability_receipt_parity import (
    audit_roundtrip,
    core_to_engine,
    engine_to_core,
)


def test_merge_never_synthesizes_measured_100():
    r = merge_capability_receipt(
        name="codeintel",
        selected=True,
        invoked=True,
        gate_passed=True,
        evidence_refs=["ev:1"],
    )
    t = r.telemetries
    assert t.get("telemetry_source") == "unavailable"
    assert t.get("wall_time_ms") is None
    assert t.get("token_usage") is None
    assert t.get("claimable") is False
    assert r.public_claim_safe is False


def test_honest_unavailable_shape():
    t = honest_unavailable_telemetries()
    assert t["telemetry_source"] == "unavailable"
    assert t["missing_evidence_reason"]


def test_engine_to_core_not_silent_pass():
    eng = EngineReceipt(
        name="memory",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        selection_source="planner",
        executor_id="mem-1",
        evidence_refs=("ev:1",),
        failure_reason="",
        telemetries={"telemetry_source": "unavailable"},
    )
    report = engine_to_core(eng)
    assert report["parity_complete"] is False
    assert report["ok"] is False
    assert report["public_claim_allowed"] is False
    assert report["blockers"]
    assert "partial_core" in report


def test_core_to_engine_detects_lossy_outcome():
    report = core_to_engine(
        {
            "capability_name": "belief",
            "selected": True,
            "invoked": True,
            "evidence_id": "e1",
            "gate_passed": True,
            "outcome": {"score": 1},
            "skill_receipts": [{"x": 1}],
            "timestamp": "2026-01-01",
            "telemetries": {},
        }
    )
    assert report["ok"] is False
    assert any("lossy" in b or "unrepresentable" in b for b in report["blockers"])


def test_roundtrip_not_lossless():
    eng = EngineReceipt(
        name="x",
        selected=True,
        invoked=True,
        evidence_refs=("a",),
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        selection_source="planner",
    )
    rt = audit_roundtrip(eng)
    assert rt["lossless"] is False
    assert rt["public_claim_allowed"] is False


def test_estimated_telemetry_not_public_claim_safe():
    r = merge_capability_receipt(
        name="y",
        selected=True,
        invoked=True,
        gate_passed=True,
        evidence_refs=["e"],
        telemetries={
            "telemetry_source": "estimated",
            "wall_time_ms": 50,
            "token_usage": 10,
            "provider_costs": 0.0,
            "overhead_ms": 1,
        },
    )
    assert r.public_claim_safe is False


def test_no_alias_of_classes():
    from nexus.core.belief_contracts import CapabilityReceipt as Core
    from nexus.engine.capability_contracts import CapabilityReceipt as Eng

    assert Core is not Eng
    assert set(f.name for f in Core.__dataclass_fields__.values()) != set(
        f.name for f in Eng.__dataclass_fields__.values()
    )
