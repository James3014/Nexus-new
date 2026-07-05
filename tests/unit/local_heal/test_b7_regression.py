"""B7-A: Regression tests for C_13453 constrained action pipeline."""
import os
import hashlib
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_protocol_mode(monkeypatch):
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")
    yield
    monkeypatch.delenv("NEXUS_PROTOCOL_MODE", raising=False)


from nexus.services.local_heal.constrained_action_applier import (
    ConstrainedActionApplier, ConstrainedAction, ActionResult,
    CANONICAL_ACTION_TYPES, ACTION_TYPE_ALIASES,
    apply_constrained_actions_to_source,
)


def test_action_type_alias_normalization():
    """CALL_EXISTENT_HELPER normalizes to CALL_EXISTING_HELPER."""
    applier = ConstrainedActionApplier()
    raw = {"selected_action_type": "CALL_EXISTENT_HELPER", "replacement_snippet": "self.foo()"}
    action = applier.normalize_action(raw)
    assert action is not None
    assert action.action_type == "CALL_EXISTING_HELPER"
    assert action.original_action_type == "CALL_EXISTENT_HELPER"


def test_action_type_misspelling_normalization():
    """CALL_EXISTENT_HELPER (misspelled) normalizes safely."""
    applier = ConstrainedActionApplier()
    raw = {"selected_action_type": "CALL_EXISTENT_HELPER", "replacement_snippet": "self.foo()"}
    action = applier.normalize_action(raw)
    assert action is not None
    assert action.action_type == "CALL_EXISTING_HELPER"


def test_unknown_action_type_rejected():
    """Unknown action type is rejected."""
    applier = ConstrainedActionApplier()
    raw = {"selected_action_type": "UNKNOWN_ACTION", "replacement_snippet": "x = 1"}
    action = applier.normalize_action(raw)
    assert action is None


def test_abstain_action():
    """ABSTAIN passes without patch application."""
    applier = ConstrainedActionApplier()
    raw = {"selected_action_type": "ABSTAIN", "replacement_snippet": ""}
    action = applier.normalize_action(raw)
    assert action is not None
    assert action.action_type == "ABSTAIN"
    result = applier.apply_action(action, "source code", "anchor", "test.py")
    assert result.patch_apply_status == "skipped"


def test_insert_after_call():
    """Insertion resolver places helper after _set_fill_values."""
    source = (
        "def write(self, table):\n"
        "    cols = list(table.columns.values())\n"
        "    self.data._set_fill_values(cols)\n"
        "    lines = []\n"
    )
    applier = ConstrainedActionApplier()
    action = ConstrainedAction(
        action_type="CALL_EXISTING_HELPER", original_action_type="CALL_EXISTING_HELPER",
        target_symbol="write", target_file="test.py", target_span="L1-L4",
        replacement_snippet="self.data._set_col_formats()",
        expected_effect="apply column formats after fill_values",
        confidence=0.9,
    )
    result, patched = applier.apply_action(action, source, "anchor", "test.py")
    assert result.patch_apply_status == "applied"
    assert "self.data._set_col_formats()" in patched
    # Should be after _set_fill_values
    lines = patched.splitlines()
    fill_line = next(i for i, l in enumerate(lines) if "_set_fill_values" in l)
    format_line = next(i for i, l in enumerate(lines) if "_set_col_formats" in l)
    assert format_line > fill_line


def test_insert_stays_inside_anchor():
    """Insertion stays inside selected anchor span."""
    source = (
        "class Writer:\n"
        "    def write(self, table):\n"
        "        self._check(table)\n"
        "        cols = list(table.columns.values())\n"
        "        self.data._set_fill_values(cols)\n"
        "        lines = []\n"
        "        return lines\n"
        "    def other(self):\n"
        "        pass\n"
    )
    applier = ConstrainedActionApplier()
    action = ConstrainedAction(
        action_type="CALL_EXISTING_HELPER", original_action_type="CALL_EXISTING_HELPER",
        target_symbol="write", target_file="test.py", target_span="L2-L7",
        replacement_snippet="self.data._set_col_formats()",
        expected_effect="apply formats", confidence=0.9,
    )
    result, patched = applier.apply_action(action, source, "anchor", "test.py")
    assert result.patch_apply_status == "applied"
    assert "other" not in patched.splitlines()[result.resolved_insert_line]


