"""M0: formal_from_pilot — pair_count>0 honest REVISE/KEEP; claim stays false."""
from __future__ import annotations

from copy import deepcopy

from nexus.services.formal_fused_projection import (
    efficiency_revise_demo_pilot,
    efficiency_revise_live_shaped_pilot,
    formal_from_pilot,
)
from nexus.services.verified_assist_contract import compute_consumption_proof


def _rehash_projection(projection: dict) -> None:
    projection["consumption_proof"] = compute_consumption_proof(
        packet_hash=projection["packet_hash"],
        packet_id=projection["packet_id"],
        consumer_stage=projection["consumer_stage"],
        injection_slot=projection["injection_slot"],
        allowed_fields_hash=projection["allowed_fields_hash"],
        assembled_fragment_hash=projection["assembled_fragment_hash"],
        final_prompt_hash=projection["final_prompt_hash"],
    )


def test_formal_from_demo_pilot_pair_count_and_honest_revise():
    # Demo/synthetic pilot is ineligible for formal M0
    demo = efficiency_revise_demo_pilot()
    demo_dec = formal_from_pilot(demo)
    assert demo_dec["phase"] == "formal"
    assert demo_dec.get("simulated") is True or demo_dec.get("formal_eligible") is False
    assert demo_dec["verdict"] == "EXPERIMENT_INVALID"
    assert demo_dec["public_claim_allowed"] is False

    pilot = efficiency_revise_live_shaped_pilot()
    decision = formal_from_pilot(pilot)
    assert decision["phase"] == "formal"
    assert int(decision["pair_count"]) > 0
    assert int(decision["comparable_count"]) > 0
    assert decision["verdict"] in {
        "REVISE_PACKET",
        "KEEP_PACKET",
        "KEEP_PACKET_SELECTIVE",
        "EXPERIMENT_INVALID",
        "STOP_PACKET",
    }
    # Empty tokens → efficiency miss → REVISE (not glue INVALID with pair_count=0)
    assert decision["verdict"] == "REVISE_PACKET"
    assert "efficiency" in str(decision.get("reason") or "").lower() or decision.get(
        "efficiency_gate", {}
    ).get("ok") is False
    assert decision["public_claim_allowed"] is False
    assert decision["routing_surface_changed"] is False
    assert decision.get("production_ready") is False
    assert decision["token_samples_numeric"] == {"b": [], "d": []}


def test_formal_unavailable_tokens_do_not_count_as_numeric():
    pilot = efficiency_revise_live_shaped_pilot()
    pilot["token_samples"] = {"b": ["UNAVAILABLE", None], "d": ["UNAVAILABLE"]}
    decision = formal_from_pilot(pilot)
    assert decision["token_samples_numeric"] == {"b": [], "d": []}
    assert decision["public_claim_allowed"] is False


def test_formal_zero_pairs_is_not_false_keep():
    pilot = {
        "schema": "nexus.fused_live_pilot.v1",
        "pair_count": 0,
        "comparable_count": 0,
        "pairs": [],
        "b_solve_mean": 1.0,
        "d_solve_mean": 1.0,
        "token_samples": {"b": [10], "d": [8]},
    }
    decision = formal_from_pilot(pilot)
    assert decision["pair_count"] == 0
    assert decision["verdict"] != "KEEP_PACKET"
    assert decision["public_claim_allowed"] is False


def test_formal_keep_still_blocks_public_claim():
    """Even if quality+efficiency pass, projection must not unlock public claim."""
    pilot = {
        "schema": "nexus.fused_live_pilot.v1",
        "pair_count": 4,
        "comparable_count": 4,
        "infra_invalid_count": 0,
        "safety_violations": 0,
        "b_solve_mean": 0.5,
        "d_solve_mean": 0.9,
        "token_samples": {"b": [100, 110, 90, 105], "d": [70, 75, 80, 65]},
        "pairs": [
            {
                "comparable": True,
                "treatment_equal": True,
                "d_assist_credited": True,
                "b_infra": False,
                "d_infra": False,
            }
            for _ in range(4)
        ],
    }
    decision = formal_from_pilot(pilot)
    assert decision["public_claim_allowed"] is False
    assert decision.get("production_ready") is False
    # If decision logic returns KEEP, claim still false
    if decision["verdict"] in {"KEEP_PACKET", "KEEP_PACKET_SELECTIVE"}:
        assert decision["public_claim_allowed"] is False


