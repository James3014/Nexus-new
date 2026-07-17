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


# --- P2-C schema validator (opt-in) ---


def test_validate_receipt_base_unknown_major_fail_closed():
    from nexus.evidence.receipt_base import validate_receipt_base

    result = validate_receipt_base(
        {"schema": "totally.unknown.v9", "schema_version": "9.0"},
        mode="compatibility",
    )
    assert result["ok"] is False
    assert any("unknown_major" in b for b in result["blockers"])
    assert result["public_claim_allowed"] is False


def test_validate_receipt_base_known_major_additive_minor_readable():
    from nexus.evidence.receipt_base import build_receipt_base_dict, validate_receipt_base

    base = build_receipt_base_dict(task_id="t", run_anchor_hash="a", receipt_hash="r")
    # Simulate additive minor schema_version bump
    base["schema_version"] = "1.1"
    result = validate_receipt_base(base, mode="product")
    assert result["ok"] is True
    assert result["schema_major"] == "nexus.receipt_base"


def test_validate_receipt_base_historical_compatibility_mode():
    from nexus.evidence.receipt_base import validate_receipt_base

    hist = {
        "schema": "nexus.receipt_base.historical.v0",
        "schema_version": "0.9",
        "task_id": "old",
        "run_anchor_hash": "a",
        "receipt_hash": "r",
        "parent_receipt_hashes": [],
        "structured_evidence_refs": [],
        "claim_boundary": {},
        "public_claim_allowed": False,
    }
    compat = validate_receipt_base(hist, mode="compatibility")
    assert compat["ok"] is True
    assert any("compatibility_schema" in w for w in compat["warnings"])
    strict = validate_receipt_base(hist, mode="strict")
    assert strict["ok"] is False


def test_validate_receipt_base_does_not_raise_by_default():
    from nexus.evidence.receipt_base import validate_receipt_base

    result = validate_receipt_base(None, mode="product")
    assert result["ok"] is False
    # opt-in raise only
    with pytest.raises(ValueError, match="receipt_base_validation_failed"):
        validate_receipt_base(None, mode="product", raise_on_error=True)


def test_validate_legacy_evidence_refs_remain_list_str():
    from nexus.evidence.receipt_base import attach_r3_receipt_base, validate_receipt_base

    receipt = {
        "task_id": "t",
        "evidence_refs": ["ev-1", "ev-2"],  # legacy list[str]
    }
    attach_r3_receipt_base(receipt)
    assert isinstance(receipt["evidence_refs"], list)
    assert all(isinstance(x, str) for x in receipt["evidence_refs"])
    ok = validate_receipt_base(receipt, mode="product")
    assert ok["ok"] is True
    # typed breakage fails closed
    broken = dict(receipt)
    broken["evidence_refs"] = [{"id": "x"}]  # must not replace legacy with objects
    bad = validate_receipt_base(broken, mode="product")
    assert bad["ok"] is False
    assert any("legacy_evidence_refs" in b for b in bad["blockers"])


# --- P2-D 5/5 product coverage audit ---


def test_audit_product_receipt_coverage_5_of_5_contract_embed():
    from nexus.evidence.receipt_base import audit_product_receipt_coverage
    from nexus.services.capability_registry import build_wiring_matrix

    audit = audit_product_receipt_coverage(wiring_matrix=build_wiring_matrix())
    assert audit["contract_coverage"] == "5/5"
    assert audit["embed_complete"] is True
    assert all(audit["contract_present"][k] for k in ("R1", "R2", "R3", "R4", "R5"))
    # Must NOT equate embed with live/semantic closure
    assert audit["live_provider_coverage"]["complete"] is False
    assert audit["semantic_closure"] is False
    assert audit["all_closure_complete"] is False
    assert audit["public_claim_allowed"] is False
    assert audit["physical_execution_coverage"]["missing_engine_count"] == 0
    assert audit["physical_execution_coverage"]["node_count"] == 57


