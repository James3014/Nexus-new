from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

class AuditStrictness(str, Enum):
    RELAXED = "relaxed"
    STANDARD = "standard"
    STRICT = "strict"
    FORMAL = "formal"

@dataclass
class PhaseActions:
    allow_research: bool
    force_baseline: bool
    require_writeback: bool
    audit_strictness: AuditStrictness
    reasoning: str

def derive_phase_actions(phase_slo_summary: Dict[str, Any], task_type: str, risk_level: str) -> PhaseActions:
    # SLO Readiness check
    pass_rate = phase_slo_summary.get("overall_pass_rate", 0.0)
    ready = pass_rate >= 0.8  # 80% threshold for "stable" research
    
    is_bug = task_type.lower() in ["bug", "bugfix"]
    is_high_risk = risk_level.upper() in ["HIGH", "CRITICAL"]
    
    # 1. Decide allow_research
    allow_research = ready or is_high_risk
    
    # 2. Decide force_baseline
    # If not ready and not high risk, or specifically requested, force baseline
    force_baseline = not allow_research or (is_bug and not is_high_risk and not ready)
    
    # 3. Decide require_writeback
    # High risk or feature tasks always require writeback
    require_writeback = is_high_risk or task_type.lower() == "feature"
    
    # 4. Decide audit strictness
    strictness = AuditStrictness.STANDARD
    if is_high_risk:
        strictness = AuditStrictness.STRICT
    elif not ready:
        strictness = AuditStrictness.FORMAL if is_bug else AuditStrictness.STRICT
        
    reasoning = f"PassRate={pass_rate:.1%}, Task={task_type}, Risk={risk_level}. "
    reasoning += "AllowResearch." if allow_research else "DenyResearch."
    
    return PhaseActions(
        allow_research=allow_research,
        force_baseline=force_baseline,
        require_writeback=require_writeback,
        audit_strictness=strictness,
        reasoning=reasoning
    )