def test_I_forged_or_wrong_formal_schema_cannot_keep():
    """I: arbitrary/forged formal schema must not yield KEEP."""
    from nexus.services.formal_fused_projection import formal_from_pilot

    forged = {
        "schema": "totally.forged.pilot.v99",
        "pair_count": 4,
        "comparable_count": 4,
        "infra_invalid_count": 0,
        "safety_violations": 0,
        "b_solve_mean": 0.1,
        "d_solve_mean": 0.99,
        "token_samples": {"b": [100, 110, 90, 105], "d": [40, 45, 50, 35]},
        "pairs": [
            {
                "comparable": True,
                "treatment_equal": True,
                "d_assist_credited": True,
                "b_infra": False,
                "d_infra": False,
            }
            for _ in range(4)
        ],
    }
    decision = formal_from_pilot(forged)
    assert decision["verdict"] not in {"KEEP_PACKET", "KEEP_PACKET_SELECTIVE"}
    assert decision["verdict"] in {
        "EXPERIMENT_INVALID",
        "REVISE_PACKET",
        "STOP_PACKET",
    } or "INVALID" in str(decision["verdict"])
    assert decision["public_claim_allowed"] is False
    # Demo pilot must be simulated/ineligible for formal M0
    demo = {
        "schema": "nexus.fused_live_pilot.demo.v1",
        "pair_count": 4,
        "comparable_count": 4,
        "pairs": [{"comparable": True, "treatment_equal": True, "d_assist_credited": True}] * 4,
        "b_solve_mean": 0.2,
        "d_solve_mean": 0.9,
        "token_samples": {"b": [10, 11, 12, 13], "d": [5, 6, 7, 8]},
    }
    demo_dec = formal_from_pilot(demo)
    assert demo_dec.get("simulated") is True or demo_dec.get("formal_eligible") is False
    assert demo_dec["verdict"] not in {"KEEP_PACKET", "KEEP_PACKET_SELECTIVE"} or demo_dec.get(
        "formal_eligible"
    ) is False
    assert demo_dec["public_claim_allowed"] is False


def test_missing_provider_or_verifier_receipt_is_experiment_invalid():
    """Phase5: absent provider/verifier receipts must not yield REVISE/KEEP."""
    from nexus.services.formal_fused_projection import formal_from_pilot

    pilot = {
        "schema": "nexus.fused_live_pilot.v1",
        "task_id": "t1",
        "treatment_fingerprint": "tf1",
        "pair_count": 4,
        "comparable_count": 4,
        "infra_invalid_count": 0,
        "safety_violations": 0,
        "b_solve_mean": 0.5,
        "d_solve_mean": 0.9,
        "token_samples": {"b": [100, 110, 90, 105], "d": [70, 75, 80, 65]},
        "pairs": [
            {
                "pair_id": f"p{i}",
                "task_id": "t1",
                "comparable": True,
                "treatment_equal": True,
                "d_assist_credited": True,
                "packet_consumption_proof": {"packet_hash": "p" * 64, "consumed": True},
                "b_infra": False,
                "d_infra": False,
            }
            for i in range(4)
        ],
        # intentionally missing provider_receipt and verifier_receipt
    }
    decision = formal_from_pilot(pilot)
    assert decision["verdict"] == "EXPERIMENT_INVALID"
    assert decision["public_claim_allowed"] is False
    assert decision.get("formal_eligible") is False