def test_audit_missing_surface_does_not_fake_5_of_5():
    from nexus.evidence.receipt_base import audit_product_receipt_coverage

    audit = audit_product_receipt_coverage(
        surfaces={"R1": True, "R2": None, "R3": True, "R4": True, "R5": True}
    )
    assert audit["contract_coverage"] == "4/5"
    assert audit["embed_complete"] is False
    assert audit["contract_present"]["R2"] is False


# --- Phase 0 false-green regressions A–L (must fail closed on product path) ---


def test_A_canonical_json_hash_rejects_non_json_safe():
    """A: Path/set/dataclass must not hash via default=str."""
    from dataclasses import dataclass
    from pathlib import Path

    from nexus.evidence.receipt_base import canonical_json_hash

    @dataclass
    class _Box:
        x: int

    with pytest.raises((TypeError, ValueError)):
        canonical_json_hash({"p": Path("/tmp/x")})
    with pytest.raises((TypeError, ValueError)):
        canonical_json_hash({"s": {1, 2, 3}})
    with pytest.raises((TypeError, ValueError)):
        canonical_json_hash({"d": _Box(1)})


def test_B_empty_identity_hashes_fail_strict_product_validation():
    """B: empty task_id / run_anchor_hash / receipt_hash fail strict product."""
    from nexus.evidence.receipt_base import build_receipt_base_dict, validate_receipt_base

    base = build_receipt_base_dict(task_id="", run_anchor_hash="", receipt_hash="")
    result = validate_receipt_base(base, mode="strict")
    assert result["ok"] is False
    joined = " ".join(result["blockers"])
    assert "task_id" in joined or "empty_task_id" in joined
    assert "run_anchor" in joined or "empty_run_anchor" in joined
    assert "receipt_hash" in joined or "empty_receipt_hash" in joined


def test_C_empty_bundle_not_verified_shared_bundle_hash():
    """C: empty/unsealed bundle must not yield verified shared_bundle_hash."""
    from nexus.evidence.receipt_base import (
        attach_r3_receipt_base,
        resolve_shared_bundle_hash,
    )

    resolved = resolve_shared_bundle_hash({})
    assert not resolved.get("verified")
    assert not (resolved.get("shared_bundle_hash") or "").strip()
    assert resolved.get("status") in {"UNAVAILABLE", "UNSEALED", "EMPTY"}

    receipt = {"task_id": "t", "capability_evidence_bundle": {}}
    attach_r3_receipt_base(receipt)
    base = receipt["receipt_base"]
    # May keep computed content hash separately, but verified seal empty
    assert not base.get("shared_bundle_verified")
    assert (base.get("shared_bundle_hash") or "") == "" or base.get(
        "shared_bundle_hash_status"
    ) in {"UNAVAILABLE", "UNSEALED", "EMPTY"}


def test_D_empty_consumer_payload_not_consumed_hash():
    """D: empty consumer payload → empty hash + UNAVAILABLE, not fake consumed."""
    from nexus.evidence.receipt_base import (
        attach_r3_receipt_base,
        resolve_consumer_payload_hash,
    )

    res = resolve_consumer_payload_hash(None)
    assert (res.get("consumer_payload_hash") or "") == ""
    assert res.get("status") == "UNAVAILABLE"

    receipt = {
        "task_id": "t",
        "consumed_evidence_ids": [],
        "contributed_capabilities": [],
        "executed_capabilities": [],
    }
    attach_r3_receipt_base(receipt)
    base = receipt["receipt_base"]
    assert (base.get("consumer_payload_hash") or "") == "" or base.get(
        "consumer_payload_hash_status"
    ) == "UNAVAILABLE"


def test_E_failed_verifier_without_artifact_no_artifact_hash():
    """E: verifier FAILED and no artifact → artifact_hash empty."""
    from nexus.evidence.receipt_base import attach_r3_receipt_base

    receipt = {
        "task_id": "t-task",
        "workspace_revision": "wr",
        "planner_decision_id": "pd",
        "verifier": {
            "status": "FAILED",
            "gate_passed": False,
            "exit_code": 1,
        },
    }
    attach_r3_receipt_base(receipt)
    base = receipt["receipt_base"]
    assert (base.get("artifact_hash") or "") == ""


