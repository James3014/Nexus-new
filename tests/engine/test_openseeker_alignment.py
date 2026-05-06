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


def test_openseeker_trace_records_belief_confidence_without_reasoning_text():
    trace = build_openseeker_trace(
        usage_trace={
            "route_decision": {
                "selected_capabilities": ["semantic_searcher", "belief"],
                "signal_snapshot": {"confidence": 0.42},
            },
            "capabilities": {"claim_verified": True},
        },
        capability_receipts=[
            {"name": "semantic_searcher", "evidence_refs": ["semantic:policy:r1"]},
            {"name": "belief", "evidence_refs": ["belief:policy:confidence:0.42"]},
        ],
    )

    assert trace["belief_confidence_at_decision"] == 0.42
    assert trace["belief_confidence_source"] == "route_decision.signal_snapshot.confidence"
    assert trace["belief_low_confidence"] is True
    assert "reasoning" not in trace


def test_openseeker_trace_counts_route_tactical_tool_map():
    trace = build_openseeker_trace(
        usage_trace={
            "route_decision": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "stop_policy": {
                    "tactical_sequence": ["hyper_sprint", "semantic_searcher", "autoreason", "belief"],
                    "tactical_tool_map": [
                        {"capability": "hyper_sprint", "evidence_required": False},
                        {"capability": "semantic_searcher", "evidence_required": True},
                        {"capability": "autoreason", "evidence_required": True},
                        {"capability": "belief", "evidence_required": True},
                    ],
                },
            },
        },
        capability_receipts=[
            {"name": "semantic_searcher", "evidence_refs": ["semantic:route:r1"]},
            {"name": "belief", "evidence_refs": ["belief:route:confidence:0.8"]},
        ],
    )

    assert trace["route_tactical_sequence"] == ["hyper_sprint", "semantic_searcher", "autoreason", "belief"]
    assert trace["tool_action_count"] == 4
    assert trace["route_tactical_tool_count"] == 4
    assert trace["route_evidence_required_count"] == 3
    assert "tactical:semantic_searcher" in trace["action_sequence"]
    assert trace["action_catalog_schema_version"] == "nexus_openseeker_action_catalog.v1"
    assert any(item["action"] == "tactical:semantic_searcher" and item["evidence_required"] for item in trace["action_catalog"])
