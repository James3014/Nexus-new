"""G4 Operational Metrics module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.operational_metrics.v1
Aggregates runtime latency, throughput, error rates, cold-start latency,
and offline execution status.

False-Green Defense:
- offline_status is marked VERIFIED_OFFLINE only if backed by physical offline execution evidence.
- Otherwise it remains UNKNOWN or NOT_EVALUATED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from nexus.calibration.provider_adoption.cohort import EvaluationResult, QualityVerdict

OPERATIONAL_METRICS_SCHEMA = "nexus.provider_experiment.operational_metrics.v1"


@dataclass(frozen=True)
class OperationalMetrics:
    schema: str
    total_cases: int
    successful_cases: int
    failed_cases: int
    error_rate: float
    accuracy: float
    format_compliance_rate: float
    semantic_correctness_rate: float
    p50_latency_ms: int
    p95_latency_ms: int
    min_latency_ms: int
    max_latency_ms: int
    mean_latency_ms: float
    cold_start_latency_ms: int
    throughput_rps: float
    offline_status: str
    network_dependency: str
    estimated_cost_usd_per_1k_tokens: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "total_cases": self.total_cases,
            "successful_cases": self.successful_cases,
            "failed_cases": self.failed_cases,
            "error_rate": self.error_rate,
            "accuracy": self.accuracy,
            "format_compliance_rate": self.format_compliance_rate,
            "semantic_correctness_rate": self.semantic_correctness_rate,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "mean_latency_ms": self.mean_latency_ms,
            "cold_start_latency_ms": self.cold_start_latency_ms,
            "throughput_rps": self.throughput_rps,
            "offline_status": self.offline_status,
            "network_dependency": self.network_dependency,
            "estimated_cost_usd_per_1k_tokens": self.estimated_cost_usd_per_1k_tokens,
        }


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    values.sort()
    idx = int(math.ceil(percentile * len(values))) - 1
    idx = max(0, min(idx, len(values) - 1))
    return values[idx]


def aggregate_operational_metrics(
    results: Sequence[EvaluationResult],
    *,
    cold_start_latency_ms: int = 0,
    total_duration_sec: float = 1.0,
    offline_verified: bool | None = None,
    network_dependency_observed: str = "UNKNOWN",
    estimated_cost_usd: float = 0.0,
) -> OperationalMetrics:
    total = len(results)
    if total == 0:
        return OperationalMetrics(
            schema=OPERATIONAL_METRICS_SCHEMA,
            total_cases=0,
            successful_cases=0,
            failed_cases=0,
            error_rate=0.0,
            accuracy=0.0,
            format_compliance_rate=0.0,
            semantic_correctness_rate=0.0,
            p50_latency_ms=0,
            p95_latency_ms=0,
            min_latency_ms=0,
            max_latency_ms=0,
            mean_latency_ms=0.0,
            cold_start_latency_ms=cold_start_latency_ms,
            throughput_rps=0.0,
            offline_status="NOT_EVALUATED",
            network_dependency=network_dependency_observed,
            estimated_cost_usd_per_1k_tokens=estimated_cost_usd,
        )

    latencies = [r.latency_ms for r in results]
    passes = sum(1 for r in results if r.quality_result == QualityVerdict.PASS)
    schema_valids = sum(1 for r in results if r.schema_valid)
    fails = sum(
        1 for r in results if r.quality_result == QualityVerdict.FAIL or r.failure_class is not None
    )

    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    min_lat = min(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0
    mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

    rps = total / total_duration_sec if total_duration_sec > 0 else 0.0

    if offline_verified is True:
        offline_status = "VERIFIED_OFFLINE"
    elif offline_verified is False:
        offline_status = "ONLINE_REQUIRED"
    else:
        offline_status = "UNKNOWN"

    return OperationalMetrics(
        schema=OPERATIONAL_METRICS_SCHEMA,
        total_cases=total,
        successful_cases=passes,
        failed_cases=fails,
        error_rate=round(fails / total, 4),
        accuracy=round(passes / total, 4),
        format_compliance_rate=round(schema_valids / total, 4),
        semantic_correctness_rate=round(passes / total, 4),
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        min_latency_ms=min_lat,
        max_latency_ms=max_lat,
        mean_latency_ms=round(mean_lat, 2),
        cold_start_latency_ms=cold_start_latency_ms,
        throughput_rps=round(rps, 2),
        offline_status=offline_status,
        network_dependency=network_dependency_observed,
        estimated_cost_usd_per_1k_tokens=estimated_cost_usd,
    )
