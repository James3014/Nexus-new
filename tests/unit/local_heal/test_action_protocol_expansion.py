"""Unit tests for BE-Track action protocol expansion and transactional apply."""
from __future__ import annotations

import tempfile
from pathlib import Path
from nexus.services.local_heal.action_protocol import (
    ActionProtocol,
    ProtocolAction,
    ActionDependency,
)


def test_multi_step_local_edit_validation():
    # 1. Valid multi-step edit
    action = ProtocolAction(
        action_id="act_01",
        file_path="src/file.py",
        anchor_symbol="function_name",
        exact_search_text="old_code",
        replacement_text="new_code",
    )
    proto = ActionProtocol(
        protocol_id="proto_01",
        protocol_type="MULTI_STEP_LOCAL_EDIT",
        task_id="C_15000",
        ordered_actions=[action],
        files_involved=["src/file.py"],
    )
    res = proto.validate_protocol()
    assert res.is_valid

    # 2. Invalid: missing anchor and search text
    action_invalid = ProtocolAction(
        action_id="act_02",
        file_path="src/file.py",
        anchor_symbol="",
        exact_search_text="",
        replacement_text="new_code",
    )
    proto_invalid = ActionProtocol(
        protocol_id="proto_02",
        protocol_type="MULTI_STEP_LOCAL_EDIT",
        task_id="C_15000",
        ordered_actions=[action_invalid],
        files_involved=["src/file.py"],
    )
    res_invalid = proto_invalid.validate_protocol()
    assert not res_invalid.is_valid


def test_bounded_cross_file_edit_validation():
    # 1. Valid: <= 3 files and match
    action = ProtocolAction(
        action_id="act_01",
        file_path="src/file.py",
        anchor_symbol="func",
        exact_search_text="old",
        replacement_text="new",
    )
    proto = ActionProtocol(
        protocol_id="proto_01",
        protocol_type="BOUNDED_CROSS_FILE_EDIT",
        task_id="C_15000",
        ordered_actions=[action],
        files_involved=["src/file.py"],
    )
    res = proto.validate_protocol()
    assert res.is_valid

    # 2. Invalid: > 3 files
    proto_many = ActionProtocol(
        protocol_id="proto_many",
        protocol_type="BOUNDED_CROSS_FILE_EDIT",
        task_id="C_15000",
        ordered_actions=[action],
        files_involved=["a.py", "b.py", "c.py", "d.py"],
    )
    res_many = proto_many.validate_protocol()
    assert not res_many.is_valid

    # 3. Invalid: action files exceed files_involved set
    proto_mismatch = ActionProtocol(
        protocol_id="proto_mismatch",
        protocol_type="BOUNDED_CROSS_FILE_EDIT",
        task_id="C_15000",
        ordered_actions=[action],
        files_involved=["other.py"],
    )
    res_mismatch = proto_mismatch.validate_protocol()
    assert not res_mismatch.is_valid


def test_dependent_symbol_update_validation():
    # 1. Valid: has dependency edges and evidence node id
    action1 = ProtocolAction(
        action_id="act_01",
        file_path="src/file.py",
        anchor_symbol="func1",
        exact_search_text="old",
        replacement_text="new",
        evidence_node_id="node_01",
    )
    action2 = ProtocolAction(
        action_id="act_02",
        file_path="src/file.py",
        anchor_symbol="func2",
        exact_search_text="old",
        replacement_text="new",
        evidence_node_id="node_02",
    )
    proto = ActionProtocol(
        protocol_id="proto_01",
        protocol_type="DEPENDENT_SYMBOL_UPDATE",
        task_id="C_15000",
        ordered_actions=[action1, action2],
        dependency_edges=[ActionDependency("act_01", "act_02")],
        files_involved=["src/file.py"],
    )
    res = proto.validate_protocol()
    assert res.is_valid

    # 2. Invalid: no dependency edges
    proto_no_edge = ActionProtocol(
        protocol_id="proto_02",
        protocol_type="DEPENDENT_SYMBOL_UPDATE",
        task_id="C_15000",
        ordered_actions=[action1, action2],
        files_involved=["src/file.py"],
    )
    assert not proto_no_edge.validate_protocol().is_valid


def test_apply_transactional_rollback():
    # Setup temporary directory and mock apply
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_file = tmp_path / "test.py"
        test_file.write_text("initial_state")

        action = ProtocolAction("act_01", "test.py", "init", "initial_state", "changed_state")
        proto = ActionProtocol(
            protocol_id="proto_01",
            protocol_type="MULTI_STEP_LOCAL_EDIT",
            task_id="C_15000",
            ordered_actions=[action],
            files_involved=["test.py"],
            rollback_policy="mock_policy",
        )

        rollback_called = False

        def mock_rollback(proj_root):
            nonlocal rollback_called
            rollback_called = True
            test_file.write_text("initial_state")

        proto.rollback = mock_rollback

        # 1. Simulation of failure in applier -> rollback called
        def applier_fail(act):
            return False, "applier_error"

        def verifier_ok():
            return True, ""

        success, msg = proto.apply_transactional(tmp_path, applier_fail, verifier_ok)
        assert not success
        assert "applier_error" in msg
        assert rollback_called

        # 2. Simulation of failure in verifier -> rollback called
        rollback_called = False
        def applier_ok(act):
            test_file.write_text("changed_state")
            return True, ""

        def verifier_fail():
            return False, "verifier_error"

        success, msg = proto.apply_transactional(tmp_path, applier_ok, verifier_fail)
        assert not success
        assert "verifier_error" in msg
        assert rollback_called
        assert test_file.read_text() == "initial_state"
