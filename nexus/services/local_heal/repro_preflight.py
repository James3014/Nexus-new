"""
ReproRunner Pre-flight Gate v1.0

Formally gates whether a task can enter the patch lane.
Determines: bug_reproduced, blocking_noise_present, next_stop_layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ReproPreflightResult:
    """Result of ReproRunner pre-flight diagnosis."""
    bug_reproduced: bool
    blocking_noise_present: bool
    repro_command: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    next_stop_layer: str = ""  # "localization" or "reprorunner"
    failure_reason: str = ""
    agent_fixable: bool = True
    
    @property
    def can_enter_patch_lane(self) -> bool:
        """Only enter patch lane if bug is reproduced AND no blocking noise."""
        return self.bug_reproduced and not self.blocking_noise_present


class ReproPreflightDiagnosis:
    """
    Pre-flight gate that determines whether a task can proceed to patch synthesis.
    
    Flow:
    1. Check if env failures are present
    2. If env_denoise fixed noise → re-check reproduction
    3. If bug reproduced → allow patch lane
    4. If not reproduced → stop at reprorunner
    """
    
    @staticmethod
    def diagnose(ctx) -> ReproPreflightResult:
        repro_success = bool(getattr(ctx, "reproduced", False))
        env_resolution = dict(getattr(ctx, "env_resolution", {}) or {})
        env_denoise = dict(getattr(ctx, "env_denoise", {}) or {})
        failure_reason = str(getattr(ctx, "failure_reason", "") or "")
        repro_script = str(getattr(ctx, "repro_script", "") or "")
        
        # Check for env blocking
        env_failed = not env_resolution.get("ready", True)
        env_noise = any(
            kw in failure_reason.upper()
            for kw in ["ENV_", "ENVIRONMENT", "IMPORT", "VERSION", "DEPENDENCY"]
        )
        
        # Case 1: Bug reproduced, no noise → allow patch lane
        if repro_success and not env_noise:
            return ReproPreflightResult(
                bug_reproduced=True,
                blocking_noise_present=False,
                repro_command=f"python reproduce_bug.py",
                evidence_refs=["repro_evidence.log"],
                next_stop_layer="localization",
                agent_fixable=False,
            )
        
        # Case 2: Bug reproduced but env noise present → noise was already handled
        if repro_success and env_noise:
            return ReproPreflightResult(
                bug_reproduced=True,
                blocking_noise_present=False,  # noise was resolved by env_denoise
                repro_command=f"python reproduce_bug.py",
                evidence_refs=["repro_evidence.log"],
                next_stop_layer="localization",
                agent_fixable=False,
            )
        
        # Case 3: Bug not reproduced, no env info → stop at reprorunner
        if not repro_success and not env_failed:
            return ReproPreflightResult(
                bug_reproduced=False,
                blocking_noise_present=False,
                evidence_refs=[],
                next_stop_layer="reprorunner",
                failure_reason="REPRO_NOT_REPRODUCED",
                agent_fixable=True,
            )
        
        # Case 4: Environment blocked → stop at env_resolver
        if env_failed:
            return ReproPreflightResult(
                bug_reproduced=False,
                blocking_noise_present=True,
                evidence_refs=["env_resolution.json"],
                next_stop_layer="env_resolver",
                failure_reason=failure_reason or "ENV_BLOCKED",
                agent_fixable=True,
            )
        
        # Default: uncertain → stop at reprorunner (fail-closed)
        return ReproPreflightResult(
            bug_reproduced=False,
            blocking_noise_present=True,
            evidence_refs=[],
            next_stop_layer="reprorunner",
            failure_reason=failure_reason or "REPRO_UNCERTAIN",
            agent_fixable=True,
        )
