"""P5-I0 Part B: Memory Action Receipt Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.memory_action_receipt import MemoryActionReceipt


def test_to_jsonl_row_fields():
    """P5-I0: to_jsonl_row returns all required fields."""
    receipt = MemoryActionReceipt(
        memory_action_id="ma-1",
        task_id="t1",
        phase="learning",
        action_type="memory_write",
        memory_file="learning.jsonl",
        memory_key="key1",
        reason="test",
        input_refs=("ref1",),
        output_ref="out1",
    )
    row = receipt.to_jsonl_row()
    assert row["memory_action_id"] == "ma-1"
    assert row["task_id"] == "t1"
    assert row["action_type"] == "memory_write"
    assert row["outcome"] == "success"
    assert row["failure_reason"] is None


def test_failed_without_failure_reason_raises():
    """P5-I0: outcome='failed' without failure_reason raises ValueError."""
    with pytest.raises(ValueError, match="failure_reason"):
        MemoryActionReceipt(
            memory_action_id="ma-1",
            task_id="t1",
            phase="test",
            action_type="memory_write",
            memory_file="f",
            memory_key="k",
            reason="r",
            input_refs=(),
            output_ref=None,
            outcome="failed",
        )


def test_invalid_action_type_raises():
    """P5-I0: invalid action_type raises ValueError."""
    with pytest.raises(ValueError, match="Invalid action_type"):
        MemoryActionReceipt(
            memory_action_id="ma-1",
            task_id="t1",
            phase="test",
            action_type="invalid_type",
            memory_file="f",
            memory_key="k",
            reason="r",
            input_refs=(),
            output_ref=None,
        )


def test_used_by_later_stage_default():
    """P5-I0: used_by_later_stage default False."""
    receipt = MemoryActionReceipt(
        memory_action_id="ma-1",
        task_id="t1",
        phase="test",
        action_type="memory_read",
        memory_file="f",
        memory_key="k",
        reason="r",
        input_refs=(),
        output_ref=None,
    )
    assert receipt.used_by_later_stage is False


def test_serializable_to_json():
    """P5-I0: to_jsonl_row is serializable to JSON."""
    receipt = MemoryActionReceipt(
        memory_action_id="ma-1",
        task_id="t1",
        phase="test",
        action_type="memory_write",
        memory_file="f",
        memory_key="k",
        reason="r",
        input_refs=("ref1",),
        output_ref="out1",
    )
    json_str = json.dumps(receipt.to_jsonl_row())
    assert len(json_str) > 0


def test_auto_generated_id_nonempty():
    """P5-I0: memory_action_id must be non-empty."""
    with pytest.raises(ValueError, match="memory_action_id"):
        MemoryActionReceipt(
            memory_action_id="",
            task_id="t1",
            phase="test",
            action_type="memory_write",
            memory_file="f",
            memory_key="k",
            reason="r",
            input_refs=(),
            output_ref=None,
        )
