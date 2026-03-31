"""
OpenTelemetry TracerProvider 初始化
支援三種模式：
  1. OTLP (生產) — 推送至 Jaeger / Grafana Tempo
  2. Console (開發) — 直接印在 stderr
  3. JSONL (Nexus 原生) — 寫入 .nexus/traces/traces.jsonl
"""

import os
import json
import logging
import pathlib
import typing
from typing import Optional, Dict, Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

# ── Nexus JSONL Exporter（零依賴持久化）────────────────────────
class JsonlSpanExporter(SpanExporter):
    """將 Span 輸出為 append-only JSONL，與 EventBus 同風格。"""

    def __init__(self, file_path: pathlib.Path):
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                for span in spans:
                    record = {
                        "trace_id": format(span.context.trace_id, "032x"),
                        "span_id": format(span.context.span_id, "016x"),
                        "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
                        "name": span.name,
                        "start_time_ns": span.start_time,
                        "end_time_ns": span.end_time,
                        "status": span.status.status_code.name,
                        "attributes": dict(span.attributes) if span.attributes else {},
                        "events": [
                            {"name": e.name, "timestamp": e.timestamp, "attributes": dict(e.attributes) if e.attributes else {}}
                            for e in (span.events or [])
                        ],
                    }
                    f.write(json.dumps(record, default=str) + "\n")
            return SpanExportResult.SUCCESS
        except OSError as exc:
            logger.warning("jsonl_span_export_failed: %s", exc)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass


def init_otel(project_root: Optional[pathlib.Path] = None, service_name: str = "nexus-engine") -> None:
    """
    初始化全域 TracerProvider。
    優先順序：
      1. 環境變數 OTEL_EXPORTER_OTLP_ENDPOINT 存在 → OTLP exporter
      2. 環境變數 NEXUS_TRACE_CONSOLE=1 → Console exporter
      3. 預設 → JSONL exporter（寫入 .nexus/traces/traces.jsonl）
    """
    resource = Resource.create({"service.name": service_name, "service.version": "9.0.0"})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    console_mode = os.environ.get("NEXUS_TRACE_CONSOLE", "0") == "1"

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            logger.info("OTel: OTLP exporter → %s", otlp_endpoint)
        except (ImportError, Exception) as e:
            logger.warning(
                "OTLP Exporter failed to initialize. Falling back to Console/JSONL.",
                exc_info=e
            )
            console_mode = False  # fall through to JSONL
    elif console_mode:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel: Console exporter (debug mode)")

    # 無論是否有 OTLP/Console，總是附加 JSONL exporter 作為持久化兜底
    if project_root:
        project_root_path = pathlib.Path(project_root)
        jsonl_path = project_root_path / ".nexus" / "traces" / "traces.jsonl"
        provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(jsonl_path)))
        logger.info("OTel: JSONL exporter → %s", jsonl_path)

    trace.set_tracer_provider(provider)

# ── Nexus Prometheus Metrics ────────────────────────
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

def init_metrics_prometheus(port: int = 8000) -> None:
    """初始化 Prometheus 指標暴露服務。"""
    try:
        from opentelemetry.exporter.prometheus import PrometheusMetricExporter
        from prometheus_client import start_http_server

        exporter = PrometheusMetricExporter()
        reader = PeriodicExportingMetricReader(exporter)
        provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(provider)
        
        start_http_server(port=port)
        logger.info("OTel: Prometheus metrics exporter active on port %d", port)
    except ImportError:
        logger.warning("OTel: opentelemetry-exporter-prometheus not installed. Metrics disabled.")

# 全域 Meter 實例
meter = metrics.get_meter("nexus.dual_engine")

# 定義 v18.4 核型指標
mttr_histogram = meter.create_histogram(
    name="nexus_mttr",
    description="Nexus Dual-Engine Mean Time To Repair (Seconds)",
    unit="s",
)

accuracy_gauge = meter.create_gauge(
    name="nexus_accuracy",
    description="Nexus Cumulative Resolution Accuracy (Percentage)",
    unit="%",
)

jepa_surprise_gauge = meter.create_gauge(
    name="nexus_jepa_surprise",
    description="LeWorldModel Prediction Surprise Rate (Placeholder for Phase 13)",
)
