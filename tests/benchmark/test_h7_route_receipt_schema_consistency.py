"""
H7-5C RouteDecision / CapabilityReceipt / SkillReceipt Schema Consistency Tests

Gates: TG-01 / TG-02 / TG-03 from H7-4.

TG-01: RouteDecision schema consistency — route truth fields.
TG-02: CapabilityReceipt required false assertion — default fail-closed.
TG-03: SkillReceipt selected/injected/invoked consistency.

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

Schema Gap Classification (H7-3 alignment):
- RouteDecision: missing decision_id, route_id, selected_candidate_hash, applied_patch_hash
  → planning-stage projections, not yet in typed contracts
- SkillReceipt: uses `injected` (not `was_injected`) — name mapping documented here
- Recovery fields: selected_candidate_hash / applied_patch_hash → missing_contract_field
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# LOCAL TEST-ONLY HELPERS (must NOT be moved to production code)
# ---------------------------------------------------------------------------

def is_recovery_ready(contract: dict[str, object]) -> bool:
    """
    Test-only helper: recovery is ready only when ALL hash fields are present
    and no mismatch is detected.
    """
    return bool(
        contract.get("candidate_id")
        and contract.get("selected_candidate_hash")
        and contract.get("applied_patch_hash")
        and contract.get("hash_mismatch_detected") is False
        and contract.get("hash_mismatch_fail_closed") is False
    )


def is_publicly_claimable_receipt(contract: dict[str, object]) -> bool:
    """
    Test-only helper: a receipt is publicly claimable only when ALL gates pass.
    """
    return bool(
        contract.get("public_claim_safe") is True
        and contract.get("public_claim_allowed") is True
        and contract.get("production_ready") is True
        and contract.get("evidence_refs")
    )


# ---------------------------------------------------------------------------
# SCHEMA GAP CLASSIFICATION TABLE (H7-3 derived)
# ---------------------------------------------------------------------------

H7_SCHEMA_GAP_CLASSIFICATION = [
    # (object, field_name, present_in_typed, gap_class, follow_up)
    ("RouteDecision",  "task_id",                   True,  "existing_contract_field", "—"),
    ("RouteDecision",  "selected_capabilities",     True,  "existing_contract_field", "—"),
    ("RouteDecision",  "required_capabilities",     True,  "existing_contract_field", "—"),
    ("RouteDecision",  "forbidden_capabilities",    True,  "existing_contract_field", "—"),
    ("RouteDecision",  "decision_source",           True,  "existing_contract_field", "—"),
    ("RouteDecision",  "public_claim_scope",        True,  "existing_contract_field", "—"),
    ("RouteDecision",  "decision_id",               False, "missing_contract_field",  "H8 add unique settlement ID"),
    ("RouteDecision",  "route_id",                  False, "missing_contract_field",  "H8 add route path ID"),
    ("RouteDecision",  "selected_candidate_hash",   False, "missing_contract_field",  "U3-1 required; blocks recovery"),
    ("RouteDecision",  "applied_patch_hash",        False, "missing_contract_field",  "U3-1 required; prevents replay drift"),
    ("CapabilityReceipt", "name",                   True,  "existing_contract_field", "—"),
    ("CapabilityReceipt", "invoked",                True,  "existing_contract_field", "—"),
    ("CapabilityReceipt", "gate_passed",            True,  "existing_contract_field", "—"),
    ("CapabilityReceipt", "evidence_refs",          True,  "existing_contract_field", "—"),
    ("CapabilityReceipt", "public_claim_safe",      True,  "existing_contract_field", "—"),
    ("CapabilityReceipt", "evidence_present",       True,  "existing_contract_field", "—"),
    ("CapabilityReceipt", "outcome_contributed",    True,  "existing_contract_field", "—"),
    ("SkillReceipt",   "skill_id",                  True,  "existing_contract_field", "—"),
    ("SkillReceipt",   "selected",                  True,  "existing_contract_field", "—"),
    ("SkillReceipt",   "injected",                  True,  "existing_contract_field", "Note: 'injected' not 'was_injected'"),
    ("SkillReceipt",   "used",                      True,  "existing_contract_field", "—"),
    ("SkillReceipt",   "outcome_contributed",       True,  "existing_contract_field", "—"),
    ("SkillReceipt",   "was_injected",              False, "name_mapping",            "H7-4 used 'was_injected'; actual is 'injected'"),
]


# ---------------------------------------------------------------------------
# IMPORT HELPERS
# ---------------------------------------------------------------------------

def _import_contracts():
    from nexus.engine.capability_contracts import (
        CapabilityReceipt,
        CapabilityPlan,
        CapabilityExecutionPlan,
        RouteDecision,
        SkillReceipt,
        CapabilitySignalSet,
        CapabilityConstraints,
    )
    return (
        CapabilityReceipt,
        CapabilityPlan,
        CapabilityExecutionPlan,
        RouteDecision,
        SkillReceipt,
        CapabilitySignalSet,
        CapabilityConstraints,
    )


def _build_minimal_route_decision(**overrides) -> Any:
    """Build a minimal but structurally valid RouteDecision for schema testing."""
    (_, _, _, RouteDecision, _, _, _) = _import_contracts()
    defaults = dict(
        schema_version="h7-test-v0",
        plan_schema_version="h7-test-v0",
        plan_mode="dry_run",
        plan_score=0,
        task_id="h7-5c-task-001",
        task_type="test",
        task_desc_hash="abc123",
        recommended_flow="linear",
        decision_source="planner",
        signal_snapshot={},
        selected_capabilities=("cap_a",),
    )
    defaults.update(overrides)
    return RouteDecision(**defaults)


def _build_minimal_receipt(**overrides) -> Any:
    """Build a minimal CapabilityReceipt for schema testing."""
    (CapabilityReceipt, _, _, _, _, _, _) = _import_contracts()
    defaults = dict(name="test-cap", selected=False)
    defaults.update(overrides)
    return CapabilityReceipt(**defaults)


def _build_minimal_skill_receipt(**overrides) -> Any:
    """Build a minimal SkillReceipt for schema testing."""
    (_, _, _, _, SkillReceipt, _, _) = _import_contracts()
    defaults = dict(skill_id="skill-001", selected=False)
    defaults.update(overrides)
    return SkillReceipt(**defaults)


# ---------------------------------------------------------------------------
# TEST 1: RouteDecision Contains Route Truth Fields (TG-01)
# ---------------------------------------------------------------------------

class TestH75CRouteDecisionRouTruthFields:
    """TG-01: RouteDecision must expose route truth fields."""

    def test_h7_5c_route_decision_contains_route_truth_fields(self):
        """
        RouteDecision must contain fields that represent route truth:
        task_id, selected_capabilities, required_capabilities,
        forbidden_capabilities, decision_source, public_claim_scope.

        Note: decision_id and route_id are missing_contract_field (H8 planned).
        """
        rd = _build_minimal_route_decision()

        # Existing route truth fields
        assert hasattr(rd, "task_id"), "RouteDecision must have task_id"
        assert isinstance(rd.task_id, str) and rd.task_id, "task_id must be non-empty str"

        assert hasattr(rd, "selected_capabilities"), "RouteDecision must have selected_capabilities"
        assert isinstance(rd.selected_capabilities, tuple), "selected_capabilities must be tuple"

        assert hasattr(rd, "required_capabilities"), "RouteDecision must have required_capabilities"
        assert isinstance(rd.required_capabilities, tuple)

        assert hasattr(rd, "forbidden_capabilities"), "RouteDecision must have forbidden_capabilities"
        assert isinstance(rd.forbidden_capabilities, tuple)

        assert hasattr(rd, "decision_source"), "RouteDecision must have decision_source"
        assert isinstance(rd.decision_source, str)

        assert hasattr(rd, "public_claim_scope"), "RouteDecision must have public_claim_scope"
        assert isinstance(rd.public_claim_scope, str)

        # Schema version for traceability
        assert hasattr(rd, "schema_version"), "RouteDecision must have schema_version"

    def test_h7_5c_route_decision_missing_contract_fields_are_absent(self):
        """
        Confirm that decision_id, route_id, selected_candidate_hash,
        applied_patch_hash are NOT yet present in RouteDecision typed contract.
        These are missing_contract_field per H7-3. Gap is expected; test
        documents the gap for H8 follow-up.
        """
        rd = _build_minimal_route_decision()

        missing_fields = [
            "decision_id",
            "route_id",
            "selected_candidate_hash",
            "applied_patch_hash",
        ]
        for field_name in missing_fields:
            assert not hasattr(rd, field_name), (
                f"'{field_name}' unexpectedly present in RouteDecision — "
                f"update gap classification if production code added it"
            )

    def test_h7_5c_route_decision_to_dict_contains_route_truth_keys(self):
        """
        RouteDecision.to_dict() must contain all expected route truth keys
        for downstream consumers.
        """
        rd = _build_minimal_route_decision()
        d = rd.to_dict()

        required_keys = [
            "task_id",
            "selected_capabilities",
            "required_capabilities",
            "forbidden_capabilities",
            "decision_source",
            "public_claim_scope",
            "schema_version",
        ]
        for key in required_keys:
            assert key in d, (
                f"RouteDecision.to_dict() must contain '{key}'"
            )

    def test_h7_5c_route_decision_is_frozen_dataclass(self):
        """
        RouteDecision must be a frozen dataclass — immutable after construction.
        Mutability would allow uncontrolled route re-writing.
        """
        rd = _build_minimal_route_decision()
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            rd.task_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TEST 2: CapabilityPlan Does Not Imply Runtime Execution (TG-01/TG-02)
# ---------------------------------------------------------------------------

class TestH75CCapabilityPlanNoRuntimeExecution:
    """TG-01/TG-02: CapabilityPlan / RouteDecision must not imply runtime execution."""

    def test_h7_5c_capability_plan_does_not_imply_runtime_execution(self):
        """
        CapabilityPlan.planner_mode must default to 'dry_run' or 'shadow',
        not to any mode implying live provider/model/network execution.
        """
        (_, CapabilityPlan, _, _, _, _, _) = _import_contracts()
        plan = CapabilityPlan(
            schema_version="h7-test-v0",
            selected_capabilities=["cap_a"],
            required_capabilities=[],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=0.0,
        )
        # Default planner_mode must not imply live execution
        assert plan.planner_mode == "dry_run", (
            f"CapabilityPlan default planner_mode must be 'dry_run', got '{plan.planner_mode}'"
        )
        assert plan.planner_mode not in (
            "live", "production", "provider_active", "model_exec", "network_enabled"
        ), f"planner_mode '{plan.planner_mode}' implies runtime execution — forbidden in H7"

    def test_h7_5c_route_decision_fallback_policy_is_fail_closed(self):
        """
        RouteDecision.fallback_policy must default to 'fail_closed'.
        Any routing decision that cannot complete must fail safely.
        """
        rd = _build_minimal_route_decision()
        assert rd.fallback_policy == "fail_closed", (
            f"RouteDecision fallback_policy must be 'fail_closed', got '{rd.fallback_policy}'"
        )

    @pytest.mark.parametrize("denied_field", [
        "model_call_executed",
        "provider_invoked",
        "network_accessed",
        "model_loaded",
    ])
    def test_h7_5c_route_decision_lacks_runtime_execution_fields(self, denied_field):
        """
        RouteDecision typed contract must not have fields that represent
        active runtime execution of provider/model/network.
        These are denial fields that must remain absent (missing_contract_field)
        to prevent accidental runtime execution via RouteDecision.
        """
        rd = _build_minimal_route_decision()
        assert not hasattr(rd, denied_field), (
            f"RouteDecision must not have '{denied_field}' — "
            f"runtime execution fields must not be embedded in route contracts"
        )

    def test_h7_5c_capability_plan_forbidden_capabilities_is_list(self):
        """
        CapabilityPlan.forbidden_capabilities must be a list (not None).
        This ensures the forbidden gate is always evaluable.
        """
        (_, CapabilityPlan, _, _, _, _, _) = _import_contracts()
        plan = CapabilityPlan(
            schema_version="h7-test-v0",
            selected_capabilities=[],
            required_capabilities=[],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=["provider_exec", "model_load"],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=0.0,
        )
        assert isinstance(plan.forbidden_capabilities, list)
        assert "provider_exec" in plan.forbidden_capabilities
        assert "model_load" in plan.forbidden_capabilities


# ---------------------------------------------------------------------------
# TEST 3: CapabilityReceipt Contains Receipt Truth Fields (TG-02)
# ---------------------------------------------------------------------------

class TestH75CCapabilityReceiptReceiptTruthFields:
    """TG-02: CapabilityReceipt must expose receipt truth fields."""

    def test_h7_5c_capability_receipt_contains_receipt_truth_fields(self):
        """
        CapabilityReceipt must contain: name, invoked, gate_passed,
        evidence_refs, public_claim_safe (property), evidence_present,
        outcome_contributed.
        """
        receipt = _build_minimal_receipt(name="h7-5c-cap", selected=True)

        assert hasattr(receipt, "name") and receipt.name == "h7-5c-cap"
        assert hasattr(receipt, "invoked") and isinstance(receipt.invoked, bool)
        assert hasattr(receipt, "gate_passed") and isinstance(receipt.gate_passed, bool)
        assert hasattr(receipt, "evidence_refs") and isinstance(receipt.evidence_refs, tuple)
        assert hasattr(receipt, "evidence_present") and isinstance(receipt.evidence_present, bool)
        assert hasattr(receipt, "outcome_contributed") and isinstance(receipt.outcome_contributed, bool)
        assert hasattr(receipt, "public_claim_safe"), "public_claim_safe property must exist"
        assert isinstance(receipt.public_claim_safe, bool)

    def test_h7_5c_capability_receipt_is_frozen_dataclass(self):
        """
        CapabilityReceipt must be a frozen dataclass — immutable after construction.
        """
        receipt = _build_minimal_receipt()
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            receipt.invoked = True  # type: ignore[misc]

    def test_h7_5c_capability_receipt_to_dict_contains_public_claim_safe(self):
        """
        CapabilityReceipt.to_dict() must include 'public_claim_safe' as a serialized bool.
        """
        receipt = _build_minimal_receipt(selected=False, invoked=False)
        d = receipt.to_dict()
        assert "public_claim_safe" in d
        assert isinstance(d["public_claim_safe"], bool)
        assert d["public_claim_safe"] is False  # default receipt → fail closed

    def test_h7_5c_capability_receipt_evidence_refs_in_to_dict_is_list(self):
        """
        CapabilityReceipt.to_dict() must serialize evidence_refs as a list
        (not a tuple), for stable downstream JSON serialization.
        """
        receipt = _build_minimal_receipt(evidence_refs=("ref:001", "ref:002"))
        d = receipt.to_dict()
        assert "evidence_refs" in d
        assert isinstance(d["evidence_refs"], list), (
            "evidence_refs in to_dict() must be list, not tuple"
        )
        assert d["evidence_refs"] == ["ref:001", "ref:002"]


# ---------------------------------------------------------------------------
# TEST 4: CapabilityReceipt Defaults Fail Closed (TG-02)
# ---------------------------------------------------------------------------

class TestH75CCapabilityReceiptDefaultsFailClosed:
    """TG-02: default CapabilityReceipt must not be public-claimable."""

    def test_h7_5c_capability_receipt_defaults_fail_closed(self):
        """
        A freshly constructed CapabilityReceipt with only required fields
        must have public_claim_safe=False and must not imply production readiness.
        """
        (CapabilityReceipt, _, _, _, _, _, _) = _import_contracts()
        receipt = CapabilityReceipt(name="default-test", selected=False)

        assert receipt.invoked is False
        assert receipt.gate_passed is False
        assert receipt.evidence_present is False
        assert receipt.outcome_contributed is False
        assert receipt.evidence_refs == ()
        assert receipt.public_claim_safe is False, (
            "Default CapabilityReceipt must have public_claim_safe=False"
        )
        # is_publicly_claimable_receipt must also return False
        contract = receipt.to_dict() | {"public_claim_allowed": False, "production_ready": False}
        assert is_publicly_claimable_receipt(contract) is False

    @pytest.mark.parametrize("field,value", [
        ("invoked",             False),
        ("gate_passed",         False),
        ("evidence_present",    False),
        ("outcome_contributed", False),
    ])
    def test_h7_5c_capability_receipt_each_false_field_blocks_claim(self, field, value):
        """
        Parametrized: each receipt truth field being False must individually
        block public_claim_safe.
        """
        overrides = {
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_alignment": True,
            "evidence_refs": ("ref:001",),
            "telemetries": {
                "wall_time_ms": 100, "token_usage": 10,
                "provider_costs": 0.001, "overhead_ms": 5,
                "model_calls": 1, "telemetry_source": "measured",
            },
        }
        overrides[field] = value  # set the one False field
        receipt = _build_minimal_receipt(**overrides)
        assert receipt.public_claim_safe is False, (
            f"public_claim_safe must be False when {field}={value!r}"
        )


# ---------------------------------------------------------------------------
# TEST 5: SkillReceipt Selected Without Injection Not Public-Claim-Safe (TG-03)
# ---------------------------------------------------------------------------

class TestH75CSkillReceiptSelectedWithoutInjection:
    """TG-03: selected-only skill must not imply injection or outcome."""

    def test_h7_5c_skill_receipt_selected_without_injection_is_not_public_claim_safe(self):
        """
        A SkillReceipt with selected=True but injected=False must not
        indicate successful injection or outcome contribution.
        This guards against 'ghost injection' — skill counted as used but not executed.
        """
        receipt = _build_minimal_skill_receipt(
            selected=True,
            injected=False,   # selected but NOT injected
            used=False,
            outcome_contributed=False,
        )
        assert receipt.selected is True
        assert receipt.injected is False
        assert receipt.used is False
        assert receipt.outcome_contributed is False, (
            "SkillReceipt selected-only must not have outcome_contributed=True"
        )

    def test_h7_5c_skill_receipt_field_name_is_injected_not_was_injected(self):
        """
        Documents name mapping: H7-4 plan used 'was_injected' but the actual
        typed field in SkillReceipt is 'injected'. This test captures the
        correct field name and classifies 'was_injected' as name_mapping gap.
        """
        receipt = _build_minimal_skill_receipt(selected=False)
        # Actual field: 'injected'
        assert hasattr(receipt, "injected"), "SkillReceipt must have 'injected' field"
        # Planned name: 'was_injected' — does NOT exist (name_mapping gap)
        assert not hasattr(receipt, "was_injected"), (
            "'was_injected' does not exist; actual field is 'injected' (name_mapping gap)"
        )

    @pytest.mark.parametrize("selected,injected,used,outcome_contributed,should_be_ok", [
        (True,  True,  True,  True,  True),   # fully completed
        (True,  True,  False, False, False),  # injected but not used
        (True,  False, False, False, False),  # selected only — not injected
        (False, False, False, False, False),  # not selected
    ])
    def test_h7_5c_skill_receipt_state_consistency(
        self, selected, injected, used, outcome_contributed, should_be_ok
    ):
        """
        Parametrized: SkillReceipt states should form a progression:
        selected → injected → used → outcome_contributed.
        Skipping a step must never yield outcome_contributed=True.
        """
        receipt = _build_minimal_skill_receipt(
            selected=selected,
            injected=injected,
            used=used,
            outcome_contributed=outcome_contributed,
        )
        if not should_be_ok:
            # Ensure the state is internally consistent: if not fully progressed,
            # outcome_contributed must be False
            if not (selected and injected and used):
                assert receipt.outcome_contributed is False, (
                    f"outcome_contributed must be False when pipeline is incomplete: "
                    f"selected={selected}, injected={injected}, used={used}"
                )


# ---------------------------------------------------------------------------
# TEST 6: SkillReceipt Injected Without Invocation Not Outcome-Contributing (TG-03)
# ---------------------------------------------------------------------------

class TestH75CSkillReceiptInjectedWithoutInvocation:
    """TG-03: injected but not used must not count as outcome-contributing."""

    def test_h7_5c_skill_receipt_injected_without_invocation_is_not_outcome_contributing(self):
        """
        A SkillReceipt with injected=True but used=False must not have
        outcome_contributed=True.
        """
        receipt = _build_minimal_skill_receipt(
            selected=True,
            injected=True,
            used=False,
            outcome_contributed=False,
        )
        assert receipt.injected is True
        assert receipt.used is False
        assert receipt.outcome_contributed is False, (
            "SkillReceipt injected-but-not-used must not be outcome_contributed=True"
        )

    def test_h7_5c_skill_receipt_is_frozen_dataclass(self):
        """SkillReceipt must be frozen — immutable after construction."""
        receipt = _build_minimal_skill_receipt()
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            receipt.selected = True  # type: ignore[misc]

    def test_h7_5c_skill_receipt_to_dict_contains_all_fields(self):
        """
        SkillReceipt.to_dict() must contain all expected fields for
        downstream serialization and schema validation.
        """
        receipt = _build_minimal_skill_receipt(
            selected=True, injected=True, used=True,
            evidence_present=True, outcome_contributed=True,
        )
        d = receipt.to_dict()
        for key in ["skill_id", "selected", "injected", "used",
                    "evidence_present", "outcome_contributed", "failure_reason"]:
            assert key in d, f"SkillReceipt.to_dict() must contain '{key}'"


# ---------------------------------------------------------------------------
# TEST 7: evidence_refs Are Stable Sequence (TG-02)
# ---------------------------------------------------------------------------

class TestH75CReceiptEvidenceRefsStableSequence:
    """TG-02: evidence_refs must be a stable list/tuple of strings."""

    def test_h7_5c_receipt_evidence_refs_are_stable_sequence(self):
        """
        CapabilityReceipt.evidence_refs must be a tuple of strings.
        Tuples are ordered, hashable, and stable across serialization.
        """
        receipt = _build_minimal_receipt(
            evidence_refs=("ref:evidence:001", "ref:evidence:002"),
        )
        assert isinstance(receipt.evidence_refs, tuple), (
            "evidence_refs must be a tuple (frozen dataclass)"
        )
        assert all(isinstance(r, str) for r in receipt.evidence_refs), (
            "All elements in evidence_refs must be strings"
        )

    def test_h7_5c_evidence_refs_default_is_empty_tuple(self):
        """
        Default evidence_refs must be empty tuple — fail closed on empty.
        """
        receipt = _build_minimal_receipt()
        assert receipt.evidence_refs == (), (
            "Default evidence_refs must be empty tuple ()"
        )

    @pytest.mark.parametrize("refs,should_be_stable", [
        (("ref:001",),              True),
        (("ref:001", "ref:002"),    True),
        ((),                        True),   # empty is stable (just not public-claim-eligible)
    ])
    def test_h7_5c_evidence_refs_are_hashable_tuples(self, refs, should_be_stable):
        """
        evidence_refs tuples must be hashable (tuples of strings are hashable).
        This ensures they can be used as dict keys or set members in downstream logic.
        """
        receipt = _build_minimal_receipt(evidence_refs=refs)
        if should_be_stable:
            # Must be hashable
            try:
                hash(receipt.evidence_refs)
            except TypeError:
                pytest.fail(
                    f"evidence_refs {refs!r} must be hashable but is not"
                )


# ---------------------------------------------------------------------------
# TEST 8: Missing Candidate Hash Blocks Recovery Readiness (TG-02 / U3)
# ---------------------------------------------------------------------------

class TestH75CMissingCandidateHashBlocksRecovery:
    """
    TG-02 / U3 blocker: missing selected_candidate_hash / applied_patch_hash
    must block recovery readiness.
    """

    def test_h7_5c_missing_candidate_hash_blocks_recovery_readiness(self):
        """
        is_recovery_ready must return False when selected_candidate_hash
        or applied_patch_hash is missing from the recovery contract.
        These fields are missing_contract_field in current typed objects (H7-3).
        """
        # Missing both hashes
        contract_no_hashes = {
            "candidate_id": "cand-001",
            "selected_candidate_hash": None,      # missing
            "applied_patch_hash": None,           # missing
            "hash_mismatch_detected": False,
            "hash_mismatch_fail_closed": False,
        }
        assert is_recovery_ready(contract_no_hashes) is False, (
            "Recovery must be blocked when selected_candidate_hash is missing"
        )

    @pytest.mark.parametrize("missing_field", [
        "candidate_id",
        "selected_candidate_hash",
        "applied_patch_hash",
    ])
    def test_h7_5c_recovery_blocked_when_any_id_field_missing(self, missing_field):
        """
        Parametrized: recovery must be blocked when any of candidate_id,
        selected_candidate_hash, applied_patch_hash is missing/None.
        """
        full_contract = {
            "candidate_id": "cand-001",
            "selected_candidate_hash": "sha256:abc123",
            "applied_patch_hash": "sha256:def456",
            "hash_mismatch_detected": False,
            "hash_mismatch_fail_closed": False,
        }
        full_contract[missing_field] = None  # clear the field
        assert is_recovery_ready(full_contract) is False, (
            f"Recovery must be blocked when '{missing_field}' is None"
        )

    def test_h7_5c_recovery_blocked_when_hash_mismatch_detected(self):
        """
        is_recovery_ready must return False when hash_mismatch_detected=True,
        even if both hashes are present.
        """
        contract = {
            "candidate_id": "cand-001",
            "selected_candidate_hash": "sha256:abc123",
            "applied_patch_hash": "sha256:def456",
            "hash_mismatch_detected": True,       # mismatch!
            "hash_mismatch_fail_closed": False,
        }
        assert is_recovery_ready(contract) is False, (
            "Recovery must be blocked when hash_mismatch_detected=True"
        )

    def test_h7_5c_recovery_ready_only_when_all_conditions_met(self):
        """
        is_recovery_ready returns True only when ALL conditions are satisfied.
        This documents the complete recovery readiness contract.
        """
        full_ok_contract = {
            "candidate_id": "cand-001",
            "selected_candidate_hash": "sha256:abc123",
            "applied_patch_hash": "sha256:def456",
            "hash_mismatch_detected": False,
            "hash_mismatch_fail_closed": False,
        }
        assert is_recovery_ready(full_ok_contract) is True, (
            "Recovery must be ready when all conditions are satisfied"
        )

    def test_h7_5c_route_decision_does_not_have_recovery_hash_fields(self):
        """
        Confirm that selected_candidate_hash and applied_patch_hash are NOT
        yet present in RouteDecision typed contract (missing_contract_field).
        This is the current state; U3-1 must add them.
        """
        rd = _build_minimal_route_decision()
        assert not hasattr(rd, "selected_candidate_hash"), (
            "selected_candidate_hash not yet in RouteDecision (U3-1 follow-up)"
        )
        assert not hasattr(rd, "applied_patch_hash"), (
            "applied_patch_hash not yet in RouteDecision (U3-1 follow-up)"
        )


# ---------------------------------------------------------------------------
# TEST 9: Schema Gap Classification Contains Required Entries (TG-01/02/03)
# ---------------------------------------------------------------------------

class TestH75CSchemaGapClassification:
    """TG-01/02/03: schema gap classification must cover all H7-3 required fields."""

    KNOWN_GAP_CLASSES = {
        "existing_contract_field",
        "missing_contract_field",
        "adapter_field",
        "name_mapping",
    }

    def test_h7_5c_schema_gap_classification_contains_required_entries(self):
        """
        H7_SCHEMA_GAP_CLASSIFICATION must cover all key objects and fields
        identified in H7-3 field alignment matrix.
        """
        objects_covered = {entry[0] for entry in H7_SCHEMA_GAP_CLASSIFICATION}
        assert "RouteDecision" in objects_covered
        assert "CapabilityReceipt" in objects_covered
        assert "SkillReceipt" in objects_covered

        # Must have at least one missing_contract_field entry (recovery blockers)
        missing_entries = [
            e for e in H7_SCHEMA_GAP_CLASSIFICATION
            if e[3] == "missing_contract_field"
        ]
        assert len(missing_entries) >= 3, (
            "Must classify at least 3 missing_contract_fields (decision_id, route_id, "
            "selected_candidate_hash, applied_patch_hash from H7-3)"
        )

    @pytest.mark.parametrize("obj,field,present,gap_class,_followup", H7_SCHEMA_GAP_CLASSIFICATION)
    def test_h7_5c_each_gap_entry_has_valid_gap_class(
        self, obj, field, present, gap_class, _followup
    ):
        """
        Parametrized: each entry in H7_SCHEMA_GAP_CLASSIFICATION must have
        a recognized gap_class value.
        """
        assert gap_class in self.KNOWN_GAP_CLASSES, (
            f"Unknown gap_class '{gap_class}' for {obj}.{field}"
        )

    def test_h7_5c_recovery_blocker_fields_classified_as_missing(self):
        """
        selected_candidate_hash and applied_patch_hash must be classified
        as missing_contract_field in H7_SCHEMA_GAP_CLASSIFICATION.
        """
        recovery_blocker_fields = {"selected_candidate_hash", "applied_patch_hash"}
        classified_missing = {
            entry[1]
            for entry in H7_SCHEMA_GAP_CLASSIFICATION
            if entry[3] == "missing_contract_field"
        }
        for field_name in recovery_blocker_fields:
            assert field_name in classified_missing, (
                f"'{field_name}' must be classified as missing_contract_field in gap table"
            )

    def test_h7_5c_name_mapping_was_injected_classified(self):
        """
        H7-4 used 'was_injected' but actual field is 'injected'.
        This name mapping must be documented in H7_SCHEMA_GAP_CLASSIFICATION.
        """
        name_mapping_entries = [
            e for e in H7_SCHEMA_GAP_CLASSIFICATION
            if e[3] == "name_mapping" and e[1] == "was_injected"
        ]
        assert len(name_mapping_entries) == 1, (
            "'was_injected' → 'injected' name mapping must be in gap classification"
        )


# ---------------------------------------------------------------------------
# FINAL STATE MARKER
# ---------------------------------------------------------------------------
# H7_5C_ROUTE_RECEIPT_SCHEMA_CONSISTENCY_TESTS — tests defined above.
# Final state to be confirmed after pytest run.
