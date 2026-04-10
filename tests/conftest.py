from pathlib import Path
import sys
import types
import math
from contextlib import contextmanager


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_opentelemetry_stub() -> None:
    if "opentelemetry" in sys.modules:
        return

    otel = types.ModuleType("opentelemetry")
    trace_mod = types.ModuleType("opentelemetry.trace")
    metrics_mod = types.ModuleType("opentelemetry.metrics")
    sdk_mod = types.ModuleType("opentelemetry.sdk")
    sdk_trace_mod = types.ModuleType("opentelemetry.sdk.trace")
    sdk_trace_export_mod = types.ModuleType("opentelemetry.sdk.trace.export")
    sdk_resources_mod = types.ModuleType("opentelemetry.sdk.resources")
    sdk_metrics_mod = types.ModuleType("opentelemetry.sdk.metrics")
    sdk_metrics_export_mod = types.ModuleType("opentelemetry.sdk.metrics.export")

    class _SpanContext:
        def __init__(self) -> None:
            self.trace_id = 1
            self.span_id = 1

    class _SpanStatusCode:
        name = "OK"

    class _SpanStatus:
        status_code = _SpanStatusCode()

    class Span:
        def __init__(self, name: str = "span") -> None:
            self.name = name
            self.context = _SpanContext()
            self.parent = None
            self.start_time = 0
            self.end_time = 0
            self.status = _SpanStatus()
            self.attributes = {}
            self.events = []

        def is_recording(self) -> bool:
            return True

        def get_span_context(self):
            return self.context

        def set_status(self, *args, **kwargs):
            return None

        def record_exception(self, *args, **kwargs):
            return None

        def add_event(self, name, attributes=None):
            self.events.append(types.SimpleNamespace(name=name, timestamp=0, attributes=attributes or {}))

        def set_attribute(self, key, value):
            self.attributes[key] = value

    class _Tracer:
        def __init__(self, provider=None):
            self._provider = provider

        @contextmanager
        def start_as_current_span(self, name, attributes=None):
            span = Span(name)
            span.attributes = attributes or {}
            _state["current_span"] = span
            try:
                yield span
            finally:
                provider = self._provider or _state.get("provider")
                for processor in getattr(provider, "_processors", []) or []:
                    exporter = getattr(processor, "exporter", None)
                    if exporter and hasattr(exporter, "export"):
                        exporter.export([span])
                _state["current_span"] = Span("noop")

    class StatusCode:
        ERROR = "ERROR"

    class TracerProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self._processors = []

        def add_span_processor(self, p):
            self._processors.append(p)

        def get_tracer(self, name):
            return _Tracer(self)

        def shutdown(self):
            return None

    class ReadableSpan(Span):
        pass

    class SpanExporter:
        def export(self, spans):
            return SpanExportResult.SUCCESS

        def shutdown(self):
            return None

    class SpanExportResult:
        SUCCESS = "SUCCESS"
        FAILURE = "FAILURE"

    class SimpleSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class ConsoleSpanExporter:
        pass

    class Resource:
        @staticmethod
        def create(attrs):
            return attrs

    class _Meter:
        def create_histogram(self, *args, **kwargs):
            return object()

        def create_gauge(self, *args, **kwargs):
            return object()

    class MeterProvider:
        def __init__(self, metric_readers=None):
            self.metric_readers = metric_readers or []

    class PeriodicExportingMetricReader:
        def __init__(self, exporter):
            self.exporter = exporter

    _state = {"provider": None, "current_span": Span("noop")}

    def set_tracer_provider(provider):
        _state["provider"] = provider

    def get_tracer(name):
        return _Tracer(_state.get("provider"))

    def get_current_span():
        return _state["current_span"]

    _meter_provider = {"provider": None}

    def set_meter_provider(provider):
        _meter_provider["provider"] = provider

    def get_meter(name):
        return _Meter()

    trace_mod.set_tracer_provider = set_tracer_provider
    trace_mod.get_tracer = get_tracer
    trace_mod.get_current_span = get_current_span
    trace_mod.StatusCode = StatusCode
    trace_mod.Span = Span

    metrics_mod.set_meter_provider = set_meter_provider
    metrics_mod.get_meter = get_meter

    sdk_trace_mod.TracerProvider = TracerProvider
    sdk_trace_mod.ReadableSpan = ReadableSpan
    sdk_trace_export_mod.SimpleSpanProcessor = SimpleSpanProcessor
    sdk_trace_export_mod.ConsoleSpanExporter = ConsoleSpanExporter
    sdk_trace_export_mod.SpanExporter = SpanExporter
    sdk_trace_export_mod.SpanExportResult = SpanExportResult
    sdk_resources_mod.Resource = Resource
    sdk_metrics_mod.MeterProvider = MeterProvider
    sdk_metrics_export_mod.PeriodicExportingMetricReader = PeriodicExportingMetricReader

    sys.modules["opentelemetry"] = otel
    sys.modules["opentelemetry.trace"] = trace_mod
    sys.modules["opentelemetry.metrics"] = metrics_mod
    sys.modules["opentelemetry.sdk"] = sdk_mod
    sys.modules["opentelemetry.sdk.trace"] = sdk_trace_mod
    sys.modules["opentelemetry.sdk.trace.export"] = sdk_trace_export_mod
    sys.modules["opentelemetry.sdk.resources"] = sdk_resources_mod
    sys.modules["opentelemetry.sdk.metrics"] = sdk_metrics_mod
    sys.modules["opentelemetry.sdk.metrics.export"] = sdk_metrics_export_mod

    otel.trace = trace_mod
    otel.metrics = metrics_mod


