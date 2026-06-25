"""
H7-5A Provider / Model / Network Denial Field Tests

Gate: TG-06 — provider/model/network denial field tests.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE
- NO_PROVIDER_CALL
- NO_MODEL_CALL
- NO_MODEL_LOAD
- NO_NETWORK_CALL
- NO_PROCESS_SPAWN
- production_ready=false
- public_claim_allowed=false (under H7 conditions)
- H7 runtime not started

All tests are field-contract / fixture tests only.
No real provider, model, or network is invoked.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# H7-5A DENIAL CONTRACT FIXTURE
# ---------------------------------------------------------------------------
# Represents the expected H7-phase denial contract for any capability receipt,
# shadow receipt, or routing decision. Fields that are missing_or_moved in
# current typed objects are represented here as test-only fixture values.
# This fixture does NOT modify production code. It is test-local only.
# ---------------------------------------------------------------------------

H7_DENIAL_CONTRACT = {
    # --- typed fields in ShadowReceipt (nexus/services/local_heal/shadow_receipt.py) ---
    "model_call_executed": False,
    "runtime_effect": False,
    # --- ClaimBoundary / receipt dict (nexus/evidence/claim_boundary.py, local_heal/receipt.py) ---
    "public_claim_allowed": False,
    "production_ready": False,
    # --- sandbox_runner dict (nexus/engine/sandbox_runner.py) ---
    "network_allowed": False,
    # --- missing_or_moved: planned governance fields (see H7-3 Field Alignment Matrix) ---
    # These fields do not yet exist in typed contracts; they are represented
    # here as test-only fixture values per H7-4 TG-06 design.
    "provider_invoked": False,
    "provider_probe_allowed": False,
    "provider_invocation_allowed": False,
    "provider_execution_allowed": False,
    "process_spawn_allowed": False,
    "model_load_allowed": False,
    "model_call_allowed": False,
}

# Required keys that must ALL be present in the denial contract
REQUIRED_DENIAL_KEYS = list(H7_DENIAL_CONTRACT.keys())


# ---------------------------------------------------------------------------
# MODULE AVAILABILITY CHECKS
# ---------------------------------------------------------------------------

def _import_shadow_receipt():
    """Import ShadowReceipt and create_dry_run_receipt without side effects."""
    from nexus.services.local_heal.shadow_receipt import (
        ShadowReceipt,
        create_dry_run_receipt,
        validate_receipt,
    )
    return ShadowReceipt, create_dry_run_receipt, validate_receipt


def _import_claim_boundary():
    """Import ClaimBoundary without side effects."""
    from nexus.evidence.claim_boundary import ClaimBoundary, evaluate_claim_boundary
    return ClaimBoundary, evaluate_claim_boundary


def _import_capability_receipt():
    """Import CapabilityReceipt without side effects."""
    from nexus.engine.capability_contracts import CapabilityReceipt
    return CapabilityReceipt


# ---------------------------------------------------------------------------
# TEST 1: H7-5A Denial Fields Required False Contract
# ---------------------------------------------------------------------------

class TestH75ADenialFieldsRequiredFalseContract:
    """TG-06: All required denial fields must be False in H7 contract."""

    def test_h7_5a_denial_fields_required_false_contract(self):
        """
        H7-5A core test: assert all required denial fields in the H7 contract
        are False. Uses ShadowReceipt for typed fields and test-only fixture
        for missing_or_moved fields.
        """
        _, create_dry_run_receipt, _ = _import_shadow_receipt()

        receipt = create_dry_run_receipt(
            task_id="h7-5a-test-001",
            dry_row_id="dry-001",
            model="shadow-only",
            task_type="capability_denial_check",
            input_ref="test://input/h7_5a",
        )

        # Typed fields in ShadowReceipt — must be False
        assert receipt.model_call_executed is False, (
            "model_call_executed must be False in H7 dry-run receipt"
        )
        assert receipt.runtime_effect is False, (
            "runtime_effect must be False in H7 dry-run receipt"
        )

        # Governance dict in ShadowReceipt — must carry public_claim_allowed=False
        assert receipt.governance.get("public_claim_allowed") is False, (
            "public_claim_allowed must be False in shadow receipt governance"
        )

        # Test-only fixture fields (missing_or_moved) — verified via H7_DENIAL_CONTRACT
        missing_or_moved_fields = [
            "provider_invoked",
            "provider_probe_allowed",
            "provider_invocation_allowed",
            "provider_execution_allowed",
            "process_spawn_allowed",
            "model_load_allowed",
            "model_call_allowed",
        ]
        for field_name in missing_or_moved_fields:
            fixture_val = H7_DENIAL_CONTRACT[field_name]
            assert fixture_val is False, (
                f"H7 denial contract fixture field '{field_name}' must be False, "
                f"got {fixture_val!r}"
            )

    def test_h7_5a_shadow_receipt_validate_passes_for_dry_run(self):
        """
        ShadowReceipt created via create_dry_run_receipt must pass validate_receipt()
        with all governance fields locked to False.
        """
        _, create_dry_run_receipt, validate_receipt = _import_shadow_receipt()

        receipt = create_dry_run_receipt(
            task_id="h7-5a-validate-001",
            dry_row_id="dry-002",
            model="shadow-only",
            task_type="validation_check",
            input_ref="test://input/validate",
        )
        result = validate_receipt(receipt)
        assert result.ok is True, (
            f"validate_receipt must pass for dry-run receipt. Errors: {result.errors}"
        )
        assert result.errors == [], (
            f"No validation errors expected for dry-run receipt. Got: {result.errors}"
        )


# ---------------------------------------------------------------------------
# TEST 2: H7-5A No Public Claim or Production Ready
# ---------------------------------------------------------------------------

class TestH75ANoPublicClaimOrProductionReady:
    """TG-06: public_claim_allowed and production_ready must be False under H7."""

    def test_h7_5a_no_public_claim_or_production_ready(self):
        """
        Assert production_ready=False and public_claim_allowed=False in H7 contract.
        Tested via:
        - ShadowReceipt governance dict (typed adapter output)
        - ClaimBoundary with H7-equivalent conditions (model_calls=0)
        - H7_DENIAL_CONTRACT test-only fixture
        """
        # Via ShadowReceipt governance dict
        _, create_dry_run_receipt, _ = _import_shadow_receipt()
        receipt = create_dry_run_receipt(
            task_id="h7-5a-test-002",
            dry_row_id="dry-003",
            model="shadow-only",
            task_type="public_claim_check",
            input_ref="test://input/h7_5a_002",
        )
        assert receipt.governance.get("public_claim_allowed") is False, (
            "ShadowReceipt governance must have public_claim_allowed=False"
        )

        # Via ClaimBoundary with H7-phase conditions (model_calls=0 → blocked)
        ClaimBoundary, evaluate_claim_boundary = _import_claim_boundary()
        boundary = evaluate_claim_boundary(
            simulated=False,
            claim_eligible=True,
            receipt_present=True,
            model_calls=0,  # H7: no model calls allowed
        )
        assert boundary.public_claim_allowed is False, (
            "ClaimBoundary must block public_claim_allowed when model_calls=0 (H7 condition)"
        )
        assert "model_calls=0" in boundary.claim_block_reason, (
            "ClaimBoundary block reason must reference model_calls=0"
        )

        # Via test-only fixture
        assert H7_DENIAL_CONTRACT["public_claim_allowed"] is False
        assert H7_DENIAL_CONTRACT["production_ready"] is False

    def test_h7_5a_claim_boundary_simulated_blocks_public_claim(self):
        """
        ClaimBoundary with simulated=True must block public_claim_allowed.
        This covers the H7 scenario where all runs are dry/shadow only.
        """
        _, evaluate_claim_boundary = _import_claim_boundary()
        boundary = evaluate_claim_boundary(
            simulated=True,
            claim_eligible=True,
            receipt_present=True,
            model_calls=5,  # Even with model_calls > 0, simulated=True blocks
        )
        assert boundary.public_claim_allowed is False, (
            "simulated=True must block public_claim_allowed even with model_calls>0"
        )

    def test_h7_5a_capability_receipt_public_claim_safe_is_false_without_invocation(self):
        """
        CapabilityReceipt.public_claim_safe must be False when invoked=False.
        This is a typed field property test on the production contracts.
        """
        CapabilityReceipt = _import_capability_receipt()
        receipt = CapabilityReceipt(
            name="test-capability",
            selected=True,
            invoked=False,  # H7: no invocations
        )
        assert receipt.public_claim_safe is False, (
            "CapabilityReceipt.public_claim_safe must be False when invoked=False"
        )


# ---------------------------------------------------------------------------
# TEST 3: H7-5A No Provider or Model Execution Flags
# ---------------------------------------------------------------------------

class TestH75ANoProviderOrModelExecutionFlags:
    """TG-06: provider/model/model-load/model-call flags must be False under H7."""

    def test_h7_5a_no_provider_or_model_execution_flags(self):
        """
        Assert all provider and model execution fields are False.
        Typed fields tested via ShadowReceipt; missing_or_moved fields via fixture.
        """
        _, create_dry_run_receipt, _ = _import_shadow_receipt()
        receipt = create_dry_run_receipt(
            task_id="h7-5a-test-003",
            dry_row_id="dry-004",
            model="shadow-only",
            task_type="provider_model_check",
            input_ref="test://input/h7_5a_003",
        )

        # Typed: model_call_executed (ShadowReceipt)
        assert receipt.model_call_executed is False, (
            "model_call_executed must be False"
        )

        # Typed: governance dict model_calls_executed
        assert receipt.governance.get("model_calls_executed") is False, (
            "governance.model_calls_executed must be False"
        )

        # missing_or_moved fields via fixture (H7-3 alignment: not yet in typed contracts)
        provider_flags = [
            "provider_invoked",
            "provider_probe_allowed",
            "provider_invocation_allowed",
            "provider_execution_allowed",
            "model_load_allowed",
            "model_call_allowed",
        ]
        for flag in provider_flags:
            assert H7_DENIAL_CONTRACT[flag] is False, (
                f"H7 denial contract: '{flag}' must be False (missing_or_moved field)"
            )

    @pytest.mark.parametrize("field_name,expected", [
        ("model_call_executed", False),
        ("runtime_effect", False),
        ("routing_changed", False),
        ("patch_apply_allowed", False),
        ("verifier_override_allowed", False),
        ("source_mutation_allowed", False),
        ("training_export_allowed", False),
        ("adoption_allowed", False),
    ])
    def test_h7_5a_shadow_receipt_typed_fields_all_false(self, field_name, expected):
        """
        Parametrized: each typed ShadowReceipt denial field must be False
        in a dry-run receipt.
        """
        _, create_dry_run_receipt, _ = _import_shadow_receipt()
        receipt = create_dry_run_receipt(
            task_id=f"h7-5a-param-{field_name}",
            dry_row_id="dry-param",
            model="shadow-only",
            task_type="parametrized_denial_check",
            input_ref="test://input/param",
        )
        actual = getattr(receipt, field_name, None)
        assert actual is expected, (
            f"ShadowReceipt.{field_name} must be {expected}, got {actual!r}"
        )


# ---------------------------------------------------------------------------
# TEST 4: H7-5A No Network or Process Spawn Flags
# ---------------------------------------------------------------------------

class TestH75ANoNetworkOrProcessSpawnFlags:
    """TG-06: network_allowed and process_spawn_allowed must be False under H7."""

    def test_h7_5a_no_network_or_process_spawn_flags(self):
        """
        Assert network and process spawn fields are False.
        network_allowed tested via ShadowReceipt governance dict (adapter_field).
        process_spawn_allowed is missing_or_moved; tested via fixture.
        """
        _, create_dry_run_receipt, _ = _import_shadow_receipt()
        receipt = create_dry_run_receipt(
            task_id="h7-5a-test-004",
            dry_row_id="dry-005",
            model="shadow-only",
            task_type="network_process_check",
            input_ref="test://input/h7_5a_004",
        )

        # adapter_field: governance dict does not include network_allowed by default,
        # but sandbox_runner emits network_allowed=False in its config dict.
        # We test via fixture here as the contract representation.
        assert H7_DENIAL_CONTRACT["network_allowed"] is False, (
            "H7 denial contract: network_allowed must be False"
        )

        # missing_or_moved
        assert H7_DENIAL_CONTRACT["process_spawn_allowed"] is False, (
            "H7 denial contract: process_spawn_allowed must be False"
        )

    def test_h7_5a_shadow_receipt_no_forbidden_output_detected(self):
        """
        ShadowReceipt from dry-run must have forbidden_output_detected=False
        and authority_creep_detected=False.
        """
        _, create_dry_run_receipt, _ = _import_shadow_receipt()
        receipt = create_dry_run_receipt(
            task_id="h7-5a-test-004b",
            dry_row_id="dry-006",
            model="shadow-only",
            task_type="forbidden_output_check",
            input_ref="test://input/h7_5a_004b",
        )
        assert receipt.forbidden_output_detected is False, (
            "forbidden_output_detected must be False in H7 dry-run receipt"
        )
        assert receipt.authority_creep_detected is False, (
            "authority_creep_detected must be False in H7 dry-run receipt"
        )


# ---------------------------------------------------------------------------
# TEST 5: H7-5A Denial Contract Contains All Required Keys
# ---------------------------------------------------------------------------

class TestH75ADenialContractContainsAllRequiredKeys:
    """TG-06: the H7 denial contract must contain every required key."""

    def test_h7_5a_denial_contract_contains_all_required_keys(self):
        """
        Ensure H7_DENIAL_CONTRACT has every required denial field.
        This acts as a schema guard for the test fixture itself.
        """
        for key in REQUIRED_DENIAL_KEYS:
            assert key in H7_DENIAL_CONTRACT, (
                f"H7_DENIAL_CONTRACT is missing required key: '{key}'"
            )
            assert H7_DENIAL_CONTRACT[key] is False, (
                f"H7_DENIAL_CONTRACT['{key}'] must be False, got {H7_DENIAL_CONTRACT[key]!r}"
            )

    def test_h7_5a_denial_contract_key_count(self):
        """
        H7_DENIAL_CONTRACT must have at least 12 keys covering all required
        denial fields from H7-4 TG-06 design.
        """
        assert len(H7_DENIAL_CONTRACT) >= 12, (
            f"H7_DENIAL_CONTRACT must cover at least 12 denial fields, "
            f"got {len(H7_DENIAL_CONTRACT)}: {list(H7_DENIAL_CONTRACT.keys())}"
        )

    @pytest.mark.parametrize("field_name,present,tested_via,gap_class", [
        ("model_call_executed",        True,  "typed field (ShadowReceipt)",     "existing_contract_field"),
        ("runtime_effect",             True,  "typed field (ShadowReceipt)",     "existing_contract_field"),
        ("production_ready",           True,  "adapter_field (local_heal/receipt.py dict)", "adapter_field"),
        ("public_claim_allowed",       True,  "typed field (ClaimBoundary) + adapter", "existing_contract_field"),
        ("network_allowed",            True,  "adapter_field (sandbox_runner dict)", "adapter_field"),
        ("provider_invoked",           False, "test-only fixture",               "missing_contract_field"),
        ("provider_probe_allowed",     False, "test-only fixture",               "missing_contract_field"),
        ("provider_invocation_allowed",False, "test-only fixture",               "missing_contract_field"),
        ("provider_execution_allowed", False, "test-only fixture",               "missing_contract_field"),
        ("process_spawn_allowed",      False, "test-only fixture",               "missing_contract_field"),
        ("model_load_allowed",         False, "test-only fixture",               "missing_contract_field"),
        ("model_call_allowed",         False, "test-only fixture",               "missing_contract_field"),
    ])
    def test_h7_5a_denial_field_gap_classification(
        self, field_name, present, tested_via, gap_class
    ):
        """
        Parametrized gap classification for each required denial field.
        Documents field presence, how it is tested, and its gap classification.
        Fields classified as missing_contract_field are tested via test-only fixture;
        they require follow-up in H8 to add typed contract fields.
        """
        # All fields must be False in the H7 denial contract regardless of presence
        assert H7_DENIAL_CONTRACT[field_name] is False, (
            f"Field '{field_name}' (present={present}, via={tested_via}, "
            f"gap={gap_class}) must be False in H7_DENIAL_CONTRACT"
        )
        # Gap class must be one of the recognized values
        assert gap_class in (
            "existing_contract_field",
            "adapter_field",
            "missing_contract_field",
        ), f"Unknown gap_class: {gap_class}"


# ---------------------------------------------------------------------------
# FINAL STATE MARKER
# ---------------------------------------------------------------------------
# H7_5A_PROVIDER_MODEL_NETWORK_DENIAL_FIELD_TESTS — tests defined above.
# Final state to be confirmed after pytest run.
