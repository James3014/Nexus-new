"""
Nexus Tracer — 封裝 OpenTelemetry API，提供 Pipeline-Aware 的 Span 管理

使用方式：
    from nexus.telemetry.tracer import NexusTracer

    tracer = NexusTracer()
    with tracer.pipeline_span("task-123") as root:
        with tracer.phase_span("P", task_id="task-123") as p_span:
            p_span.set_attribute("plan.steps", 5)
        with tracer.phase_span("D", task_id="task-123"):
            ...
"""

from contextlib import contextmanager
from typing import Optional, Dict, Any
import logging

from opentelemetry import trace
from opentelemetry.trace import StatusCode, Span

logger = logging.getLogger(__name__)


class NexusTracer:
    """Pipeline-Aware Tracing，為 PDXRAC 六階段提供結構化 Span。"""

    def __init__(self, tracer_name: str = "nexus.engine.pipeline"):
        self._tracer = trace.get_tracer(tracer_name)

    @contextmanager
    def pipeline_span(self, task_id: str, **attributes):
        """
        建立 Pipeline 根 Span（一個 task_id 一個 trace）
        回傳 (span, trace_id_hex, span_id_hex)
        """
        with self._tracer.start_as_current_span(
            name=f"pipeline.run:{task_id}",
            attributes={"nexus.task_id": task_id, **attributes},
        ) as span:
            ctx = span.get_span_context()
            trace_id_hex = format(ctx.trace_id, "032x")
            span_id_hex = format(ctx.span_id, "016x")
            logger.debug("OTel pipeline span started: trace=%s span=%s", trace_id_hex, span_id_hex)
            try:
                yield span, trace_id_hex, span_id_hex
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

    @contextmanager
    def phase_span(self, phase: str, task_id: str = "", **attributes):
        """
        建立階段級子 Span（P/D/X/R/A/C）
        自動從 Context 繼承父 Span（pipeline root）
        """
        with self._tracer.start_as_current_span(
            name=f"phase.{phase}",
            attributes={
                "nexus.phase": phase,
                "nexus.task_id": task_id,
                **attributes,
            },
        ) as span:
            try:
                yield span
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

    @staticmethod
    def current_trace_id() -> str:
        """取得當前 Context 的 trace_id（hex），供 EventBus / State 注入"""
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
        return ""

    @staticmethod
    def current_span_id() -> str:
        """取得當前 Context 的 span_id（hex）"""
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.span_id:
            return format(ctx.span_id, "016x")
        return ""

    @staticmethod
    def add_event(name: str, attributes: Optional[dict] = None) -> None:
        """在當前 Span 追加 Event（對應 pipeline 中的關鍵決策點）"""
        span = trace.get_current_span()
        span.add_event(name, attributes=attributes or {})

    @staticmethod
    def set_attribute(key: str, value: Any) -> None:
        """在當前 Span 設定 Attribute"""
        span = trace.get_current_span()
        span.set_attribute(key, value)
