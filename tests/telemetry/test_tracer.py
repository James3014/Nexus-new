import pytest
from nexus.telemetry.tracer import NexusTracer
from opentelemetry import trace
from unittest.mock import MagicMock, patch

def test_tracer_pipeline_span():
    tracer = NexusTracer()
    with tracer.pipeline_span("task-1") as (span, tid, sid):
        assert tid != ""
        assert sid != ""
        assert span.is_recording()
        assert "task-1" in span.name

def test_tracer_phase_span_nesting():
    tracer = NexusTracer()
    with tracer.pipeline_span("task-1"):
        with tracer.phase_span("P") as p_span:
            assert p_span.is_recording()
            assert "phase.P" in p_span.name
            
            # Check current IDs
            assert tracer.current_trace_id() != ""
            assert tracer.current_span_id() != ""

def test_tracer_add_event():
    tracer = NexusTracer()
    with tracer.pipeline_span("task-1"):
        tracer.add_event("decision_made", {"decision": "proceed"})
        # No easy way to assert on current span without mocking the provider, 
        # but we can verify it doesn't crash.


def test_tracer_record_belief_shift_adds_semantic_event():
    span = MagicMock()
    with patch("nexus.telemetry.tracer.trace.get_current_span", return_value=span):
        NexusTracer.record_belief_shift("task-1", 0.9, 0.1)

    span.add_event.assert_called_once_with(
        "belief.shift",
        attributes={
            "nexus.task_id": "task-1",
            "belief.old": 0.9,
            "belief.new": 0.1,
            "belief.delta": -0.8,
        },
    )