def test_forged_minimal_formal_receipts_are_experiment_invalid():
    """provider confirmed / status PASS / anything packet must not be eligible."""
    from nexus.services.formal_fused_projection import formal_from_pilot

    pilot = {
        "schema": "nexus.fused_live_pilot.v1",
        "task_id": "forge",
        "treatment_fingerprint": "tf",
        "pair_count": 1,
        "comparable_count": 1,
        "b_solve_mean": 0.1,
        "d_solve_mean": 0.9,
        "token_samples": {"b": [10], "d": [5]},
        "provider_receipt": {"confirmed": True},
        "verifier_receipt": {"status": "PASS"},
        "packet_consumption_proof": {"anything": True},
        "pairs": [
            {
                "pair_id": "p0",
                "task_id": "forge",
                "comparable": True,
                "treatment_equal": True,
                "d_assist_credited": True,
            }
        ],
        "contract_path_ok": True,  # must not unlock
    }
    decision = formal_from_pilot(pilot)
    assert decision["verdict"] == "EXPERIMENT_INVALID"
    assert decision["formal_eligible"] is False
    assert decision["contract_path_ok"] is False
    assert decision["provider_receipt_verified"] is False
    assert decision["verifier_receipt_verified"] is False
    assert decision["packet_consumption_verified"] is False
    assert decision["formal_blockers"]
    assert decision["public_claim_allowed"] is False


def test_authentic_live_shaped_formal_emits_eligibility_flags():
    from nexus.services.formal_fused_projection import (
        efficiency_revise_live_shaped_pilot,
        formal_from_pilot,
    )

    decision = formal_from_pilot(efficiency_revise_live_shaped_pilot())
    assert decision["formal_eligible"] is True
    assert decision["contract_path_ok"] is True
    assert decision["provider_receipt_verified"] is True
    assert decision["verifier_receipt_verified"] is True
    assert decision["packet_consumption_verified"] is False
    assert decision["serialized_projection_verified"] is True
    assert decision["measurement_eligible"] is True
    assert decision["formal_blockers"] == []
    assert decision["public_claim_allowed"] is False
    assert decision["verdict"] == "REVISE_PACKET"


def test_product_credit_assertion_cannot_enter_formal_projection() -> None:
    pilot = efficiency_revise_live_shaped_pilot()
    forged = deepcopy(pilot)
    forged["pairs"][0]["d_assist_credited"] = True

    decision = formal_from_pilot(forged)

    assert decision["verdict"] == "EXPERIMENT_INVALID"
    assert decision["formal_eligible"] is False
    assert decision["packet_consumption_verified"] is False
    assert decision["serialized_projection_verified"] is True
    assert decision["measurement_eligible"] is False
    assert any(
        "product_assist_credit_forbidden_in_projection" in blocker
        for blocker in decision["formal_blockers"]
    )
    assert decision["public_claim_allowed"] is False


def test_malformed_declared_packet_hashes_fail_closed() -> None:
    for source in ("pilot", "vap", "assist", "projection"):
        pilot = efficiency_revise_live_shaped_pilot()
        if source == "pilot":
            pilot["packet_hash"] = "not-a-sha"
        elif source in {"vap", "assist"}:
            pilot[f"{source}_packet"] = {
                "packet_hash": "not-a-sha",
                "packet_id": pilot["packet_id"],
            }
        else:
            projection = pilot["packet_consumption_proof"]
            projection["packet_hash"] = "not-a-sha"
            _rehash_projection(projection)

        decision = formal_from_pilot(pilot)

        assert decision["formal_eligible"] is False
        assert decision["measurement_eligible"] is False
        assert decision["public_claim_allowed"] is False
        assert any(
            f"{source}_packet_hash_not_sha256" in blocker
            or "packet_hash_not_sha256" in blocker
            for blocker in decision["formal_blockers"]
        )


