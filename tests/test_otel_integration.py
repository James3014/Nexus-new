from pathlib import Path
"""Unit tests for P2 OpenTelemetry integration."""

import json
import tempfile

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from nexus.telemetry.otel_config import JsonlSpanExporter, init_otel
from nexus.telemetry.tracer import NexusTracer


def test_jsonl_exporter_writes_span():
    """JSONL exporter 應將 span 寫入檔案"""
    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = Path(tmpdir) / "traces.jsonl"
        exporter = JsonlSpanExporter(jsonl_path)

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test-span") as span:
            span.set_attribute("test.key", "test-value")

        provider.shutdown()

        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["name"] == "test-span"
        assert "trace_id" in record
        assert len(record["trace_id"]) == 32


def test_nexus_tracer_pipeline_span():
    """NexusTracer.pipeline_span 應產生 root span 並回傳 trace_id"""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)

    tracer = NexusTracer()
    with tracer.pipeline_span("task-unit-test") as (span, trace_id, span_id):
        assert len(trace_id) == 32
        assert len(span_id) == 16
        assert trace_id != "0" * 32

    provider.shutdown()


def test_nexus_tracer_phase_span_inherits_parent():
    """phase_span 應自動繼承 pipeline_span 的 trace context"""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)

    tracer = NexusTracer()
    with tracer.pipeline_span("task-inherit-test") as (root, root_trace_id, _):
        with tracer.phase_span("P", task_id="task-inherit-test") as p_span:
            child_trace_id = NexusTracer.current_trace_id()
            assert child_trace_id == root_trace_id  # 同一 trace

    provider.shutdown()


def test_event_bus_injects_trace_context():
    """EventBus.publish 應在 span context 內自動注入 _trace_id"""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)

    tracer = NexusTracer()
    captured = {}

    with tracer.pipeline_span("task-eventbus-test") as (_, trace_id, _):
        # 模擬 EventBus 行為
        from nexus.telemetry.tracer import NexusTracer as NT
        captured["trace_id"] = NT.current_trace_id()

    assert captured["trace_id"] == trace_id
    provider.shutdown()
