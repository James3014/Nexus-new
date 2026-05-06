from __future__ import annotations

from nexus.engine.capability_contracts import CapabilityReceipt
from nexus.engine.openseeker_alignment import build_openseeker_trace, summarize_receipt_metrics


def test_openseeker_trace_counts_actions_and_evidence_hops():
    trace = build_openseeker_trace(
        usage_trace={
            "phase_trace": {"P": "route_built", "X": "retrieval_checked", "A": "artifact_verified"},
            "capability_plan": {"selected_capabilities": ["semantic_searcher", "belief", "artifact_gate"]},
            "capabilities": {"claim_verified": True},
        },
        capability_receipts=[
            {"name": "semantic_searcher", "evidence_refs": ["semantic:task:doc"]},
            {"name": "belief", "evidence_refs": [".nexus/reports/codeintel/impact.json"]},
        ],
    )

    assert trace["schema_version"] == "nexus_openseeker_alignment.v1"
    assert trace["trajectory_step_count"] == 6
    assert trace["tool_action_count"] == 3
    assert trace["evidence_hop_count"] == 2
    assert trace["evidence_source_count"] == 2
    assert trace["low_step_filtered"] is True
    assert trace["single_source_claim"] is False


def test_receipt_metrics_count_only_invoked_tool_actions():
    out = summarize_receipt_metrics(
        [
            CapabilityReceipt(
                name="semantic_searcher",
                selected=True,
                invoked=True,
                evidence_present=True,
                evidence_refs=("semantic:task:doc",),
            ),
            CapabilityReceipt(name="external_doc_scout", selected=True, invoked=False),
        ]
    )

    assert out["schema_version"] == "nexus_openseeker_receipt_metrics.v1"
    assert out["tool_action_count"] == 1
    assert out["evidence_hop_count"] == 1