def test_mismatched_declared_packet_hashes_fail_closed() -> None:
    for source in ("pilot", "vap", "assist", "projection"):
        pilot = efficiency_revise_live_shaped_pilot()
        foreign_hash = "e" * 64
        if source == "pilot":
            pilot["packet_hash"] = foreign_hash
        elif source in {"vap", "assist"}:
            pilot[f"{source}_packet"] = {
                "packet_hash": foreign_hash,
                "packet_id": pilot["packet_id"],
            }
        else:
            projection = pilot["packet_consumption_proof"]
            projection["packet_hash"] = foreign_hash
            _rehash_projection(projection)

        decision = formal_from_pilot(pilot)

        assert decision["formal_eligible"] is False
        assert decision["measurement_eligible"] is False
        assert decision["public_claim_allowed"] is False
        assert any("packet_hash_mismatch" in blocker for blocker in decision["formal_blockers"])


def test_authoritative_packet_identity_cannot_come_from_projection_alone() -> None:
    pilot = efficiency_revise_live_shaped_pilot()
    pilot.pop("packet_hash")
    pilot.pop("packet_id")
    pilot.pop("vap_packet")

    decision = formal_from_pilot(pilot)

    assert decision["formal_eligible"] is False
    assert "declared_packet_hash_missing" in decision["formal_blockers"]
    assert "declared_packet_id_missing" in decision["formal_blockers"]


def test_present_null_or_empty_declared_identity_fails_closed() -> None:
    for source in ("pilot", "vap", "assist"):
        for field in ("packet_hash", "packet_id"):
            for value in (None, ""):
                pilot = efficiency_revise_live_shaped_pilot()
                if source == "pilot":
                    pilot[field] = value
                else:
                    pilot[f"{source}_packet"] = {
                        "packet_hash": pilot["packet_hash"],
                        "packet_id": pilot["packet_id"],
                        field: value,
                    }

                decision = formal_from_pilot(pilot)

                assert decision["formal_eligible"] is False
                assert decision["measurement_eligible"] is False
                assert any(
                    f"{source}_{field}" in blocker
                    for blocker in decision["formal_blockers"]
                )


def test_present_non_mapping_vap_or_assist_identity_fails_closed() -> None:
    for source in ("vap", "assist"):
        for value in (None, "not-a-mapping", []):
            pilot = efficiency_revise_live_shaped_pilot()
            pilot[f"{source}_packet"] = value

            decision = formal_from_pilot(pilot)

            assert decision["formal_eligible"] is False
            assert f"{source}_packet_not_mapping" in decision["formal_blockers"]
            assert decision["public_claim_allowed"] is False


def test_pilot_and_pair_projection_packet_ids_are_bound() -> None:
    for source in ("pilot", "vap", "assist", "projection", "pair"):
        pilot = efficiency_revise_live_shaped_pilot()
        if source == "pilot":
            pilot["packet_id"] = "foreign-pilot-id"
        elif source in {"vap", "assist"}:
            pilot[f"{source}_packet"] = {
                "packet_hash": pilot["packet_hash"],
                "packet_id": f"foreign-{source}-id",
            }
        elif source == "projection":
            projection = pilot["packet_consumption_proof"]
            projection["packet_id"] = "foreign-projection-id"
            _rehash_projection(projection)
        else:
            projection = deepcopy(pilot["pairs"][0]["packet_consumption_proof"])
            projection["packet_id"] = "foreign-pair-id"
            _rehash_projection(projection)
            pilot["pairs"][0]["packet_consumption_proof"] = projection

        decision = formal_from_pilot(pilot)

        assert decision["formal_eligible"] is False
        assert decision["measurement_eligible"] is False
        assert decision["public_claim_allowed"] is False
        assert any("packet_id_mismatch" in blocker for blocker in decision["formal_blockers"])


def test_pair_task_identity_must_match_pilot_identity() -> None:
    pilot = efficiency_revise_live_shaped_pilot()
    for pair in pilot["pairs"]:
        pair["task_id"] = "foreign-task"

    decision = formal_from_pilot(pilot)

    assert decision["formal_eligible"] is False
    assert decision["measurement_eligible"] is False
    assert any(
        "pair_task_identity_mismatch" in blocker
        for blocker in decision["formal_blockers"]
    )


