"""Unit tests for VerifiedAssistPacket + consumption_proof (shipped path, v1.1)."""

from __future__ import annotations

from nexus.services.local_substitution import build_online_safe_local_forward
from nexus.services.verified_assist_contract import (
    assert_treatment_core_equal,
    attach_verified_assist_to_forward,
    build_producer_verification,
    build_treatment_fingerprint,
    build_verified_assist_packet,
    decide_fused_slice_verdict,
    evaluate_assist_credit,
    evaluate_comparable_gate,
    evaluate_efficiency_gate,
    packet_is_substantive,
    record_packet_consumption,
    settle_main_chain,
)


def _sample_packet(**overrides):
    base = dict(
        task_id="task-vap-001",
        treatment_run_id="run-1",
        planner_decision_id="plan-1",
        task_contract_hash="contract-abc",
        producer="local_armor",
        reproduction_evidence="pytest failed on assert f()==1",
        target_files=("target.py",),
        exact_spans=("target.py:def f",),
        semantic_assertions=("f()==1",),
        failure_class="semantic",
        bounded_diagnosis="return value wrong",
        verifier_evidence="structural_ok",
        producer_verification=build_producer_verification(result="pass"),
    )
    base.update(overrides)
    return build_verified_assist_packet(**base)


def test_build_packet_is_substantive_and_hashed() -> None:
    pkt = _sample_packet()
    assert pkt.packet_role == "verified_assist"
    assert len(pkt.packet_hash) == 64
    assert packet_is_substantive(pkt) is True
    assert pkt.packet_hash in pkt.online_safe_summary()
    assert pkt.online_safe_summary().startswith("[VAP]")
    assert pkt.producer_verification.get("semantic_completion_verified") is False


def test_producer_verification_never_means_final_semantic() -> None:
    pv = build_producer_verification(result="pass")
    assert pv.semantic_completion_verified is False
    assert pv.to_dict()["semantic_completion_verified"] is False
    assert "structure" in pv.verification_scope or "localization" in pv.verification_scope


def test_empty_packet_not_substantive() -> None:
    pkt = build_verified_assist_packet(task_id="t-empty")
    assert packet_is_substantive(pkt) is False
    rec = record_packet_consumption(pkt, injected_prompt_fragment="anything")
    assert rec.consumption_status == "not_consumed"
    assert rec.assist_credit_allowed is False
    credit = evaluate_assist_credit(rec)
    assert credit["assist_credited"] is False
    assert credit["public_claim_allowed"] is False


def test_unconsumed_packet_denies_credit() -> None:
    pkt = _sample_packet()
    rec = record_packet_consumption(
        pkt,
        consumed_by_stage="online_prompt_assembly",
        injected_prompt_fragment="",
    )
    assert rec.consumption_status == "not_consumed"
    assert rec.reason == "packet_hash_not_in_injection"
    credit = evaluate_assist_credit(rec)
    assert credit["assist_credited"] is False


def test_hash_mismatch_blocks_credit() -> None:
    pkt = _sample_packet()
    rec = record_packet_consumption(
        pkt,
        consumed_by_stage="online_prompt_assembly",
        injected_prompt_fragment=f"packet_hash={pkt.packet_hash}",
        expected_packet_hash="0" * 64,
    )
    assert rec.consumption_status == "blocked"
    assert rec.reason == "packet_hash_mismatch"
    assert evaluate_assist_credit(rec)["assist_credited"] is False


def test_self_claimed_consumed_without_physical_fields_denied() -> None:
    """Receipt that only sets consumption_status without physical proof must not credit."""
    fake = {
        "consumption_status": "consumed",
        "consumption_proof": "fake",
        "packet_hash": "abc",
        "assist_credit_allowed": True,
        "packet_hash_verified": False,
        "assembled_fragment_hash": "",
        "consumer_stage": "online_prompt_assembly",
    }
    assert evaluate_assist_credit(fake)["assist_credited"] is False


