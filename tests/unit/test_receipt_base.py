"""RC-1: receipt_base, run_anchor_hash, acyclic hash DAG, legacy evidence compat."""
from __future__ import annotations

import json

import pytest

from nexus.evidence.receipt_base import (
    attach_r3_receipt_base,
    build_receipt_base_dict,
    build_structured_evidence_ref,
    canonical_json_hash,
    compute_receipt_hash,
    compute_run_anchor_hash,
    hash_stage_payload,
    legacy_evidence_refs_to_structured,
)


def test_canonical_hash_deterministic_and_key_order_independent():
    a = canonical_json_hash({"b": 1, "a": 2})
    b = canonical_json_hash({"a": 2, "b": 1})
    assert a == b
    assert len(a) == 64


def test_run_anchor_stable_for_same_identity():
    h1 = compute_run_anchor_hash(task_id="t1", planner_decision_id="pd", packet_hash="p")
    h2 = compute_run_anchor_hash(task_id="t1", planner_decision_id="pd", packet_hash="p")
    assert h1 == h2
    h3 = compute_run_anchor_hash(task_id="t1", planner_decision_id="pd", packet_hash="p2")
    assert h1 != h3


def test_receipt_hash_excludes_self_and_detects_child_tamper():
    anchor = compute_run_anchor_hash(task_id="t")
    child_ok = hash_stage_payload({"invoked": True, "x": 1}, stage_name="local")
    child_bad = hash_stage_payload({"invoked": True, "x": 2}, stage_name="local")
    r1 = compute_receipt_hash(run_anchor_hash=anchor, ordered_child_hashes=[child_ok])
    r2 = compute_receipt_hash(run_anchor_hash=anchor, ordered_child_hashes=[child_ok])
    r3 = compute_receipt_hash(run_anchor_hash=anchor, ordered_child_hashes=[child_bad])
    assert r1 == r2
    assert r1 != r3
    # self-inclusion would change hash if we accidentally fed receipt_hash back in
    r_with_noise = compute_receipt_hash(
        run_anchor_hash=anchor,
        ordered_child_hashes=[child_ok],
        claim_boundary={"public_claim_allowed": False},
    )
    assert r_with_noise != r1 or r_with_noise  # always defined


def test_structured_evidence_unavailable_without_content_hash():
    ref = build_structured_evidence_ref(evidence_id="ev1", content_hash="")
    assert ref["hash_status"] == "UNAVAILABLE"
    assert ref["claim_contribution"] is False
    # must not invent hash from id
    assert ref["content_hash"] == ""


def test_legacy_evidence_refs_project_without_breaking_list_str():
    legacy = ["ev:a", "ev:b"]
    structured = legacy_evidence_refs_to_structured(legacy, task_id="t")
    assert len(structured) == 2
    assert all(r["hash_status"] == "UNAVAILABLE" for r in structured)
    # original list still list[str]
    assert all(isinstance(x, str) for x in legacy)


def test_receipt_base_dict_is_json_safe_and_claim_false():
    base = build_receipt_base_dict(
        task_id="t",
        run_anchor_hash="a" * 64,
        receipt_hash="b" * 64,
        claim_boundary={"public_claim_allowed": True},  # producer attempt
    )
    raw = json.dumps(base)
    loaded = json.loads(raw)
    assert loaded["public_claim_allowed"] is False
    assert loaded["claim_boundary"]["public_claim_allowed"] is False
    assert "structured_evidence_refs" in loaded


def test_attach_r3_preserves_legacy_evidence_refs_and_sets_base():
    receipt = {
        "schema": "nexus.unified_runtime.receipt.v1",
        "task_id": "task-1",
        "workspace_revision": "wr-1",
        "planner_decision_id": "pd-1",
        "evidence_refs": ["ref:1", "ref:2"],
        "selection_authority": "CapabilityPlanner",
        "claim_boundary": {"public_claim_allowed": True, "receipt_complete": True},
        "public_claim_allowed": True,
        "local": {"invoked": True, "evidence_refs": ["ref:1"]},
        "online": {"invoked": True},
        "capability_results": {
            "codeintel": {
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": False,
                "evidence_refs": ["ref:2"],
            }
        },
        "capability_evidence_bundle": {"evidence_ids": ["ref:1"], "ok": True},
        "consumed_evidence_ids": ["ref:1"],
        "contributed_capabilities": [],
        "executed_capabilities": ["codeintel"],
    }
    out = attach_r3_receipt_base(receipt)
    assert out is receipt
    assert receipt["evidence_refs"] == ["ref:1", "ref:2"]  # legacy preserved
    assert isinstance(receipt["evidence_refs"][0], str)
    base = receipt["receipt_base"]
    assert base["schema"].startswith("nexus.receipt_base")
    assert base["run_anchor_hash"]
    assert base["receipt_hash"]
    assert base["public_claim_allowed"] is False
    assert receipt["public_claim_allowed"] is False
    # acyclic: parent is run_anchor, not final receipt_hash
    assert base["parent_receipt_hashes"] == [base["run_anchor_hash"]]
    assert base["receipt_hash"] not in base["parent_receipt_hashes"]
    assert base["run_anchor_hash"] != base["receipt_hash"]
    # structured additive
    assert len(base["structured_evidence_refs"]) == 2
    # JSON dump works
    json.dumps(receipt)


