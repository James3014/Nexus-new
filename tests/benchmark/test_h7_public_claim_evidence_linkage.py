"""
H7-5B public_claim_safe Fail-Closed + evidence_refs Linkage Tests

Gates: TG-04 / TG-05 from H7-4.

TG-04: public_claim_safe fail-closed — verify no receipt becomes public-claim-safe
       when telemetries are missing/estimated/unknown.
TG-05: evidence_refs linkage — verify public claim requires non-empty string refs
       and cannot override public_claim_allowed=false or production_ready=false.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE
- NO_PROVIDER_CALL
- NO_MODEL_CALL
- NO_MODEL_LOAD
- NO_NETWORK_CALL
- NO_PROCESS_SPAWN
- production_ready=false
- public_claim_allowed=false
- H7 runtime not started
- No production code modification

All tests are field-contract / fixture tests only.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# LOCAL TEST-ONLY HELPERS  (must NOT be moved to production code)
# ---------------------------------------------------------------------------

def _has_valid_evidence_refs(refs: object) -> bool:
    """Return True only if refs is a non-empty collection of non-empty strings."""
    if not refs:
        return False
    if not isinstance(refs, (list, tuple)):
        return False
    return all(isinstance(r, str) and r.strip() for r in refs)


def compute_final_public_claim_allowed(contract: dict[str, object]) -> bool:
    """
    Test-only helper: determines whether a receipt/contract is ultimately
    allowed to make a public claim.

    ALL conditions must hold:
    - public_claim_safe is True (computed property gate)
    - public_claim_allowed is True  (explicit governance permission)
    - production_ready is True      (system-wide readiness gate)
    - evidence_refs is non-empty list of non-empty strings
    - verifier_passed is True
    - artifact_gate_passed is True

    This helper is test-local only. Do not promote to production code.
    """
    return bool(
        contract.get("public_claim_safe") is True
        and contract.get("public_claim_allowed") is True
        and contract.get("production_ready") is True
        and _has_valid_evidence_refs(contract.get("evidence_refs"))
        and contract.get("verifier_passed") is True
        and contract.get("artifact_gate_passed") is True
    )


# ---------------------------------------------------------------------------
# IMPORT HELPERS
# ---------------------------------------------------------------------------

def _import_capability_receipt():
    from nexus.engine.capability_contracts import CapabilityReceipt
    return CapabilityReceipt


def _import_claim_boundary():
    from nexus.evidence.claim_boundary import ClaimBoundary, evaluate_claim_boundary
    return ClaimBoundary, evaluate_claim_boundary


def _import_merge_capability_receipt():
    from nexus.engine.capability_receipt_adapters import merge_capability_receipt
    return merge_capability_receipt


# ---------------------------------------------------------------------------
# MINIMAL TELEMETRY FIXTURE
# All keys required by CapabilityReceipt.public_claim_safe property.
# ---------------------------------------------------------------------------

_VALID_TELEMETRIES = {
    "wall_time_ms": 1500,
    "token_usage": 200,
    "provider_costs": 0.002,
    "overhead_ms": 50,
    "model_calls": 1,
    "telemetry_source": "measured",
}


def _make_full_receipt(*, evidence_refs=("ref:evidence:001",), **overrides):
    """
    Build a CapabilityReceipt that would be public_claim_safe=True
    under the typed property logic (all required fields set).
    Overrides allow individual field mutation for negative tests.
    """
    CapabilityReceipt = _import_capability_receipt()
    defaults = dict(
        name="test-capability",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_alignment=True,
        evidence_refs=evidence_refs,
        telemetries=dict(_VALID_TELEMETRIES),
    )
    defaults.update(overrides)
    return CapabilityReceipt(**defaults)


# ---------------------------------------------------------------------------
# TEST 1: public_claim_safe Without evidence_refs Fails Closed
# ---------------------------------------------------------------------------

class TestH75BPublicClaimSafeWithoutEvidenceRefsFailed:
    """TG-04/TG-05: public_claim_safe must be False when evidence_refs is empty."""

    def test_h7_5b_public_claim_safe_without_evidence_refs_fails_closed(self):
        """
        A receipt with all other fields satisfied but evidence_refs=() must
        have public_claim_safe=False. Empty evidence_refs means no verifiable
        source — fail closed.
        """
        receipt = _make_full_receipt(
            evidence_refs=(),         # Empty — no evidence linkage
            evidence_present=False,   # Consistent: no refs → no evidence
        )
        assert receipt.public_claim_safe is False, (
            "public_claim_safe must be False when evidence_refs is empty"
        )

    def test_h7_5b_public_claim_safe_false_when_evidence_present_false(self):
        """
        evidence_present=False must cause public_claim_safe=False,
        even if evidence_refs contains a string (integrity mismatch is fail-closed).
        """
        receipt = _make_full_receipt(
            evidence_present=False,
            evidence_refs=("ref:evidence:001",),
        )
        assert receipt.public_claim_safe is False, (
            "public_claim_safe must be False when evidence_present=False"
        )

    def test_h7_5b_compute_final_fails_without_evidence_refs(self):
        """
        compute_final_public_claim_allowed must return False when evidence_refs
        is an empty list, even if all other gates are True.
        """
        contract = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": [],          # empty — no evidence
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract) is False, (
            "compute_final_public_claim_allowed must be False when evidence_refs=[]"
        )

    @pytest.mark.parametrize("bad_refs", [
        [],
        (),
        None,
        [""],           # empty string ref
        ["   "],         # whitespace-only ref
    ])
    def test_h7_5b_invalid_evidence_refs_always_fails(self, bad_refs):
        """
        Any empty, None, or blank-string evidence_refs must cause
        compute_final_public_claim_allowed to return False.
        """
        contract = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": bad_refs,
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract) is False, (
            f"compute_final_public_claim_allowed must be False for refs={bad_refs!r}"
        )


# ---------------------------------------------------------------------------
# TEST 2: public_claim_safe Cannot Override public_claim_allowed=False
# ---------------------------------------------------------------------------

class TestH75BPublicClaimSafeCannotOverridePublicClaimAllowedFalse:
    """TG-05: public_claim_safe=True cannot override explicit public_claim_allowed=False."""

    def test_h7_5b_public_claim_safe_cannot_override_public_claim_allowed_false(self):
        """
        Even when a receipt is public_claim_safe=True (computed property),
        the explicit governance gate public_claim_allowed=False must win.
        """
        receipt = _make_full_receipt()
        # Confirm receipt is public_claim_safe=True
        assert receipt.public_claim_safe is True, (
            "Fixture should produce public_claim_safe=True for this test"
        )

        # Now apply the governance gate: public_claim_allowed=False
        contract = receipt.to_dict()
        contract["public_claim_allowed"] = False       # governance override
        contract["production_ready"] = True
        contract["verifier_passed"] = True
        contract["artifact_gate_passed"] = True
        contract["evidence_refs"] = list(receipt.evidence_refs)

        final = compute_final_public_claim_allowed(contract)
        assert final is False, (
            "public_claim_safe=True must NOT override public_claim_allowed=False"
        )

    def test_h7_5b_claim_boundary_model_calls_zero_blocks_regardless_of_receipt(self):
        """
        ClaimBoundary with model_calls=0 must block public_claim_allowed
        even if the CapabilityReceipt is public_claim_safe=True.
        H7 condition: no model calls → public claim always blocked.
        """
        _, evaluate_claim_boundary = _import_claim_boundary()
        boundary = evaluate_claim_boundary(
            simulated=False,
            claim_eligible=True,
            receipt_present=True,
            model_calls=0,   # H7: no model calls
        )
        assert boundary.public_claim_allowed is False, (
            "ClaimBoundary with model_calls=0 must block public_claim_allowed"
        )
        assert "model_calls=0" in boundary.claim_block_reason

        # Even with a public_claim_safe=True receipt, the boundary rules win
        receipt = _make_full_receipt()
        assert receipt.public_claim_safe is True

        # Combine: boundary blocks regardless of receipt's claim safety
        contract = {
            "public_claim_safe": receipt.public_claim_safe,
            "public_claim_allowed": boundary.public_claim_allowed,  # False
            "production_ready": True,
            "evidence_refs": list(receipt.evidence_refs),
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract) is False

    def test_h7_5b_claim_boundary_simulated_blocks_regardless_of_receipt(self):
        """
        ClaimBoundary with simulated=True blocks public_claim_allowed even
        if the CapabilityReceipt computes public_claim_safe=True.
        """
        _, evaluate_claim_boundary = _import_claim_boundary()
        boundary = evaluate_claim_boundary(
            simulated=True,
            claim_eligible=True,
            receipt_present=True,
            model_calls=5,
        )
        assert boundary.public_claim_allowed is False

        contract = {
            "public_claim_safe": True,
            "public_claim_allowed": boundary.public_claim_allowed,  # False
            "production_ready": True,
            "evidence_refs": ["ref:001"],
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract) is False, (
            "simulated=True must block final public claim even with public_claim_safe=True"
        )


# ---------------------------------------------------------------------------
# TEST 3: public_claim_safe Cannot Override production_ready=False
# ---------------------------------------------------------------------------

class TestH75BPublicClaimSafeCannotOverrideProductionReadyFalse:
    """TG-05: public_claim_safe=True cannot override production_ready=False."""

    def test_h7_5b_public_claim_safe_cannot_override_production_ready_false(self):
        """
        production_ready=False is a system-wide readiness gate.
        Even a receipt with public_claim_safe=True must not yield
        final public claim permission when production_ready=False.
        """
        receipt = _make_full_receipt()
        assert receipt.public_claim_safe is True

        contract = receipt.to_dict()
        contract["public_claim_allowed"] = True
        contract["production_ready"] = False          # system not ready
        contract["verifier_passed"] = True
        contract["artifact_gate_passed"] = True
        contract["evidence_refs"] = list(receipt.evidence_refs)

        assert compute_final_public_claim_allowed(contract) is False, (
            "production_ready=False must block final public claim even with "
            "public_claim_safe=True"
        )

    @pytest.mark.parametrize("field,val", [
        ("public_claim_safe",    False),
        ("public_claim_allowed", False),
        ("production_ready",     False),
        ("verifier_passed",      False),
        ("artifact_gate_passed", False),
    ])
    def test_h7_5b_any_single_false_gate_blocks_final_claim(self, field, val):
        """
        compute_final_public_claim_allowed must be False if ANY required gate
        is False. This confirms AND-logic (all gates must pass).
        """
        base = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": ["ref:evidence:001"],
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        base[field] = val
        assert compute_final_public_claim_allowed(base) is False, (
            f"compute_final_public_claim_allowed must be False when {field}={val!r}"
        )


# ---------------------------------------------------------------------------
# TEST 4: evidence_refs Must Be Non-Empty Strings
# ---------------------------------------------------------------------------

class TestH75BEvidenceRefsMustBeNonEmptyStrings:
    """TG-05: evidence_refs must be non-empty list/tuple of non-empty strings."""

    def test_h7_5b_evidence_refs_must_be_non_empty_strings(self):
        """
        _has_valid_evidence_refs must reject empty collections, None,
        non-string items, and blank strings.
        """
        # Valid cases
        assert _has_valid_evidence_refs(("ref:001",)) is True
        assert _has_valid_evidence_refs(["ref:001", "ref:002"]) is True
        assert _has_valid_evidence_refs(("ref:evidence:abc123",)) is True

        # Invalid cases
        assert _has_valid_evidence_refs([]) is False
        assert _has_valid_evidence_refs(()) is False
        assert _has_valid_evidence_refs(None) is False
        assert _has_valid_evidence_refs("") is False
        assert _has_valid_evidence_refs(["", "ref:001"]) is False   # one blank
        assert _has_valid_evidence_refs(["   "]) is False            # whitespace only
        assert _has_valid_evidence_refs([True]) is False             # boolean placeholder
        assert _has_valid_evidence_refs([1, 2]) is False             # integer refs

    def test_h7_5b_typed_receipt_evidence_refs_is_tuple_of_strings(self):
        """
        CapabilityReceipt.evidence_refs must be a tuple of strings.
        The tuple type is enforced by the frozen dataclass default.
        """
        CapabilityReceipt = _import_capability_receipt()
        # Default: empty tuple
        receipt_empty = CapabilityReceipt(name="test", selected=False)
        assert isinstance(receipt_empty.evidence_refs, tuple)
        assert len(receipt_empty.evidence_refs) == 0

        # With refs: must be tuple of strings
        receipt_with_refs = CapabilityReceipt(
            name="test",
            selected=True,
            evidence_refs=("ref:001", "ref:002"),
        )
        assert isinstance(receipt_with_refs.evidence_refs, tuple)
        assert all(isinstance(r, str) for r in receipt_with_refs.evidence_refs)

    def test_h7_5b_merge_capability_receipt_filters_empty_strings(self):
        """
        merge_capability_receipt must strip empty/blank strings from evidence_refs,
        ensuring that only valid string refs survive the merge.
        """
        merge_capability_receipt = _import_merge_capability_receipt()
        receipt = merge_capability_receipt(
            name="test-capability",
            selected=True,
            invoked=True,
            gate_passed=True,
            evidence_refs=["ref:001", "", "   ", "ref:002"],  # 2 valid, 2 bad
        )
        # All refs in the receipt must be non-empty strings
        for ref in receipt.evidence_refs:
            assert isinstance(ref, str) and ref.strip(), (
                f"Empty/blank evidence_ref survived merge: {ref!r}"
            )
        assert len(receipt.evidence_refs) >= 2, (
            "At least 2 valid refs should survive the merge"
        )


# ---------------------------------------------------------------------------
# TEST 5: Missing Verifier or Artifact Evidence Fails Closed
# ---------------------------------------------------------------------------

class TestH75BMissingVerifierOrArtifactEvidenceFailed:
    """TG-04/TG-05: missing verifier or artifact gate evidence must fail closed."""

    def test_h7_5b_missing_verifier_or_artifact_evidence_fails_closed(self):
        """
        When verifier_passed=False or artifact_gate_passed=False, the final
        public claim must be denied, even if evidence_refs is populated.
        """
        # Case 1: verifier not passed
        contract_no_verifier = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": ["ref:evidence:001"],
            "verifier_passed": False,          # verifier failed
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract_no_verifier) is False, (
            "verifier_passed=False must block final public claim"
        )

        # Case 2: artifact gate not passed
        contract_no_artifact = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": ["ref:evidence:001"],
            "verifier_passed": True,
            "artifact_gate_passed": False,     # artifact gate failed
        }
        assert compute_final_public_claim_allowed(contract_no_artifact) is False, (
            "artifact_gate_passed=False must block final public claim"
        )

    def test_h7_5b_public_claim_safe_false_when_gate_not_passed(self):
        """
        CapabilityReceipt.public_claim_safe (typed property) must be False
        when gate_passed=False, regardless of evidence_refs content.
        """
        receipt = _make_full_receipt(
            gate_passed=False,   # gate failed
        )
        assert receipt.public_claim_safe is False, (
            "public_claim_safe must be False when gate_passed=False"
        )

    def test_h7_5b_public_claim_safe_false_when_outcome_not_contributed(self):
        """
        CapabilityReceipt.public_claim_safe must be False when
        outcome_contributed=False (no measurable outcome recorded).
        """
        receipt = _make_full_receipt(
            outcome_contributed=False,
        )
        assert receipt.public_claim_safe is False, (
            "public_claim_safe must be False when outcome_contributed=False"
        )

    def test_h7_5b_public_claim_safe_false_when_telemetries_missing(self):
        """
        CapabilityReceipt.public_claim_safe must be False when telemetries is
        empty dict — no telemetry means no verifiable claim basis.
        """
        CapabilityReceipt = _import_capability_receipt()
        receipt = CapabilityReceipt(
            name="test",
            selected=True,
            invoked=True,
            evidence_present=True,
            gate_passed=True,
            outcome_contributed=True,
            evidence_alignment=True,
            evidence_refs=("ref:001",),
            telemetries={},  # empty — missing telemetry
        )
        assert receipt.public_claim_safe is False, (
            "public_claim_safe must be False when telemetries is empty"
        )

    @pytest.mark.parametrize("bad_source", ["estimated", "unknown"])
    def test_h7_5b_public_claim_safe_false_when_telemetry_source_not_measured(
        self, bad_source
    ):
        """
        TG-04: public_claim_safe must be False when telemetry_source is
        'estimated' or 'unknown' — only 'measured' telemetry is trust-eligible.
        """
        CapabilityReceipt = _import_capability_receipt()
        bad_telemetries = dict(_VALID_TELEMETRIES)
        bad_telemetries["telemetry_source"] = bad_source
        receipt = CapabilityReceipt(
            name="test",
            selected=True,
            invoked=True,
            evidence_present=True,
            gate_passed=True,
            outcome_contributed=True,
            evidence_alignment=True,
            evidence_refs=("ref:001",),
            telemetries=bad_telemetries,
        )
        assert receipt.public_claim_safe is False, (
            f"public_claim_safe must be False when telemetry_source='{bad_source}'"
        )


# ---------------------------------------------------------------------------
# TEST 6: Valid Evidence Still Requires Explicit Public Claim Permission
# ---------------------------------------------------------------------------

class TestH75BValidEvidenceStillRequiresExplicitPublicClaimPermission:
    """TG-05: having valid evidence_refs does not automatically grant public claim."""

    def test_h7_5b_valid_evidence_still_requires_explicit_public_claim_permission(self):
        """
        Even with valid evidence_refs and public_claim_safe=True, the explicit
        public_claim_allowed=True gate must still be present and True.
        Evidence alone cannot unlock public claim.
        """
        receipt = _make_full_receipt(evidence_refs=("ref:evidence:001",))
        assert receipt.public_claim_safe is True
        assert _has_valid_evidence_refs(receipt.evidence_refs) is True

        # Without explicit permission — must be False
        contract_no_permission = {
            "public_claim_safe": True,
            "public_claim_allowed": False,         # no explicit permission
            "production_ready": True,
            "evidence_refs": list(receipt.evidence_refs),
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract_no_permission) is False, (
            "Valid evidence alone must NOT grant public claim without "
            "explicit public_claim_allowed=True"
        )

        # With explicit permission — can be True
        contract_with_permission = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": list(receipt.evidence_refs),
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract_with_permission) is True, (
            "All gates satisfied should yield compute_final_public_claim_allowed=True"
        )

    def test_h7_5b_h7_phase_explicit_permission_is_always_false(self):
        """
        Under H7 conditions, public_claim_allowed must always be False because:
        - model_calls=0 (no model invocations occurred)
        - H7 runtime not started

        This test encodes the H7-phase invariant into the test suite.
        """
        _, evaluate_claim_boundary = _import_claim_boundary()

        # H7 condition: no model calls
        h7_boundary = evaluate_claim_boundary(
            simulated=False,
            claim_eligible=True,
            receipt_present=True,
            model_calls=0,
        )
        assert h7_boundary.public_claim_allowed is False, (
            "Under H7 conditions (model_calls=0), public_claim_allowed must be False"
        )

        # Therefore final public claim is impossible under H7
        contract = {
            "public_claim_safe": True,       # even if receipt says safe
            "public_claim_allowed": h7_boundary.public_claim_allowed,  # False
            "production_ready": False,        # H7: not production ready
            "evidence_refs": ["ref:001"],
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        assert compute_final_public_claim_allowed(contract) is False, (
            "H7 phase must yield compute_final_public_claim_allowed=False at all times"
        )


# ---------------------------------------------------------------------------
# TEST 7: Public Claim Boundary Contract Contains Required Keys
# ---------------------------------------------------------------------------

class TestH75BPublicClaimBoundaryContractContainsRequiredKeys:
    """TG-05: the public claim boundary contract must contain all required keys."""

    # Keys that must exist in any public claim boundary / contract dict
    REQUIRED_PUBLIC_CLAIM_CONTRACT_KEYS = [
        "public_claim_safe",
        "public_claim_allowed",
        "production_ready",
        "evidence_refs",
        "verifier_passed",
        "artifact_gate_passed",
    ]

    def test_h7_5b_public_claim_boundary_contract_contains_required_keys(self):
        """
        The local test helper compute_final_public_claim_allowed reads from
        a contract dict. Verify that the H7-phase contract template contains
        all required keys, all set to the H7-safe-default (False / empty).
        """
        h7_contract_template = {
            "public_claim_safe": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "evidence_refs": [],
            "verifier_passed": False,
            "artifact_gate_passed": False,
        }
        for key in self.REQUIRED_PUBLIC_CLAIM_CONTRACT_KEYS:
            assert key in h7_contract_template, (
                f"H7 public claim contract template missing key: '{key}'"
            )

        # With all False / empty, final result must be False
        assert compute_final_public_claim_allowed(h7_contract_template) is False, (
            "H7 default template (all False) must yield False"
        )

    def test_h7_5b_claim_boundary_to_dict_contains_public_claim_allowed(self):
        """
        ClaimBoundary.to_dict() must include public_claim_allowed key.
        This verifies the adapter output carries the required field.
        """
        ClaimBoundary, _ = _import_claim_boundary()
        boundary = ClaimBoundary(simulated=False)
        d = boundary.to_dict()
        assert "public_claim_allowed" in d, (
            "ClaimBoundary.to_dict() must contain 'public_claim_allowed'"
        )

    def test_h7_5b_capability_receipt_to_dict_contains_public_claim_safe(self):
        """
        CapabilityReceipt.to_dict() must include public_claim_safe key,
        ensuring downstream consumers can read the computed property.
        """
        receipt = _make_full_receipt(evidence_refs=("ref:001",))
        d = receipt.to_dict()
        assert "public_claim_safe" in d, (
            "CapabilityReceipt.to_dict() must contain 'public_claim_safe'"
        )
        assert isinstance(d["public_claim_safe"], bool), (
            "public_claim_safe in to_dict() must be bool"
        )

    @pytest.mark.parametrize("key", REQUIRED_PUBLIC_CLAIM_CONTRACT_KEYS)
    def test_h7_5b_required_key_is_read_by_compute_helper(self, key):
        """
        Parametrized: removing any single required key from the contract and
        calling compute_final_public_claim_allowed must return False (fail-closed
        on missing keys via dict.get defaults).
        """
        full_contract = {
            "public_claim_safe": True,
            "public_claim_allowed": True,
            "production_ready": True,
            "evidence_refs": ["ref:001"],
            "verifier_passed": True,
            "artifact_gate_passed": True,
        }
        del full_contract[key]
        # Missing key → get() returns None/falsy → must fail closed
        result = compute_final_public_claim_allowed(full_contract)
        assert result is False, (
            f"compute_final_public_claim_allowed must return False when '{key}' is missing"
        )


# ---------------------------------------------------------------------------
# FINAL STATE MARKER
# ---------------------------------------------------------------------------
# H7_5B_PUBLIC_CLAIM_EVIDENCE_LINKAGE_TESTS — tests defined above.
# Final state to be confirmed after pytest run.
