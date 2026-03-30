import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from nexus.telemetry.otel_config import init_otel, JsonlSpanExporter
from opentelemetry import trace

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

def test_jsonl_exporter_writes_spans(temp_dir):
    jsonl_path = temp_dir / "traces.jsonl"
    exporter = JsonlSpanExporter(jsonl_path)
    
    # Mock a readable span
    span = MagicMock()
    span.context.trace_id = 0x1234567890abcdef1234567890abcdef
    span.context.span_id = 0x1234567890abcdef
    span.parent = None
    span.name = "test-span"
    span.start_time = 1000
    span.end_time = 2000
    span.status.status_code.name = "OK"
    span.attributes = {"key": "value"}
    span.events = []
    
    exporter.export([span])
    
    assert jsonl_path.exists()
    content = jsonl_path.read_text()
    data = json.loads(content)
    assert data["name"] == "test-span"
    assert data["trace_id"] == "1234567890abcdef1234567890abcdef"
    assert data["attributes"]["key"] == "value"

@patch("nexus.telemetry.otel_config.TracerProvider")
@patch("opentelemetry.trace.set_tracer_provider")
def test_init_otel_defaults_to_jsonl(mock_set, mock_provider_cls, temp_dir):
    # Ensure env vars are clean
    with patch.dict(os.environ, {}, clear=True):
        init_otel(project_root=temp_dir)
        
        # Should have added JSONL processor
        provider = mock_provider_cls.return_value
        assert provider.add_span_processor.called

@patch("nexus.telemetry.otel_config.ConsoleSpanExporter")
def test_init_otel_console_mode(mock_console_cls, temp_dir):
    with patch.dict(os.environ, {"NEXUS_TRACE_CONSOLE": "1"}):
        init_otel(project_root=temp_dir)
        assert mock_console_cls.called