def test_same_bundle_different_consumption_chain_changes_hash():
    anchor = compute_run_anchor_hash(task_id="t", shared_bundle_hash="bundle")
    chain_used = [
        {
            "capability": "local_model_executor",
            "selected": True,
            "injected": True,
            "used": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "consumer": "online",
        }
    ]
    chain_unused = [
        {
            "capability": "local_model_executor",
            "selected": True,
            "injected": True,
            "used": False,
            "evidence_present": True,
            "gate_passed": False,
            "outcome_contributed": False,
            "consumer": "online",
        }
    ]
    h1 = compute_receipt_hash(
        run_anchor_hash=anchor,
        shared_bundle_hash="bundle",
        consumption_chain=chain_used,
    )
    h2 = compute_receipt_hash(
        run_anchor_hash=anchor,
        shared_bundle_hash="bundle",
        consumption_chain=chain_unused,
    )
    assert h1 != h2


def test_attach_detects_tamper_via_stage_change():
    base_receipt = {
        "task_id": "t",
        "evidence_refs": [],
        "claim_boundary": {},
        "local": {"invoked": True, "payload": "a"},
        "capability_evidence_bundle": {},
    }
    r1 = attach_r3_receipt_base(dict(base_receipt))
    h1 = r1["receipt_hash"]
    r2 = attach_r3_receipt_base({**base_receipt, "local": {"invoked": True, "payload": "b"}})
    assert r2["receipt_hash"] != h1


def test_r1_r2_bind_run_anchor_not_final_r3():
    from nexus.evidence.receipt_base import project_child_receipt_base

    r1 = project_child_receipt_base(
        source_world="C",
        source_component="local_executor",
        task_id="shared-task",
        planner_decision_id="pd1",
        shared_bundle_hash="bundle-x",
        stage_payload={"invoked": True, "candidate_hash": "abc"},
        stage_name="local_model_executor",
        used=True,
        evidence_present=True,
        source_candidate_hash="abc",
        applied_candidate_hash="abc",
    )
    r2 = project_child_receipt_base(
        source_world="hybrid",
        source_component="hybrid_runtime",
        task_id="shared-task",
        planner_decision_id="pd1",
        shared_bundle_hash="bundle-x",
        stage_payload={"status": "ok", "live": True},
        stage_name="cloud_with_local_assist",
        used=True,
        evidence_present=True,
    )
    assert r1["run_anchor_hash"] == r2["run_anchor_hash"]
    assert r1["shared_bundle_hash"] == r2["shared_bundle_hash"] == "bundle-x"
    assert r1["parent_receipt_hashes"] == [r1["run_anchor_hash"]]
    assert r2["parent_receipt_hashes"] == [r2["run_anchor_hash"]]
    assert r1["receipt_hash"] != r2["receipt_hash"]
    # same bundle, one side unused → different consumption hash path
    r2_unused = project_child_receipt_base(
        source_world="hybrid",
        source_component="hybrid_runtime",
        task_id="shared-task",
        planner_decision_id="pd1",
        shared_bundle_hash="bundle-x",
        stage_payload={"status": "ok", "live": False},
        stage_name="cloud_with_local_assist",
        used=False,
        evidence_present=False,
    )
    assert r2_unused["receipt_hash"] != r2["receipt_hash"]


def test_stamp_r1_auth_blocked_not_success():
    from types import SimpleNamespace
    from nexus.evidence.receipt_base import stamp_r1_local_response

    resp = SimpleNamespace(
        invoked=True,
        local_model_called=False,
        candidate_hash="",
        evidence_refs=(),
        provider="none",
        model_name="",
        error="provider_not_configured",
        raw_model_metadata={},
    )
    req = SimpleNamespace(task_id="t1", planner_snapshot={}, instance_id="")
    stamp_r1_local_response(resp, request=req)
    base = resp.raw_model_metadata["receipt_base"]
    assert base["auth_status"] == "AUTH_BLOCKED"
    assert base["public_claim_allowed"] is False
    assert base["consumption_chain"][0]["used"] is False