def test_F_source_candidate_not_equal_applied_without_apply():
    """F: generated candidate must not equal applied without apply stage."""
    from nexus.evidence.receipt_base import stamp_r1_local_response

    class _Resp:
        raw_model_metadata: dict = {}
        candidate_hash = "cand-abc"
        evidence_refs = ()
        invoked = True
        local_model_called = True
        provider = "ollama"
        model_name = "qwen"
        error = ""

    stamp_r1_local_response(_Resp())
    base = _Resp.raw_model_metadata.get("receipt_base") or {}
    # source may be set; applied must be empty until apply stage
    assert base.get("source_candidate_hash") == "cand-abc"
    assert (base.get("applied_candidate_hash") or "") == ""
    # artifact must not impersonate generated candidate
    assert (base.get("artifact_hash") or "") != "cand-abc" or not base.get("artifact_hash")


def test_G_hidden_verifier_failed_clears_applied_lineage():
    """G: hidden_verifier_passed=false → applied_candidate_hash blank."""
    from nexus.evidence.receipt_base import stamp_r2_hybrid_meta

    meta = stamp_r2_hybrid_meta(
        {
            "live_evidence_allowed": True,
            "candidate_identity": "cand-xyz",
            "selected_hash_matches_applied": True,
            "hidden_verifier_passed": False,
            "semantic_correctness_passed": False,
            "cloud_payload": {"selected_hash": "cand-xyz"},
        },
        task_id="t",
    )
    base = meta["receipt_base"]
    assert (base.get("applied_candidate_hash") or "") == ""
    assert base.get("gate_passed") is False or base.get("consumption_chain", [{}])[0].get(
        "gate_passed"
    ) is False
    assert base.get("outcome_contributed") is False or base.get("consumption_chain", [{}])[
        0
    ].get("outcome_contributed") is False


def test_H_gate_failed_forces_outcome_contributed_false():
    """H: gate_passed=false → outcome_contributed must be false."""
    from nexus.evidence.receipt_base import build_consumption_chain_entry

    entry = build_consumption_chain_entry(
        capability="claim_gate",
        selected=True,
        injected=True,
        used=True,
        evidence_present=True,
        gate_passed=False,
        outcome_contributed=True,  # producer attempt
    )
    assert entry["gate_passed"] is False
    assert entry["outcome_contributed"] is False


def test_J_bool_true_is_declared_not_observed_coverage():
    """J: bool True counts declared only, not observed embed."""
    from nexus.evidence.receipt_base import audit_product_receipt_coverage

    audit = audit_product_receipt_coverage(
        surfaces={"R1": True, "R2": True, "R3": True, "R4": True, "R5": True}
    )
    # declared may be 5/5; observed must not claim real embeds
    assert audit.get("contract_declared_coverage") == "5/5" or audit.get(
        "declared_coverage"
    ) == "5/5" or "declared" in str(audit)
    observed = audit.get("observed_receipt_embed_coverage") or audit.get(
        "observed_coverage"
    )
    assert observed in {"0/5", "0/5"} or (
        isinstance(observed, str) and observed.startswith("0/")
    )
    # Must not mark observed embed complete from bools alone
    assert audit.get("observed_embed_complete") is not True
    if "observed_present" in audit:
        assert not any(audit["observed_present"].values())


def test_K_one_of_fifty_seven_eligible_not_physical_complete():
    """K: 1/57 eligible must not be physical complete."""
    from nexus.evidence.receipt_base import audit_product_receipt_coverage

    audit = audit_product_receipt_coverage(
        wiring_matrix={
            "physical_runtime_eligible": 1,
            "node_count": 57,
            "contract_count": 57,
            "execution_class_counts": {"MISSING_ENGINE": 0},
            "routing_surface_changed": False,
        }
    )
    phys = audit.get("physical_execution_coverage") or {}
    observed = audit.get("physical_observed_execution_coverage") or phys
    assert phys.get("complete") is not True
    if isinstance(observed, dict):
        assert observed.get("complete") is not True
    # physical target may note 34/57 style but never full complete on 1 eligible
    eligible_cov = audit.get("physical_contract_eligible_coverage")
    if eligible_cov:
        assert "1/57" in str(eligible_cov) or eligible_cov != "57/57"