def test_tampered_consumption_proof_denies_credit() -> None:
    """Honest record from record_packet_consumption; mutating proof must fail re-verify."""
    from nexus.services.verified_assist_contract import compute_consumption_proof

    pkt = _sample_packet()
    fragment = pkt.compact_injection()
    rec = record_packet_consumption(
        pkt,
        consumed_by_stage="online_prompt_assembly",
        injected_prompt_fragment=fragment,
        expected_packet_hash=pkt.packet_hash,
        final_prompt="SYS\n" + fragment,
    )
    assert evaluate_assist_credit(rec)["assist_credited"] is True
    # Tamper only the proof string
    bad = rec.to_dict()
    bad["consumption_proof"] = "deadbeef" * 8
    bad["assist_credit_allowed"] = True
    bad["packet_hash_verified"] = True
    out = evaluate_assist_credit(bad)
    assert out["assist_credited"] is False
    assert out["physical_proof_ok"] is False
    assert out["proof_verification"]["reason"] == "consumption_proof_mismatch"
    # Expected proof still matches recompute from physical fields
    expected = compute_consumption_proof(
        packet_hash=bad["packet_hash"],
        packet_id=bad["packet_id"],
        consumer_stage=bad["consumer_stage"],
        injection_slot=bad["injection_slot"],
        allowed_fields_hash=bad["allowed_fields_hash"],
        assembled_fragment_hash=bad["assembled_fragment_hash"],
        final_prompt_hash=bad["final_prompt_hash"],
    )
    assert bad["consumption_proof"] != expected


def test_forged_physical_fields_with_fake_proof_denies_credit() -> None:
    """status=consumed + all flags set + forged proof must not credit."""
    forged = {
        "consumption_status": "consumed",
        "consumption_proof": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "packet_hash": "a" * 64,
        "packet_id": "vap-forged",
        "assist_credit_allowed": True,
        "packet_hash_verified": True,
        "hash_verified": True,
        "assembled_fragment_hash": "b" * 64,
        "final_prompt_hash": "c" * 64,
        "allowed_fields_hash": "d" * 64,
        "consumer_stage": "online_prompt_assembly",
        "consumed_by_stage": "online_prompt_assembly",
        "injection_slot": "local_assist_context",
    }
    out = evaluate_assist_credit(forged)
    assert out["assist_credited"] is False
    assert out["proof_verification"]["reason"] == "consumption_proof_mismatch"


def test_forged_physical_fields_with_recomputed_but_wrong_status_denies() -> None:
    """Even with consistent proof, non-consumed status must not credit."""
    from nexus.services.verified_assist_contract import compute_consumption_proof

    fields = {
        "packet_hash": "a" * 64,
        "packet_id": "vap-x",
        "consumer_stage": "online_prompt_assembly",
        "injection_slot": "local_assist_context",
        "allowed_fields_hash": "e" * 64,
        "assembled_fragment_hash": "f" * 64,
        "final_prompt_hash": "f" * 64,
    }
    proof = compute_consumption_proof(**fields)
    rec = {
        **fields,
        "consumed_by_stage": fields["consumer_stage"],
        "consumption_status": "not_consumed",
        "consumption_proof": proof,
        "assist_credit_allowed": True,
        "packet_hash_verified": True,
    }
    assert evaluate_assist_credit(rec)["assist_credited"] is False


def test_consumed_packet_allows_credit_not_public_claim() -> None:
    pkt = _sample_packet()
    fragment = pkt.compact_injection()
    rec = record_packet_consumption(
        pkt,
        consumed_by_stage="online_prompt_assembly",
        injected_prompt_fragment=fragment,
        expected_packet_hash=pkt.packet_hash,
        final_prompt="SYSTEM\n" + fragment + "\nUSER fix it",
    )
    assert rec.consumption_status == "consumed"
    assert rec.consumption_proof
    assert rec.assembled_fragment_hash
    assert rec.final_prompt_hash
    assert rec.packet_hash_verified is True
    credit = evaluate_assist_credit(rec)
    assert credit["assist_credited"] is True
    assert credit["public_claim_allowed"] is False
    assert credit["physical_proof_ok"] is True


def test_treatment_fingerprint_b_equals_d_except_packet_flag() -> None:
    b = build_treatment_fingerprint(assist_packet_attached=False)
    d = build_treatment_fingerprint(assist_packet_attached=True)
    eq = assert_treatment_core_equal(b, d)
    assert eq["equal"] is True
    assert b.assist_packet_attached is False
    assert d.assist_packet_attached is True
    # diverge treatment config → not equal
    d2 = build_treatment_fingerprint(
        assist_packet_attached=True,
        treatment_config={"profile": "online_nexus_v1", "with_nexus": True, "extra": "sneak"},
    )
    assert assert_treatment_core_equal(b, d2)["equal"] is False