def _install_dependency_injector_stub() -> None:
    if "dependency_injector" in sys.modules:
        return

    mod = types.ModuleType("dependency_injector")
    containers_mod = types.ModuleType("dependency_injector.containers")
    providers_mod = types.ModuleType("dependency_injector.providers")

    class _ProviderBase:
        def override(self, value):
            self._override = value

    class Configuration(_ProviderBase):
        def __init__(self):
            self._override = None

        def __call__(self, *args, **kwargs):
            return self._override

    class Singleton(_ProviderBase):
        def __init__(self, factory, *args, **kwargs):
            self.factory = factory
            self.args = args
            self.kwargs = kwargs
            self._instance = None
            self._override = None

        def __call__(self, *args, **kwargs):
            if self._override is not None:
                return self._override
            if self._instance is None:
                r_args = [a() if callable(a) and hasattr(a, "__class__") and not isinstance(a, type) else a for a in self.args]
                r_kwargs = {
                    k: (v() if callable(v) and hasattr(v, "__class__") and not isinstance(v, type) else v)
                    for k, v in self.kwargs.items()
                }
                self._instance = self.factory(*r_args, **r_kwargs)
            return self._instance

    class Factory(_ProviderBase):
        def __init__(self, factory, *args, **kwargs):
            self.factory = factory
            self.args = args
            self.kwargs = kwargs
            self._override = None
            self.provider = self

        def __call__(self, *args, **kwargs):
            if self._override is not None:
                return self._override
            r_args = [a() if callable(a) and hasattr(a, "__class__") and not isinstance(a, type) else a for a in self.args]
            r_kwargs = {
                k: (v() if callable(v) and hasattr(v, "__class__") and not isinstance(v, type) else v)
                for k, v in self.kwargs.items()
            }
            return self.factory(*r_args, **r_kwargs)

    class Dict(_ProviderBase):
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self._override = None

        def __call__(self, *args, **kwargs):
            if self._override is not None:
                return self._override
            return {k: (v() if callable(v) else v) for k, v in self.kwargs.items()}

    class DeclarativeContainer:
        pass

    providers_mod.Configuration = Configuration
    providers_mod.Singleton = Singleton
    providers_mod.Factory = Factory
    providers_mod.Dict = Dict
    containers_mod.DeclarativeContainer = DeclarativeContainer
    mod.providers = providers_mod
    mod.containers = containers_mod
    sys.modules["dependency_injector"] = mod
    sys.modules["dependency_injector.providers"] = providers_mod
    sys.modules["dependency_injector.containers"] = containers_mod