def test_pilot_and_pairs_cannot_be_relabelled_away_from_packet_task() -> None:
    pilot = efficiency_revise_live_shaped_pilot()
    pilot["task_id"] = "foreign-task"
    for pair in pilot["pairs"]:
        pair["task_id"] = "foreign-task"

    decision = formal_from_pilot(pilot)

    assert decision["formal_eligible"] is False
    assert decision["measurement_eligible"] is False
    assert "pilot_task_identity_mismatch_packet" in decision["formal_blockers"]
    assert decision["public_claim_allowed"] is False


def test_packet_pilot_and_pairs_cannot_be_coherently_relabelled_without_rehash() -> None:
    pilot = efficiency_revise_live_shaped_pilot()
    pilot["vap_packet"]["task_id"] = "foreign-task"
    pilot["task_id"] = "foreign-task"
    for pair in pilot["pairs"]:
        pair["task_id"] = "foreign-task"

    decision = formal_from_pilot(pilot)

    assert decision["formal_eligible"] is False
    assert decision["measurement_eligible"] is False
    assert any(
        "vap_packet_integrity:packet_hash_mismatch" in blocker
        for blocker in decision["formal_blockers"]
    )
    assert decision["public_claim_allowed"] is False


def test_formal_requires_complete_canonical_vap_serialization() -> None:
    cases: list[dict] = []
    for field in ("schema_version", "packet_role", "exact_spans"):
        pilot = efficiency_revise_live_shaped_pilot()
        pilot["vap_packet"].pop(field)
        cases.append(pilot)
    for field, value in (
        ("schema_version", "wrong.schema"),
        ("packet_role", "wrong-role"),
        ("target_files", ("formal-target.py",)),
    ):
        pilot = efficiency_revise_live_shaped_pilot()
        pilot["vap_packet"][field] = value
        cases.append(pilot)

    for pilot in cases:
        decision = formal_from_pilot(pilot)
        assert decision["formal_eligible"] is False
        assert decision["measurement_eligible"] is False
        assert any(
            "vap_packet_integrity:" in blocker
            for blocker in decision["formal_blockers"]
        )
        assert decision["public_claim_allowed"] is False


def test_present_packet_task_identity_is_required_and_cross_bound() -> None:
    for source in ("vap", "assist"):
        for value in (None, "", "foreign-task"):
            pilot = efficiency_revise_live_shaped_pilot()
            pilot[f"{source}_packet"] = {
                "task_id": value,
                "packet_hash": pilot["packet_hash"],
                "packet_id": pilot["packet_id"],
            }

            decision = formal_from_pilot(pilot)

            assert decision["formal_eligible"] is False
            assert decision["measurement_eligible"] is False
            assert any(
                "packet_task" in blocker
                or "task_identity" in blocker
                or "packet_integrity" in blocker
                for blocker in decision["formal_blockers"]
            )


def test_present_invalid_pair_task_or_projection_does_not_inherit() -> None:
    for field, values in (
        ("task_id", (None, "")),
        (
            "packet_consumption_proof",
            (None, {}, "", [], False, 0, "not-a-mapping"),
        ),
    ):
        for value in values:
            pilot = efficiency_revise_live_shaped_pilot()
            pilot["pairs"][0][field] = value

            decision = formal_from_pilot(pilot)

            assert decision["formal_eligible"] is False
            assert decision["measurement_eligible"] is False
            if field == "packet_consumption_proof":
                assert decision["serialized_projection_verified"] is False
            else:
                assert any(
                    "pair_task_identity_missing" in blocker
                    for blocker in decision["formal_blockers"]
                )
            assert decision["public_claim_allowed"] is False


def test_absent_pair_projection_explicitly_inherits_pilot_projection() -> None:
    pilot = efficiency_revise_live_shaped_pilot()
    for pair in pilot["pairs"]:
        pair.pop("packet_consumption_proof")

    decision = formal_from_pilot(pilot)

    assert decision["formal_eligible"] is True
    assert decision["serialized_projection_verified"] is True
    assert decision["measurement_eligible"] is True
    assert decision["public_claim_allowed"] is False
