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

def phase_slo_pass_rate(phase_slo_summary: Dict[str, Any]) -> float:
    """Share of judged phases meeting the SLO, read from the real summary schema.

    ``PhaseSLOService.build_phase_slo_report`` writes ``phase_slo_pass`` and ``phases.<P>.{total,
    writeback_required, required_done_ratio, success_ratio}`` and never ``overall_pass_rate``;
    reading only that key made every real summary look like PassRate=0%.  An explicit
    ``overall_pass_rate`` is still honoured unless the summary also says ``phase_slo_pass`` is
    not true.

    Fail closed (#2715, after #2702): a summary whose ``phase_slo_pass`` is missing or not
    ``True`` is 0.0; a missing/unavailable summary is 0.0; a phase with no required write-back
    rows is not judged (its ``required_done_ratio`` defaults to 1.0 and proves nothing), so it
    never counts as passing, and a summary with no judged phase is 0.0 (no evidence -> not ready).
    """
    summary = phase_slo_summary if isinstance(phase_slo_summary, dict) else {}
    if "phase_slo_pass" in summary and summary.get("phase_slo_pass") is not True:
        return 0.0
    if "overall_pass_rate" in summary:
        return float(summary.get("overall_pass_rate") or 0.0)
    if str(summary.get("status") or "").upper() != "SUCCESS":
        return 0.0
    if summary.get("phase_slo_pass") is not True:
        return 0.0
    raw_phases = summary.get("phases")
    phases: Dict[str, Any] = raw_phases if isinstance(raw_phases, dict) else {}
    judged = [
        row
        for row in phases.values()
        if isinstance(row, dict)
        and int(row.get("total") or 0) > 0
        and int(row.get("writeback_required") or 0) > 0
    ]
    if not judged:
        return 0.0
    passing = sum(
        1
        for row in judged
        if float(row.get("required_done_ratio") or 0.0) >= 0.95
        and float(row.get("success_ratio") or 0.0) >= 0.5
    )
    return round(passing / len(judged), 4)


def derive_phase_actions(phase_slo_summary: Dict[str, Any], task_type: str, risk_level: str) -> PhaseActions:
    # SLO Readiness check
    pass_rate = phase_slo_pass_rate(phase_slo_summary)
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
    if isinstance(phase_slo_summary, dict) and phase_slo_summary.get("reason"):
        reasoning += f" SLO={phase_slo_summary.get('reason')}."
    
    return PhaseActions(
        allow_research=allow_research,
        force_baseline=force_baseline,
        require_writeback=require_writeback,
        audit_strictness=strictness,
        reasoning=reasoning
    )
