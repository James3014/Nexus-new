from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditOutcome:
    """Structured audit result consumed by belief gates."""

    task_id: str
    assumption: str
    passed: bool
    evidence_id: str
    confidence: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BeliefGate(Protocol):
    """Minimal interface Orchestrator needs from belief governance."""

    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]:
        ...

    def assess_confidence(self, task_id: str, assumption: str = "") -> float:
        ...

    def update_belief(self, task_id: str, assumption: str, confidence: float, evidence_id: str) -> None:
        ...


@dataclass(frozen=True)
class HealingArtifact:
    """Portable self-healing recommendation contract for swarm transport."""

    task_id: str
    artifact_id: str
    artifact_type: str
    created_at: str
    evidence_id: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    signature_key_id: str = ""


@dataclass(frozen=True)
class SkillReceipt:
    """Portable receipt confirming the actual injection, usage and outcome of a specific Skill."""

    skill_id: str
    selected: bool
    used: bool
    evidence_id: str
    outcome: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class TelemetryReasonCodes:
    SUCCESS = "T000"
    TELEMETRY_MISSING = "T001"
    WALL_TIME_INVALID = "T002"
    TOKEN_USAGE_INVALID = "T003"
    OVERHEAD_INVALID = "T004"
    ALIGNMENT_FAILED = "T005"


@dataclass(frozen=True)
class TelemetryVerificationResult:
    is_valid: bool
    reason_code: str
    reason: str


@dataclass(frozen=True)
class CapabilityReceipt:
    """Rigorous artifact confirming that a capability was active, backed by concrete evidence & gates."""

    capability_name: str
    selected: bool
    invoked: bool
    evidence_id: str
    gate_passed: bool
    outcome: dict[str, Any] = field(default_factory=dict)
    skill_receipts: list[SkillReceipt] = field(default_factory=list)
    semantic_hash: str = ""
    evidence_alignment: bool = True
    telemetries: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    @property
    def verify_telemetry(self) -> TelemetryVerificationResult:
        if not self.evidence_alignment:
            return TelemetryVerificationResult(False, TelemetryReasonCodes.ALIGNMENT_FAILED, "Evidence alignment verification failed")
        if not self.telemetries:
            return TelemetryVerificationResult(False, TelemetryReasonCodes.TELEMETRY_MISSING, "Telemetry data is empty or missing")
        
        # Row-Keyed Hygiene and Source Classification checks
        source = self.telemetries.get("telemetry_source", "measured")
        if source in ("estimated", "unknown"):
            return TelemetryVerificationResult(False, TelemetryReasonCodes.TELEMETRY_MISSING, "Estimated or unknown telemetry is observation-only and cannot be claimed")
            
        if self.telemetries.get("has_infra_invalid", False):
            return TelemetryVerificationResult(False, TelemetryReasonCodes.TELEMETRY_MISSING, "Telemetry carries infra-invalid reason codes")

        if self.telemetries.get("model_calls", 0) > 0 and self.telemetries.get("token_usage", 0) <= 0:
            return TelemetryVerificationResult(False, TelemetryReasonCodes.TOKEN_USAGE_INVALID, "Model call occurred but tokens are missing (infra-invalid)")

        if self.telemetries.get("gateway_token_outlier_reason") == "stats_outlier_possible_cumulative":
            return TelemetryVerificationResult(False, TelemetryReasonCodes.TOKEN_USAGE_INVALID, "Stats outlier possible cumulative detected, public cost claim blocked")

        required_keys = ("wall_time_ms", "token_usage", "provider_costs", "overhead_ms")
        for key in required_keys:
            if key not in self.telemetries:
                return TelemetryVerificationResult(False, TelemetryReasonCodes.TELEMETRY_MISSING, f"Required telemetry key missing: {key}")
                
        if self.telemetries.get("wall_time_ms", 0) <= 0:
            return TelemetryVerificationResult(False, TelemetryReasonCodes.WALL_TIME_INVALID, "wall_time_ms must be strictly greater than 0")
        if self.telemetries.get("token_usage", 0) <= 0:
            return TelemetryVerificationResult(False, TelemetryReasonCodes.TOKEN_USAGE_INVALID, "token_usage must be strictly greater than 0")
            
        return TelemetryVerificationResult(True, TelemetryReasonCodes.SUCCESS, "Telemetry verification passed successfully")

    @property
    def is_claimable(self) -> bool:
        return self.verify_telemetry.is_valid


@dataclass(frozen=True)
class SkillSlot:
    """Rigorous HEEP/EMAS Role slot indicating how a skill is deployed within a capability."""

    role: str  # 'SCOUT', 'LOGIC', 'AUDIT'
    skill_id: str
    injected: bool = False
    used: bool = False


@dataclass(frozen=True)
class CapabilityExecutionPlan:
    """A serialized DAG of capability phases to be executed with fallback & replan logic."""

    plan_id: str
    task_id: str
    phases: list[str] = field(default_factory=list)  # Ordered sublist of S,P,X,D,R,A,C
    required_capabilities: list[str] = field(default_factory=list)
    skill_slots: dict[str, list[SkillSlot]] = field(default_factory=dict)  # cap_name -> list[SkillSlot]
    constraints: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


