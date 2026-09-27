"""Requalification Policy module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.requalification_policy.v1
Defines criteria under which existing admission/qualification evidence becomes
STALE or requires full REQUALIFICATION.

Invariants:
- A change in provider/model/model-generation/runtime identity requires
  REQUALIFICATION_REQUIRED.
- A change in transport, bound source, host/hardware, OS/kernel/architecture,
  memory, runtime path, or adapter generation marks existing evidence as STALE.
- Tool-projection drift requires REQUALIFICATION_REQUIRED.
- Observation timestamp and offline/network observations are not execution identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from nexus.calibration.provider_adoption.identity import PhysicalIdentity

REQUALIFICATION_POLICY_SCHEMA = "nexus.provider_experiment.requalification_policy.v1"


class RequalificationVerdict(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    REQUALIFICATION_REQUIRED = "REQUALIFICATION_REQUIRED"


@dataclass(frozen=True)
class DriftDimension:
    dimension_name: str
    baseline_value: str
    current_value: str
    verdict: RequalificationVerdict
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_name": self.dimension_name,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "verdict": self.verdict.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RequalificationEvaluation:
    schema: str
    experiment_id: str
    overall_verdict: RequalificationVerdict
    dimensions: tuple[DriftDimension, ...]
    requires_full_requalification: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "experiment_id": self.experiment_id,
            "overall_verdict": self.overall_verdict.value,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "requires_full_requalification": self.requires_full_requalification,
            "summary": self.summary,
        }


def evaluate_requalification(
    *,
    experiment_id: str,
    baseline_identity: PhysicalIdentity,
    current_identity: PhysicalIdentity,
    tool_projection_drift: bool = False,
) -> RequalificationEvaluation:
    dimensions: list[DriftDimension] = []

    def add_dimension(
        name: str,
        baseline_value: object,
        current_value: object,
        verdict: RequalificationVerdict,
        reason: str,
    ) -> None:
        if baseline_value == current_value:
            return
        dimensions.append(
            DriftDimension(
                name,
                str(baseline_value),
                str(current_value),
                verdict,
                reason,
            )
        )

    # Semantic/runtime identity drift invalidates inherited qualification.
    add_dimension(
        "provider_id",
        baseline_identity.provider_id,
        current_identity.provider_id,
        RequalificationVerdict.REQUALIFICATION_REQUIRED,
        "Provider ID mismatch requires full requalification.",
    )
    add_dimension(
        "model_id",
        baseline_identity.model_id,
        current_identity.model_id,
        RequalificationVerdict.REQUALIFICATION_REQUIRED,
        "Model ID mismatch requires full requalification.",
    )
    add_dimension(
        "model_generation",
        baseline_identity.model_generation,
        current_identity.model_generation,
        RequalificationVerdict.REQUALIFICATION_REQUIRED,
        "Model generation changed; semantic evidence cannot be inherited automatically.",
    )
    if (
        baseline_identity.runtime_executable_sha256 != "UNKNOWN"
        and current_identity.runtime_executable_sha256 != "UNKNOWN"
    ):
        add_dimension(
            "runtime_executable_sha256",
            baseline_identity.runtime_executable_sha256,
            current_identity.runtime_executable_sha256,
            RequalificationVerdict.REQUALIFICATION_REQUIRED,
            "Runtime executable binary hash changed.",
        )
    if (
        baseline_identity.runtime_version != "UNKNOWN"
        and current_identity.runtime_version != "UNKNOWN"
    ):
        add_dimension(
            "runtime_version",
            baseline_identity.runtime_version,
            current_identity.runtime_version,
            RequalificationVerdict.REQUALIFICATION_REQUIRED,
            "Runtime version changed.",
        )

    # Execution-environment/source drift requires review/targeted requalification,
    # but does not by itself prove a semantic model change.
    stale_dimensions = (
        (
            "transport",
            baseline_identity.transport,
            current_identity.transport,
            "Transport changed.",
        ),
        (
            "runtime_executable",
            baseline_identity.runtime_executable,
            current_identity.runtime_executable,
            "Runtime executable path changed.",
        ),
        (
            "host_identity",
            baseline_identity.host_identity,
            current_identity.host_identity,
            "Physical host identity changed.",
        ),
        (
            "hardware_identity",
            baseline_identity.hardware_identity,
            current_identity.hardware_identity,
            "Hardware identity changed.",
        ),
        (
            "os_version",
            baseline_identity.os_version,
            current_identity.os_version,
            "Operating system version changed.",
        ),
        (
            "kernel_version",
            baseline_identity.kernel_version,
            current_identity.kernel_version,
            "Kernel version changed.",
        ),
        (
            "architecture",
            baseline_identity.architecture,
            current_identity.architecture,
            "Hardware architecture changed.",
        ),
        (
            "adapter_generation",
            baseline_identity.adapter_generation,
            current_identity.adapter_generation,
            "Adapter generation changed.",
        ),
        (
            "source_commit_identity",
            baseline_identity.source_commit_identity,
            current_identity.source_commit_identity,
            "Bound source revision changed.",
        ),
        (
            "memory_gb",
            baseline_identity.memory_gb,
            current_identity.memory_gb,
            "Observed memory capacity changed.",
        ),
    )
    for name, baseline_value, current_value, reason in stale_dimensions:
        add_dimension(
            name,
            baseline_value,
            current_value,
            RequalificationVerdict.STALE,
            f"{reason} Prior evidence requires targeted review before reuse.",
        )

    if tool_projection_drift:
        dimensions.append(
            DriftDimension(
                "tool_projection",
                "baseline",
                "drifted",
                RequalificationVerdict.REQUALIFICATION_REQUIRED,
                "Tool projection schema or exposure changed.",
            )
        )

    # Calculate overall verdict
    if any(d.verdict == RequalificationVerdict.REQUALIFICATION_REQUIRED for d in dimensions):
        overall = RequalificationVerdict.REQUALIFICATION_REQUIRED
        summary = "Critical drift detected. Existing admission evidence cannot be inherited."
    elif any(d.verdict == RequalificationVerdict.STALE for d in dimensions):
        overall = RequalificationVerdict.STALE
        summary = "Environmental drift detected. Existing evidence is STALE; review required."
    else:
        overall = RequalificationVerdict.CURRENT
        summary = "No significant drift detected. Identity matches baseline."

    return RequalificationEvaluation(
        schema=REQUALIFICATION_POLICY_SCHEMA,
        experiment_id=experiment_id,
        overall_verdict=overall,
        dimensions=tuple(dimensions),
        requires_full_requalification=(overall == RequalificationVerdict.REQUALIFICATION_REQUIRED),
        summary=summary,
    )
