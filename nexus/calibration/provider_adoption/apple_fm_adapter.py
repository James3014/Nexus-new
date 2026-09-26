"""Apple Foundation Models CLI Candidate Adapter for Provider Adoption Experiments.

Reference Candidate: APPLE_FM_LOCAL_PROVIDER_PILOT_V1
Substrate: macOS /usr/bin/fm CLI

Strict Invariants:
1. If the Apple FM license is not agreed to ('fm license --status' exits 69 or reports 'Not agreed'),
   the adapter MUST mark the status as BLOCKED_BY_ENVIRONMENT with exact blocker
   APPLE_FM_LICENSE_NOT_AGREED.
2. The agent SHALL NOT execute 'sudo fm license' or accept the license autonomously.
3. Offline status MUST NOT be assumed. Without physical offline execution, it is UNKNOWN.
4. Zero mock/synthetic data may be masqueraded as physical Apple FM evidence.
"""

from __future__ import annotations

import datetime
import os
import platform
import subprocess

from nexus.calibration.provider_adoption.adapter import CandidateAdapter
from nexus.calibration.provider_adoption.capability import (
    CAP_001_PLAIN_TEXT,
    CapabilityProbeResult,
    CapabilityStatus,
    evaluate_capability_probe,
)
from nexus.calibration.provider_adoption.cohort import CohortCase
from nexus.calibration.provider_adoption.failure import (
    FailureClass,
    FailureObservationItem,
)
from nexus.calibration.provider_adoption.identity import (
    PhysicalIdentity,
    inspect_physical_host_identity,
)

APPLE_FM_BINARY = "/usr/bin/fm"


class AppleFMCandidateAdapter(CandidateAdapter):
    """Adapter for Apple Foundation Models CLI on macOS."""

    def __init__(self, binary_path: str = APPLE_FM_BINARY) -> None:
        self.binary_path = binary_path

    def is_environment_blocked(self) -> tuple[bool, str]:
        # 1. Platform check
        if platform.system() != "Darwin":
            return True, "UNSUPPORTED_PLATFORM: Apple FM is only supported on macOS."

        # 2. Binary existence
        if not os.path.isfile(self.binary_path):
            return True, f"APPLE_FM_CLI_UNAVAILABLE: Binary not found at {self.binary_path}."

        # 3. License status check
        try:
            res = subprocess.run(
                [self.binary_path, "license", "--status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()
            combined = f"{stdout}\n{stderr}".lower()

            if res.returncode == 69 or "not agreed" in combined:
                return (
                    True,
                    "APPLE_FM_LICENSE_NOT_AGREED: Run 'sudo fm license' to review and agree.",
                )
            if res.returncode != 0:
                return (
                    True,
                    f"APPLE_FM_PREFLIGHT_ERROR: fm license --status exited with code {res.returncode}.",
                )
        except Exception as exc:
            return True, f"APPLE_FM_PROBE_EXCEPTION: {str(exc)}"

        return False, ""

    def inspect_identity(self) -> PhysicalIdentity:
        blocked, reason = self.is_environment_blocked()
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        runtime_ver = "UNKNOWN"
        try:
            res = subprocess.run(
                [self.binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                runtime_ver = res.stdout.strip()
        except Exception:
            pass

        # Invariant 6.1: offline_verified is None (UNKNOWN) because no physical offline probe has run
        return inspect_physical_host_identity(
            provider_id="apple-fm",
            model_id="apple-foundation-model-v1",
            transport="apple_fm_cli",
            runtime_executable=self.binary_path,
            runtime_version=runtime_ver,
            adapter_generation="v1",
            model_generation="apple-fm-local-v1",
            timestamp=timestamp,
            offline_verified=None,
            network_dependency_observed="UNKNOWN",
        )

    def probe_capability(self, capability_id: str) -> CapabilityProbeResult:
        blocked, reason = self.is_environment_blocked()
        if blocked:
            return CapabilityProbeResult(
                capability_id=capability_id,
                status=CapabilityStatus.BLOCKED,
                physical_evidence=f"Execution blocked by environment: {reason}",
                exit_code=69 if "LICENSE" in reason else 1,
                latency_ms=0,
                error_message=reason,
            )

        # If not blocked, physical probe can be executed
        # Example for CAP-001:
        if capability_id == CAP_001_PLAIN_TEXT:
            try:
                t0 = datetime.datetime.now()
                res = subprocess.run(
                    [self.binary_path, "respond", "Hello"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                dt_ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
                return evaluate_capability_probe(
                    capability_id,
                    executed=True,
                    exit_code=res.returncode,
                    output_text=res.stdout.strip(),
                    latency_ms=dt_ms,
                    error_message=res.stderr.strip(),
                )
            except Exception as exc:
                return evaluate_capability_probe(
                    capability_id,
                    executed=True,
                    exit_code=1,
                    output_text="",
                    latency_ms=0,
                    error_message=str(exc),
                )

        return CapabilityProbeResult(
            capability_id=capability_id,
            status=CapabilityStatus.NOT_EVALUATED,
            physical_evidence="Capability probe not implemented or not evaluated.",
            exit_code=None,
            latency_ms=0,
        )

    def execute_case(self, case: CohortCase) -> tuple[str, bool, str | None, int]:
        blocked, reason = self.is_environment_blocked()
        if blocked:
            return "", False, FailureClass.AUTH_ERROR.value, 0

        try:
            t0 = datetime.datetime.now()
            res = subprocess.run(
                [self.binary_path, "respond", case.input_prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )
            dt_ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
            if res.returncode != 0:
                return "", False, FailureClass.PROCESS_CRASH.value, dt_ms
            output = res.stdout.strip()
            return output, True, None, dt_ms
        except subprocess.TimeoutExpired:
            return "", False, FailureClass.PROVIDER_TIMEOUT.value, 30000
        except Exception:
            return "", False, FailureClass.INTERNAL_ERROR.value, 0

    def inject_fault(self, failure_class: FailureClass) -> FailureObservationItem:
        # Invariant 6.3: Apple FM CLI does not currently expose a physical fault-injection API
        return FailureObservationItem(
            failure_class=failure_class,
            exercised=False,
            observed_fail_closed=None,
            observed_retry_behavior="NOT_EVALUATED",
            evidence_notes="Apple FM physical fault injection not supported in pilot v1.",
        )