def _install_sentence_transformers_stub() -> None:
    if "sentence_transformers" in sys.modules:
        return
    import numpy as _np

    mod = types.ModuleType("sentence_transformers")

    class SentenceTransformer:
        def __init__(self, model_name):
            self.model_name = model_name

        def encode(self, texts):
            if isinstance(texts, str):
                texts = [texts]
            out = []
            for t in texts:
                seed = abs(hash(t)) % 1000
                vec = _np.array([(seed + i) % 97 / 97.0 for i in range(384)], dtype=float)
                out.append(vec)
            return _np.array(out) if len(out) > 1 else out[0]

    mod.SentenceTransformer = SentenceTransformer
    sys.modules["sentence_transformers"] = mod


def _install_lancedb_stub() -> None:
    if "lancedb" in sys.modules and "lancedb.pydantic" in sys.modules:
        return
    import pandas as _pd

    lancedb_mod = types.ModuleType("lancedb")
    pyd_mod = types.ModuleType("lancedb.pydantic")

    class _SearchResult:
        def __init__(self):
            self._limit = 5

        def limit(self, n):
            self._limit = n
            return self

        def to_pandas(self):
            return _pd.DataFrame([])

        def to_list(self):
            return []

    class _Table:
        def __init__(self):
            self._rows = []

        def search(self, *args, **kwargs):
            return _SearchResult()

        def add(self, data=None, **kwargs):
            if data is None:
                return None
            if hasattr(data, "to_dict"):
                rows = data.to_dict(orient="records")
            elif isinstance(data, list):
                rows = data
            else:
                rows = []
            self._rows.extend(rows)
            return None

    class _DB:
        def __init__(self):
            self._tables = {}

        def table_names(self):
            return list(self._tables.keys())

        def open_table(self, name):
            return self._tables.setdefault(name, _Table())

        def create_table(self, name, schema=None, data=None, **kwargs):
            table = self._tables.setdefault(name, _Table())
            if data is not None:
                table.add(data=data)
            return table

    def connect(path):
        return _DB()

    class LanceModel:
        pass

    def Vector(dim):
        return list

    lancedb_mod.connect = connect
    pyd_mod.Vector = Vector
    pyd_mod.LanceModel = LanceModel
    sys.modules["lancedb"] = lancedb_mod
    sys.modules["lancedb.pydantic"] = pyd_mod


def _install_scipy_stub() -> None:
    if "scipy" in sys.modules and "scipy.stats" in sys.modules:
        return
    import numpy as _np

    scipy_mod = types.ModuleType("scipy")
    stats_mod = types.ModuleType("scipy.stats")

    class _Norm:
        @staticmethod
        def cdf(x):
            x = _np.asarray(x, dtype=float)
            return 0.5 * (1.0 + _np.vectorize(math.erf)(x / _np.sqrt(2.0)))

        @staticmethod
        def pdf(x):
            x = _np.asarray(x, dtype=float)
            return (1.0 / _np.sqrt(2.0 * _np.pi)) * _np.exp(-0.5 * x * x)

    stats_mod.norm = _Norm()
    sys.modules["scipy"] = scipy_mod
    sys.modules["scipy.stats"] = stats_mod


def _install_irys_stub() -> None:
    if "irys_sdk" in sys.modules:
        return
    mod = types.ModuleType("irys_sdk")

    class Uploader:
        def __init__(self, *args, **kwargs):
            pass

        def upload(self, content, tags=None):
            return {"id": "stub-tx"}

    mod.Uploader = Uploader
    sys.modules["irys_sdk"] = mod


try:
    import opentelemetry  # type: ignore # noqa: F401
except Exception:
    _install_opentelemetry_stub()

try:
    import dependency_injector  # type: ignore # noqa: F401
except Exception:
    _install_dependency_injector_stub()

try:
    import sentence_transformers  # type: ignore # noqa: F401
except Exception:
    _install_sentence_transformers_stub()

try:
    import lancedb.pydantic  # type: ignore # noqa: F401
except Exception:
    _install_lancedb_stub()

try:
    import scipy.stats  # type: ignore # noqa: F401
except Exception:
    _install_scipy_stub()

try:
    import irys_sdk  # type: ignore # noqa: F401
except Exception:
    _install_irys_stub()