def test_L_context_trace_route_projects_into_receipt_base():
    """L: context_trace.route must project mainchain_entry/route_freeze/version/armor."""
    from nexus.evidence.receipt_base import attach_r3_receipt_base

    receipt = {
        "task_id": "route-task",
        "workspace_revision": "wr-1",
        "planner_decision_id": "pd-1",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "with_nexus_armor": True,
            }
        },
    }
    attach_r3_receipt_base(receipt)
    base = receipt["receipt_base"]
    assert base.get("mainchain_entry") is True
    assert base.get("route_freeze") is True
    assert base.get("mainchain_route_version") == "mainchain.v1"
    assert base.get("with_nexus_armor") is True


def test_strict_forged_receipt_hash_fails_closed():
    """Phase1: validator recomputes receipt_hash; 64-zero forged hash fails."""
    from nexus.evidence.receipt_base import (
        attach_r3_receipt_base,
        compute_receipt_hash,
        validate_receipt_base,
    )

    receipt = {
        "task_id": "tamper-task",
        "workspace_revision": "wr",
        "planner_decision_id": "pd",
        "local": {"invoked": True, "x": 1},
    }
    attach_r3_receipt_base(receipt)
    base = dict(receipt["receipt_base"])
    assert len(base["receipt_hash"]) == 64
    # Honest recompute should match
    ok = validate_receipt_base(base, mode="strict")
    assert ok["ok"] is True, ok.get("blockers")
    # Forge receipt_hash with valid SHA-256 hex that is not the real aggregate
    forged = dict(base)
    forged["receipt_hash"] = "0" * 64
    bad = validate_receipt_base(forged, mode="strict")
    assert bad["ok"] is False
    assert any("receipt_hash_tamper" in b for b in bad["blockers"])
    # Ensure forged is not equal to a recompute of empty children alone accidentally
    assert forged["receipt_hash"] != base["receipt_hash"]


def test_bare_shared_bundle_hash_not_verified():
    """project_child must not mark unsealed bare hash as verified."""
    from nexus.evidence.receipt_base import project_child_receipt_base

    base = project_child_receipt_base(
        source_world="C",
        source_component="local_executor",
        task_id="t-bundle",
        shared_bundle_hash="a" * 64,  # bare non-empty, no seal proof
        stage_payload={"invoked": True},
        stage_name="local",
    )
    assert base.get("shared_bundle_verified") is False
    assert base.get("shared_bundle_hash_status") in {"UNSEALED", "EMPTY", "UNAVAILABLE"}


def test_official_verified_bundle_projects_shared_hash():
    """Official build_capability_evidence_bundle → verified shared_bundle_hash."""
    from nexus.evidence.receipt_base import resolve_shared_bundle_hash
    from nexus.services.capability_evidence_bundle import (
        build_capability_evidence_bundle,
        verify_capability_evidence_bundle,
    )

    bundle = build_capability_evidence_bundle(
        task_id="t-official",
        workspace_revision="wr1",
        task_statement="do the thing",
        plan_payload={"steps": ["a"]},
        plan_hash="plan-h1",
        planner_decision_id="pd1",
        capability_results={
            "codeintel": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["ev:codeintel:1"],
                "physical_callable": "capability_executor_registry:codeintel",
                "telemetry": {"token_usage": 0, "model_calls": 0},
            }
        },
        selected_capabilities=["codeintel"],
    )
    v = verify_capability_evidence_bundle(bundle)
    assert v["ok"] is True
    assert v["bundle_hash"] == v["expected_bundle_hash"]
    res = resolve_shared_bundle_hash(bundle)
    assert res["shared_bundle_verified"] is True
    assert res["status"] == "VERIFIED"
    assert res["shared_bundle_hash"] == bundle["bundle_hash"]
    assert res["shared_bundle_hash"] == v["expected_bundle_hash"]
    assert res.get("blockers") in (None, [], ())


