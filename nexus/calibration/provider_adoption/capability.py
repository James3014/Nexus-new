"""G2 Capability Matrix module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.capability_matrix.v1
Defines standard capability probes and evaluates physical evidence.

False-Green Defense (Invariant 6.2):
- Command exit code 0 alone NEVER equals SUPPORTED.
- "Environment has no blocker" alone NEVER equals SUPPORTED.
- Every SUPPORTED status requires concrete, verified physical execution evidence.
- Capabilities not physically probed MUST remain NOT_EVALUATED or UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

CAPABILITY_MATRIX_SCHEMA = "nexus.provider_experiment.capability_matrix.v1"


class CapabilityStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    NOT_EVALUATED = "NOT_EVALUATED"


# Canonical generic capability probe IDs
CAP_001_PLAIN_TEXT = "CAP-001"
CAP_002_STRUCTURED_JSON = "CAP-002"
CAP_003_SCHEMA_CONSTRAINED = "CAP-003"
CAP_004_CLASSIFICATION = "CAP-004"
CAP_005_EXTRACTION = "CAP-005"
CAP_006_SUMMARIZATION = "CAP-006"
CAP_007_STREAMING = "CAP-007"
CAP_008_TOOL_CALLING = "CAP-008"
CAP_009_LONG_CONTEXT = "CAP-009"
CAP_010_OFFLINE_EXECUTION = "CAP-010"
CAP_011_REPEATABILITY = "CAP-011"

ALL_CAPABILITY_IDS: tuple[str, ...] = (
    CAP_001_PLAIN_TEXT,
    CAP_002_STRUCTURED_JSON,
    CAP_003_SCHEMA_CONSTRAINED,
    CAP_004_CLASSIFICATION,
    CAP_005_EXTRACTION,
    CAP_006_SUMMARIZATION,
    CAP_007_STREAMING,
    CAP_008_TOOL_CALLING,
    CAP_009_LONG_CONTEXT,
    CAP_010_OFFLINE_EXECUTION,
    CAP_011_REPEATABILITY,
)


@dataclass(frozen=True)
class CapabilityProbeResult:
    capability_id: str
    status: CapabilityStatus
    physical_evidence: str
    exit_code: int | None
    latency_ms: int
    raw_output: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "status": self.status.value,
            "physical_evidence": self.physical_evidence,
            "exit_code": self.exit_code,
            "latency_ms": self.latency_ms,
            "raw_output": self.raw_output,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class CapabilityMatrix:
    schema: str
    probes: dict[str, CapabilityProbeResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "probes": {k: v.to_dict() for k, v in self.probes.items()},
        }

    def get_status(self, capability_id: str) -> CapabilityStatus:
        if capability_id not in self.probes:
            return CapabilityStatus.NOT_EVALUATED
        return self.probes[capability_id].status

    def is_supported(self, capability_id: str) -> bool:
        return self.get_status(capability_id) == CapabilityStatus.SUPPORTED


def evaluate_capability_probe(
    capability_id: str,
    *,
    executed: bool,
    exit_code: int | None,
    output_text: str,
    latency_ms: int,
    semantic_validator: Any = None,
    error_message: str = "",
) -> CapabilityProbeResult:
    """Evaluate capability probe with strict False-Green defense.

    Rules:
    - If not executed: NOT_EVALUATED.
    - exit_code == 0 alone NEVER makes status SUPPORTED.
    - Output must be non-empty and satisfy semantic validator if provided.
    - If exit_code != 0: BLOCKED or UNSUPPORTED depending on error.
    """
    if not executed:
        return CapabilityProbeResult(
            capability_id=capability_id,
            status=CapabilityStatus.NOT_EVALUATED,
            physical_evidence="Probe not executed; unprobed capabilities fail closed to NOT_EVALUATED.",
            exit_code=exit_code,
            latency_ms=0,
            error_message=error_message or "not_executed",
        )

    if exit_code is None:
        return CapabilityProbeResult(
            capability_id=capability_id,
            status=CapabilityStatus.UNKNOWN,
            physical_evidence="Execution produced no exit code.",
            exit_code=None,
            latency_ms=latency_ms,
            error_message=error_message or "missing_exit_code",
        )

    if exit_code != 0:
        return CapabilityProbeResult(
            capability_id=capability_id,
            status=CapabilityStatus.BLOCKED
            if "license" in error_message.lower() or exit_code == 69
            else CapabilityStatus.UNSUPPORTED,
            physical_evidence=f"Command failed with non-zero exit code: {exit_code}",
            exit_code=exit_code,
            latency_ms=latency_ms,
            error_message=error_message,
        )

    # Invariant: exit 0 alone is NOT enough! Must verify output content.
    if not output_text or not output_text.strip():
        return CapabilityProbeResult(
            capability_id=capability_id,
            status=CapabilityStatus.UNSUPPORTED,
            physical_evidence="Command exited with 0 but returned empty or whitespace-only output.",
            exit_code=exit_code,
            latency_ms=latency_ms,
            raw_output=output_text,
            error_message="empty_output",
        )

    if semantic_validator:
        try:
            valid, reason = semantic_validator(output_text)
            if not valid:
                return CapabilityProbeResult(
                    capability_id=capability_id,
                    status=CapabilityStatus.PARTIAL,
                    physical_evidence=f"Output failed semantic validation: {reason}",
                    exit_code=exit_code,
                    latency_ms=latency_ms,
                    raw_output=output_text,
                    error_message=reason,
                )
        except Exception as exc:
            return CapabilityProbeResult(
                capability_id=capability_id,
                status=CapabilityStatus.UNSUPPORTED,
                physical_evidence=f"Semantic validator exception: {exc}",
                exit_code=exit_code,
                latency_ms=latency_ms,
                raw_output=output_text,
                error_message=str(exc),
            )

    return CapabilityProbeResult(
        capability_id=capability_id,
        status=CapabilityStatus.SUPPORTED,
        physical_evidence=f"Physical execution succeeded with valid output ({len(output_text)} chars).",
        exit_code=exit_code,
        latency_ms=latency_ms,
        raw_output=output_text,
    )


def create_initial_capability_matrix() -> CapabilityMatrix:
    """Create initial matrix where all capabilities are NOT_EVALUATED."""
    probes = {
        cid: CapabilityProbeResult(
            capability_id=cid,
            status=CapabilityStatus.NOT_EVALUATED,
            physical_evidence="Initial state prior to probe execution.",
            exit_code=None,
            latency_ms=0,
        )
        for cid in ALL_CAPABILITY_IDS
    }
    return CapabilityMatrix(schema=CAPABILITY_MATRIX_SCHEMA, probes=probes)
