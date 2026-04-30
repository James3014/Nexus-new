from __future__ import annotations

from nexus.engine.capability_receipts import build_trace_receipts


def test_swarm_receipt_requires_report_evidence_for_public_claim():
    plan = {"selected_capabilities": ["swarm"]}

    missing = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": True,
                "swarm_evidence_count": 0,
                "swarm_report": {"schema_version": "nexus_swarm_receipt_v1"},
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": True,
                "swarm_report": {
                    "schema_version": "nexus_swarm_receipt_v1",
                    "source": "local_msa_bench_executor",
                    "evidence_count": 2,
                    "consensus": "pass",
                    "evidence_refs": ["role:logic:evidence:artifact_verified"],
                    "report_path": ".nexus/reports/swarm/run.json",
                },
            },
        )
    }

    assert missing["swarm"].public_claim_safe is False
    assert missing["swarm"].failure_reason == "invoked_without_evidence"
    assert proven["swarm"].public_claim_safe is True
    assert "report:.nexus/reports/swarm/run.json" in proven["swarm"].evidence_refs
    assert "role_findings:2" in proven["swarm"].evidence_refs


def test_nightshift_receipt_requires_invoked_recovered_report():
    plan = {"selected_capabilities": ["nightshift"]}

    recommended = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "nightshift_recommended": True,
                "nightshift_invoked": False,
                "nightshift_recovered": False,
                "nightshift_failure_reason": "recommended_without_report",
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "nightshift_report": {
                    "schema_version": "nexus_nightshift_receipt_v1",
                    "source": "local_msa_bench_executor",
                    "recommended": True,
                    "invoked": True,
                    "recovered": True,
                    "report_path": ".nexus/reports/nightshift/run.json",
                    "failure_reason": "",
                },
            },
        )
    }

    assert recommended["nightshift"].public_claim_safe is False
    assert recommended["nightshift"].failure_reason == "recommended_without_report"
    assert proven["nightshift"].public_claim_safe is True
    assert proven["nightshift"].evidence_refs == (".nexus/reports/nightshift/run.json",)