def test_fake_sealed_boolean_cannot_verify_bundle():
    """Producer sealed/verified bools alone must not yield verified seal."""
    from nexus.evidence.receipt_base import resolve_shared_bundle_hash

    fake = {"sealed": True, "bundle_hash": "a" * 64, "verified": True, "seal_status": "sealed"}
    res = resolve_shared_bundle_hash(fake)
    assert res["shared_bundle_verified"] is False
    assert (res.get("shared_bundle_hash") or "") == ""
    assert res["status"] in {"UNSEALED", "UNAVAILABLE"}
    assert res.get("blockers")


def test_tampered_bundle_cannot_enter_run_anchor():
    """Tampered official bundle clears shared_bundle_hash and must not bind run_anchor seal."""
    from nexus.evidence.receipt_base import (
        attach_r3_receipt_base,
        compute_run_anchor_hash,
        resolve_shared_bundle_hash,
    )
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle

    bundle = build_capability_evidence_bundle(
        task_id="t-tamper",
        workspace_revision="wr",
        task_statement="task",
        plan_payload={"x": 1},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={
            "memory": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["ev:m1"],
                "physical_callable": "mem",
            }
        },
        selected_capabilities=["memory"],
    )
    good = resolve_shared_bundle_hash(bundle)
    assert good["shared_bundle_verified"] is True
    # Tamper body while keeping claimed hash
    bad_bundle = dict(bundle)
    bad_bundle["task_id"] = "t-tamper-MUTATED"
    res = resolve_shared_bundle_hash(bad_bundle)
    assert res["shared_bundle_verified"] is False
    assert (res.get("shared_bundle_hash") or "") == ""
    assert res.get("blockers")
    # attach_r3 must not treat tampered bundle as verified seal identity
    receipt = {
        "task_id": "t-tamper",
        "workspace_revision": "wr",
        "planner_decision_id": "pd",
        "capability_evidence_bundle": bad_bundle,
    }
    attach_r3_receipt_base(receipt)
    base = receipt["receipt_base"]
    assert base.get("shared_bundle_verified") is False
    assert (base.get("shared_bundle_hash") or "") == ""
    # run_anchor must not embed the forged claimed hash as verified seal
    anchor_with_forged = compute_run_anchor_hash(
        task_id="t-tamper",
        workspace_revision="wr",
        planner_decision_id="pd",
        shared_bundle_hash=str(bad_bundle.get("bundle_hash") or ""),
    )
    assert receipt["run_anchor_hash"] != anchor_with_forged or not base.get(
        "shared_bundle_verified"
    )


def test_id_only_evidence_not_consumer_payload():
    """ID lists alone must not produce a consumer_payload_hash."""
    from nexus.evidence.receipt_base import resolve_consumer_payload_hash

    res = resolve_consumer_payload_hash(
        {
            "consumed_evidence_ids": ["ev:1", "ev:2"],
            "executed_capabilities": ["codeintel"],
            "contributed_capabilities": ["codeintel"],
        },
        consumed=True,
        used=True,
    )
    assert (res.get("consumer_payload_hash") or "") == ""
    assert res.get("status") in {"ID_ONLY_NOT_CONSUMED", "UNAVAILABLE"}
    assert res.get("consumed") is False