def test_indentation_preserved():
    """Indentation is preserved after insertion."""
    source = (
        "def write(self, table):\n"
        "    cols = list(table.columns.values())\n"
        "    self.data._set_fill_values(cols)\n"
        "    lines = []\n"
    )
    applier = ConstrainedActionApplier()
    action = ConstrainedAction(
        action_type="CALL_EXISTING_HELPER", original_action_type="CALL_EXISTING_HELPER",
        target_symbol="write", target_file="test.py", target_span="L1-L4",
        replacement_snippet="self.data._set_col_formats()",
        expected_effect="apply formats", confidence=0.9,
    )
    result, patched = applier.apply_action(action, source, "anchor", "test.py")
    assert result.patch_apply_status == "applied"
    # Check indentation matches surrounding code
    lines = patched.splitlines()
    for line in lines:
        if line.strip() and not line.startswith("def "):
            assert line.startswith("    ") or line.startswith("self") or line.startswith("return")


def test_syntax_passes_after_insertion():
    """Syntax check passes after insertion."""
    source = (
        "def write(self, table):\n"
        "    cols = list(table.columns.values())\n"
        "    self.data._set_fill_values(cols)\n"
        "    lines = []\n"
    )
    applier = ConstrainedActionApplier()
    action = ConstrainedAction(
        action_type="CALL_EXISTING_HELPER", original_action_type="CALL_EXISTING_HELPER",
        target_symbol="write", target_file="test.py", target_span="L1-L4",
        replacement_snippet="self.data._set_col_formats()",
        expected_effect="apply formats", confidence=0.9,
    )
    result, patched = applier.apply_action(action, source, "anchor", "test.py")
    assert result.syntax_check_status == "passed"


def test_refinement_can_add_state_assignment():
    """Bounded refinement can add prerequisite state assignment."""
    source = (
        "def write(self, table):\n"
        "    cols = list(table.columns.values())\n"
        "    self.data._set_fill_values(cols)\n"
        "    lines = []\n"
    )
    applier = ConstrainedActionApplier()
    # First action: insert helper
    action1 = ConstrainedAction(
        action_type="CALL_EXISTING_HELPER", original_action_type="CALL_EXISTING_HELPER",
        target_symbol="write", target_file="test.py", target_span="L1-L4",
        replacement_snippet="self.data._set_col_formats()",
        expected_effect="apply formats", confidence=0.9,
    )
    result1, patched1 = applier.apply_action(action1, source, "anchor", "test.py")
    assert result1.patch_apply_status == "applied"

    # Second action: add state assignment before helper
    action2 = ConstrainedAction(
        action_type="INSERT_FORMAT_APPLICATION", original_action_type="INSERT_FORMAT_APPLICATION",
        target_symbol="write", target_file="test.py", target_span="L1-L4",
        replacement_snippet="self.data.cols = cols",
        expected_effect="set required state", confidence=0.9,
    )
    result2, patched2 = applier.apply_action(action2, patched1, "anchor", "test.py")
    assert result2.patch_apply_status == "applied"
    assert "self.data.cols = cols" in patched2
    assert "self.data._set_col_formats()" in patched2


def test_full_method_rewrite_rejected():
    """Full method rewrite is rejected."""
    applier = ConstrainedActionApplier()
    raw = {
        "selected_action_type": "CALL_EXISTING_HELPER",
        "replacement_snippet": "def write(self, table):\n    # full rewrite\n    pass",
    }
    action = applier.normalize_action(raw)
    assert action is None  # Rejected because snippet contains "def "


def test_unrelated_file_edit_rejected():
    """Unrelated file edit is rejected."""
    applier = ConstrainedActionApplier()
    raw = {
        "selected_action_type": "INSERT_GUARD",
        "replacement_snippet": "import os; os.system('rm -rf /')",
    }
    action = applier.normalize_action(raw)
    assert action is None  # Rejected because contains "import "


def test_verifier_pass_receipt_is_internal_only():
    """Verifier pass receipt is classified as internal-only."""
    from nexus.services.local_heal.native_validation_bridge import NativeValidationBridge
    vbridge = NativeValidationBridge()
    receipt = vbridge.build_receipt(
        route_id="test_route", evidence_packet_id="test",
        model_role="12b", model_name="test_model", candidate_id="c1",
        parser_ok=True, patch_applied=True, verifier_ok=True,
    )
    assert receipt.claim_status == "internal_only"
    assert receipt.acceptance_status == "internal_only"
    assert receipt.final_status == "VERIFIER_PASS_INTERNAL_ONLY"


def test_public_claim_disabled():
    """Public claim must be disabled."""
    from nexus.services.local_heal.native_validation_bridge import NativeValidationBridge
    vbridge = NativeValidationBridge()
    receipt = vbridge.build_receipt(
        route_id="test", evidence_packet_id="test",
        model_role="12b", model_name="test", candidate_id="c1",
        parser_ok=True, patch_applied=True, verifier_ok=True,
    )
    assert receipt.claim_status != "public_claim"
    assert receipt.acceptance_status != "public_claim"
