import pytest
from nexus.telemetry.tracer import NexusTracer
from opentelemetry import trace

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