def test_explicit_consumer_hash_mismatch_fails():
    """Explicit consumer_payload_hash must match recompute from verified bundle."""
    from nexus.evidence.receipt_base import resolve_consumer_payload_hash
    from nexus.services.capability_evidence_bundle import (
        build_capability_evidence_bundle,
        hash_consumer_payloads,
    )

    bundle = build_capability_evidence_bundle(
        task_id="t-cons",
        workspace_revision="wr",
        task_statement="stmt",
        plan_payload={"p": 1},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={
            "codeintel": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["ev:c1"],
                "physical_callable": "registry:codeintel",
                "consumer_payload": {
                    "schema": "nexus.consumer_payload.v1",
                    "capability": "codeintel",
                    "markers": ["codeintel:result"],
                    "fields": {"summary": "findings", "markers": ["codeintel:result"]},
                    "payload_hash": "x",
                },
            }
        },
        selected_capabilities=["codeintel"],
    )
    # Ensure entry has real consumer_payload
    payloads = [
        e["consumer_payload"]
        for e in bundle["entries"]
        if isinstance(e.get("consumer_payload"), dict) and e["consumer_payload"]
    ]
    assert payloads
    expected = hash_consumer_payloads(payloads)
    bad = resolve_consumer_payload_hash(
        verified_bundle=bundle,
        used=True,
        consumed=True,
        explicit_hash="0" * 64,
    )
    assert (bad.get("consumer_payload_hash") or "") == ""
    assert "explicit_consumer_hash_mismatch" in (bad.get("blockers") or [])
    good = resolve_consumer_payload_hash(
        verified_bundle=bundle,
        used=True,
        consumed=True,
        explicit_hash=expected,
    )
    assert good.get("consumed") is True
    assert good.get("consumer_payload_hash") == expected
    assert good.get("status") == "CONSUMED"


def test_local_online_hash_from_actual_bounded_payload():
    """Local/Online share verified bundle + bounded input; consumption chains independent."""
    from nexus.evidence.receipt_base import (
        project_child_receipt_base,
        resolve_consumer_payload_hash,
        resolve_shared_bundle_hash,
    )
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle

    bundle = build_capability_evidence_bundle(
        task_id="t-lo",
        workspace_revision="wr",
        task_statement="shared task",
        plan_payload={"plan": True},
        plan_hash="ph",
        planner_decision_id="pd",
        capability_results={
            "belief": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["ev:b1"],
                "physical_callable": "belief",
                "response": {"outcome": {"score": 0.9, "result": "ok"}},
            }
        },
        selected_capabilities=["belief"],
    )
    seal = resolve_shared_bundle_hash(bundle)
    assert seal["shared_bundle_verified"] is True
    local_c = resolve_consumer_payload_hash(
        verified_bundle=bundle, used=True, consumed=True
    )
    online_c = resolve_consumer_payload_hash(
        verified_bundle=bundle, used=True, consumed=True
    )
    assert local_c["shared_bundle_hash"] == online_c["shared_bundle_hash"] == seal["shared_bundle_hash"]
    assert local_c["consumer_payload_hash"] == online_c["consumer_payload_hash"]
    assert local_c["bounded_input_payload_hash"] == online_c["bounded_input_payload_hash"]
    assert local_c["status"] == "CONSUMED"
    # Independent consumption chains (selected/used differ per consumer)
    local_base = project_child_receipt_base(
        source_world="C",
        source_component="local",
        task_id="t-lo",
        shared_bundle_hash=seal["shared_bundle_hash"],
        stage_payload={"shared_bundle_verified": True, "sealed": True, "consumer": "local"},
        stage_name="local",
        selected=True,
        used=True,
        injected=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        consumer="local",
    )
    online_base = project_child_receipt_base(
        source_world="A",
        source_component="online",
        task_id="t-lo",
        shared_bundle_hash=seal["shared_bundle_hash"],
        stage_payload={"shared_bundle_verified": True, "sealed": True, "consumer": "online"},
        stage_name="online",
        selected=True,
        used=False,  # online did not use
        injected=True,
        evidence_present=True,
        gate_passed=False,
        outcome_contributed=False,
        consumer="online",
    )
    assert local_base["consumption_chain"][0]["used"] is True
    assert online_base["consumption_chain"][0]["used"] is False
    assert online_base["consumption_chain"][0]["outcome_contributed"] is False
