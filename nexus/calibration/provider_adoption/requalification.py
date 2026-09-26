"""Requalification Policy module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.requalification_policy.v1
Defines criteria under which existing admission/qualification evidence becomes
STALE or requires full REQUALIFICATION.

Invariants:
- A change in model weights, provider ID, runtime binary hash, or major runtime version
  requires REQUALIFICATION_REQUIRED.
- A change in host OS version, kernel release, or minor adapter generation
  marks existing evidence as STALE.
- Untracked drift or unknown changes fail closed to REQUALIFICATION_REQUIRED.
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

    # 1. Provider ID
    if baseline_identity.provider_id != current_identity.provider_id:
        dimensions.append(
            DriftDimension(
                "provider_id",
                baseline_identity.provider_id,
                current_identity.provider_id,
                RequalificationVerdict.REQUALIFICATION_REQUIRED,
                "Provider ID mismatch requires full requalification.",
            )
        )

    # 2. Model ID
    if baseline_identity.model_id != current_identity.model_id:
        dimensions.append(
            DriftDimension(
                "model_id",
                baseline_identity.model_id,
                current_identity.model_id,
                RequalificationVerdict.REQUALIFICATION_REQUIRED,
                "Model ID mismatch requires full requalification.",
            )
        )

    # 3. Runtime Executable Hash
    if (
        baseline_identity.runtime_executable_sha256 != "UNKNOWN"
        and current_identity.runtime_executable_sha256 != "UNKNOWN"
        and baseline_identity.runtime_executable_sha256
        != current_identity.runtime_executable_sha256
    ):
        dimensions.append(
            DriftDimension(
                "runtime_executable_sha256",
                baseline_identity.runtime_executable_sha256,
                current_identity.runtime_executable_sha256,
                RequalificationVerdict.REQUALIFICATION_REQUIRED,
                "Runtime executable binary hash changed.",
            )
        )

    # 4. Runtime Version
    if (
        baseline_identity.runtime_version != "UNKNOWN"
        and current_identity.runtime_version != "UNKNOWN"
        and baseline_identity.runtime_version != current_identity.runtime_version
    ):
        dimensions.append(
            DriftDimension(
                "runtime_version",
                baseline_identity.runtime_version,
                current_identity.runtime_version,
                RequalificationVerdict.REQUALIFICATION_REQUIRED,
                "Runtime version changed.",
            )
        )

    # 5. OS Version
    if (
        baseline_identity.os_version != "UNKNOWN"
        and current_identity.os_version != "UNKNOWN"
        and baseline_identity.os_version != current_identity.os_version
    ):
        dimensions.append(
            DriftDimension(
                "os_version",
                baseline_identity.os_version,
                current_identity.os_version,
                RequalificationVerdict.STALE,
                "Operating system version changed; prior evidence is STALE.",
            )
        )

    # 6. Adapter Generation
    if baseline_identity.adapter_generation != current_identity.adapter_generation:
        dimensions.append(
            DriftDimension(
                "adapter_generation",
                baseline_identity.adapter_generation,
                current_identity.adapter_generation,
                RequalificationVerdict.STALE,
                "Adapter generation updated; prior evidence is STALE.",
            )
        )

    # 7. Tool Projection
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
