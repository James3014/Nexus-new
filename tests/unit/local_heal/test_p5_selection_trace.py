"""P5-I0 Part A: Selection Event Trace Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.selection_trace import (
    SelectionTrace,
    SelectionTraceEvent,
    SUPPORTED_EVENT_TYPES,
)


def _make_event(event_type="candidate_observed", decision="noop", phase="feature_extraction"):
    return SelectionTraceEvent(
        event_id="",
        parent_event_id=None,
        phase=phase,
        event_type=event_type,
        candidate_index=0,
        candidate_hash="abc",
        inputs={"x": 1},
        outputs={"y": 2},
        decision=decision,
        reason="test",
        reversible=True,
    )


def test_append_preserves_order_and_auto_id():
    """P5-I0: append preserves event order and auto-assigns event_id."""
    trace = SelectionTrace(trace_id="t1", task_id="task1")
    e1 = _make_event(event_type="candidate_observed")
    e2 = _make_event(event_type="candidate_feature_extracted")

    trace.append_event(e1)
    trace.append_event(e2)

    assert len(trace.events) == 2
    assert trace.events[0].event_id == "evt-0"
    assert trace.events[1].event_id == "evt-1"
    assert trace.root_event_id == "evt-0"
    assert trace.final_event_id == "evt-1"


def test_parent_event_id_links_correctly():
    """P5-I0: parent_event_id correctly links to previous different-type event."""
    trace = SelectionTrace(trace_id="t1", task_id="task1")
    e1 = _make_event(event_type="candidate_observed")
    e2 = _make_event(event_type="candidate_observed")  # same type
    e3 = _make_event(event_type="candidate_feature_extracted")  # different type

    trace.append_event(e1)
    trace.append_event(e2)
    trace.append_event(e3)

    assert trace.events[0].parent_event_id is None
    assert trace.events[1].parent_event_id is None  # same type as prev
    # e3 links to last event with different type (e2 has same type as e3, so links to e1)
    # Actually: e2 type = "candidate_observed", e3 type = "candidate_feature_extracted"
    # So e3 should link to e2 (last event with different type)
    assert trace.events[2].parent_event_id == "evt-1"


def test_to_receipt_fragment_keys():
    """P5-I0: to_receipt_fragment returns all required keys."""
    trace = SelectionTrace(trace_id="t1", task_id="task1")
    trace.append_event(_make_event())

    fragment = trace.to_receipt_fragment()
    assert "p5_trace_event_count" in fragment
    assert "p5_trace_fail_closed" in fragment
    assert "p5_trace_events" in fragment
    assert "p5_trace_root_event_id" in fragment
    assert "p5_trace_final_event_id" in fragment
    assert fragment["p5_trace_event_count"] == 1


def test_fail_closed_trace():
    """P5-I0: fail_closed trace correctly sets fail_closed flag."""
    trace = SelectionTrace(trace_id="t1", task_id="task1", fail_closed=True)
    trace.append_event(_make_event(event_type="selection_fail_closed", decision="fail_closed"))

    fragment = trace.to_receipt_fragment()
    assert fragment["p5_trace_fail_closed"] is True


def test_no_mutation_after_append():
    """P5-I0: No mutation of event after append (event fields frozen)."""
    trace = SelectionTrace(trace_id="t1", task_id="task1")
    e = _make_event()
    trace.append_event(e)

    # Event should be frozen (frozen=True dataclass)
    with pytest.raises(AttributeError):
        e.event_id = "mutated"


def test_serializable_to_json():
    """P5-I0: Receipt fragment is serializable to JSON."""
    trace = SelectionTrace(trace_id="t1", task_id="task1")
    trace.append_event(_make_event())

    fragment = trace.to_receipt_fragment()
    json_str = json.dumps(fragment)
    assert len(json_str) > 0
