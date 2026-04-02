from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
"""
nexus/core/minimal_tracer.py
─────────────────────────────
Minimal Phase Span Tracer — Sprint 11d

Design constraints:
  • Only tracks: phase.start, phase.complete, phase.error
  • Injects: trace_id, span_id into all spans
  • Fallback: If opentelemetry is unavailable, appends JSONL to .nexustracelog.jsonl
  • Cross-node traceparents are DROPPED (never propagated to remote nodes)
    to prevent malicious span injection from compromised federation peers.
"""
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Try to import opentelemetry; fall back to JSONL if unavailable
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

class NexusMinimalTracer:
    """
    Minimal-surface tracer covering only phase lifecycle events.
    Degrades gracefully to JSONL logging if OTel SDK is unavailable.
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.jsonl_path = project_root / ".nexustracelog.jsonl"
        self._tracer = None

        if _OTEL_AVAILABLE:
            provider = TracerProvider()
            self._exporter = InMemorySpanExporter()
            provider.add_span_processor(SimpleSpanProcessor(self._exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer("nexus.core.minimal_tracer")
            logger.debug("NexusMinimalTracer: OTel SDK active.")
        else:
            logger.debug("NexusMinimalTracer: OTel SDK unavailable, using JSONL fallback.")

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex

    def new_span_id(self) -> str:
        return uuid.uuid4().hex[:16]

    @contextmanager
    def phase_span(
        self,
        phase_name: str,
        trace_id: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Generator[Dict[str, str], None, None]:
        """
        Context manager covering a single phase lifecycle.
        Yields a dict containing {"trace_id": ..., "span_id": ...} for injection
        into NexusOutcomeV2 payloads.

        Cross-node traceparent injection is explicitly FORBIDDEN here.
        """
        span_id = self.new_span_id()
        ids = {"trace_id": trace_id, "span_id": span_id}
        start_time = datetime.now(timezone.utc).isoformat()
        self._emit("phase.start", phase_name, trace_id, span_id, start_time, attributes)
        try:
            yield ids
            end_time = datetime.now(timezone.utc).isoformat()
            self._emit("phase.complete", phase_name, trace_id, span_id, end_time, attributes)
        except Exception as exc:
            end_time = datetime.now(timezone.utc).isoformat()
            self._emit("phase.error", phase_name, trace_id, span_id, end_time,
                       {**(attributes or {}), "error": str(exc)})
            raise

    def _emit(
        self,
        event: str,
        phase: str,
        trace_id: str,
        span_id: str,
        timestamp: str,
        attributes: Optional[Dict[str, Any]],
    ) -> None:
        record = {
            "event": event,
            "phase": phase,
            "trace_id": trace_id,
            "span_id": span_id,
            "timestamp": timestamp,
            "attributes": attributes or {},
        }
        # Always write JSONL fallback (cheap audit trail)
        with self.jsonl_path.open("a") as f:
            f.write(json.dumps(record) + "\n")

        if _OTEL_AVAILABLE and self._tracer:
            with self._tracer.start_as_current_span(f"{phase}.{event.split('.')[-1]}") as span:
                span.set_attribute("trace_id", trace_id)
                span.set_attribute("span_id", span_id)
                for k, v in (attributes or {}).items():
                    span.set_attribute(k, str(v))
