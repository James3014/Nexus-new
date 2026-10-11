"""Local-MSA bench receipts are synthetic: tagged at the source and never counted."""

from nexus.engine.capability_receipt_adapters import (
    SYNTHETIC_BENCH_RECEIPT,
    DroneReceiptAdapter,
    NightshiftReceiptAdapter,
    SwarmReceiptAdapter,
)
from nexus.research.flow.capability_evidence import augment_local_msa_bench_evidence
from scripts.bench.ab_eval import _CAPABILITY_COVERAGE_SPEC as RULES


def _augment(tmp_path, monkeypatch, text):
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR", "1")
    return augment_local_msa_bench_evidence(
        tmp_path,
        task_id="route-oracle-001",
        task_desc=text,
        task_type="bug",
        evidence={"nightshift_recommended": True},
        artifact_verified=True,
    )


def test_augmented_reports_are_tagged_synthetic(tmp_path, monkeypatch):
    out = _augment(tmp_path, monkeypatch, "swarm drone nightshift")

    assert out["swarm_report"]["synthetic"] is True
    assert out["drone_report"]["synthetic"] is True
    assert out["nightshift_report"]["synthetic"] is True


def test_receipt_adapters_do_not_count_synthetic_reports(tmp_path, monkeypatch):
    payload = _augment(tmp_path, monkeypatch, "swarm drone nightshift")

    for adapter in (SwarmReceiptAdapter(), DroneReceiptAdapter(), NightshiftReceiptAdapter()):
        receipt = adapter.build(claim_verified=True, payload=payload)
        assert receipt.invoked is False, adapter.name
        assert receipt.gate_passed is False, adapter.name
        assert receipt.failure_reason == SYNTHETIC_BENCH_RECEIPT, adapter.name


def test_ab_eval_excludes_synthetic_rows():
    row = {
        "capability_swarm_used": True,
        "capability_swarm_evidence_count": 2,
        "capability_swarm_synthetic": True,
        "capability_drone_used": True,
        "capability_drone_invoked_count": 1,
        "capability_drone_synthetic": True,
        "capability_nightshift_invoked": True,
        "capability_nightshift_recovered": True,
        "capability_nightshift_report_path": "r.json",
        "capability_nightshift_synthetic": True,
        "capability_claim_verified": True,
    }
    for name in ("swarm", "drone", "nightshift"):
        for stage in ("invoked", "evidence", "gate"):
            assert RULES[name][stage](row) is False, (name, stage)
    real = dict(row, capability_swarm_synthetic=False)
    assert RULES["swarm"]["gate"](real) is True