def test_attach_and_settle_main_chain_claim_false() -> None:
    pkt = _sample_packet()
    fp = build_treatment_fingerprint(assist_packet_attached=True)
    base_forward = {
        "schema": "nexus.local_substitution.online_safe_forward.v1",
        "forward": {"task_id": "task-vap-001", "action": "advisor", "concise_summary": "action=advisor"},
    }
    attached = attach_verified_assist_to_forward(base_forward, pkt, consume=True)
    assert attached["public_claim_allowed"] is False
    cons = attached["verified_assist"]["consumption"]
    assert cons["consumption_status"] == "consumed"
    assert attached["verified_assist"]["credit"]["assist_credited"] is True

    settlement = settle_main_chain(
        treatment_run_id="run-1",
        planner_decision_id="plan-1",
        task_contract_hash="contract-abc",
        final_candidate_id="cand-online-1",
        final_candidate_source="online",
        verifier_result="pass",
        consumption=cons,
        online_nexus_treatment=True,
        treatment_fingerprint=fp,
    )
    assert settlement["claim_boundary"]["public_claim_allowed"] is False
    assert settlement["claim_boundary"]["monetary_claim"] is False
    assert settlement["claim_boundary"]["assist_contributed"] is True
    assert settlement["routing_surface_changed"] is False
    assert settlement["final_candidate_source"] == "online"
    assert settlement["final_verification"]["promoted_from_producer"] is False
    assert settlement["final_verification"]["result"] == "pass"


def test_build_online_safe_local_forward_wires_packet_path() -> None:
    pkt = _sample_packet()
    stage = {
        "task_id": "task-vap-001",
        "invoked": True,
        "response": {
            "task_id": "task-vap-001",
            "action": "advisor",
            "output_delivered": True,
            "local_model_invoked": True,
            "evidence_refs": ["ref:1"],
            "consume_verified_assist": True,
            "verified_assist_packet": pkt.to_dict(),
            "candidate_summary": {},
            "verifier_summary": {"verifier_status": "not_run", "verifier_reached": False},
        },
    }
    out = build_online_safe_local_forward(stage)
    assert out["public_claim_allowed"] is False
    assert "verified_assist" in out
    assert out["verified_assist"]["consumption"]["consumption_status"] == "consumed"
    assert out["verified_assist"]["credit"]["assist_credited"] is True
    assert out["forward"].get("verified_assist_packet_hash") == pkt.packet_hash


def test_forward_without_consume_denies_credit() -> None:
    pkt = _sample_packet()
    stage = {
        "task_id": "task-vap-001",
        "response": {
            "task_id": "task-vap-001",
            "action": "advisor",
            "output_delivered": True,
            "consume_verified_assist": False,
            "verified_assist_packet": pkt.to_dict(),
            "evidence_refs": [],
            "candidate_summary": {},
            "verifier_summary": {},
        },
    }
    out = build_online_safe_local_forward(stage)
    assert out["verified_assist"]["credit"]["assist_credited"] is False
    assert out["verified_assist"]["consumption"]["consumption_status"] == "not_consumed"


def test_comparable_and_efficiency_gates() -> None:
    g = evaluate_comparable_gate(pair_count=24, comparable_count=20, infra_invalid_count=4)
    assert g["ok"] is True
    g2 = evaluate_comparable_gate(pair_count=24, comparable_count=10, infra_invalid_count=14)
    assert g2["ok"] is False
    eff = evaluate_efficiency_gate(
        b_online_input_tokens=[1000, 1000, 1000],
        d_online_input_tokens=[800, 800, 800],
    )
    assert eff["ok"] is True
    assert eff["primary_ok"] is True
    eff2 = evaluate_efficiency_gate(
        b_online_input_tokens=[1000, 1000],
        d_online_input_tokens=[990, 990],
        b_online_retry_count=[2, 2],
        d_online_retry_count=[0.5, 0.5],
    )
    assert eff2["ok"] is True  # secondary retry path


def test_decide_verdict_matrix() -> None:
    dry = decide_fused_slice_verdict(phase="dry_contract", contract_path_ok=True)
    assert dry["verdict"] == "REVISE_PACKET"
    assert dry["public_claim_allowed"] is False

    inv = decide_fused_slice_verdict(
        phase="formal",
        treatment_equal=True,
        pair_count=24,
        comparable_count=5,
        infra_invalid_count=19,
        b_solve=0.5,
        d_solve=0.5,
    )
    assert inv["verdict"] == "EXPERIMENT_INVALID"

    stop = decide_fused_slice_verdict(
        phase="formal",
        treatment_equal=True,
        pair_count=24,
        comparable_count=22,
        infra_invalid_count=2,
        b_solve=0.8,
        d_solve=0.5,
        safety_violations=0,
    )
    assert stop["verdict"] == "STOP_PACKET"

    keep = decide_fused_slice_verdict(
        phase="formal",
        treatment_equal=True,
        pair_count=24,
        comparable_count=22,
        infra_invalid_count=2,
        b_solve=0.7,
        d_solve=0.75,
        safety_violations=0,
        b_online_input_tokens=[1000] * 10,
        d_online_input_tokens=[800] * 10,
    )
    assert keep["verdict"] == "KEEP_PACKET"
    assert keep["routing_surface_changed"] is False
