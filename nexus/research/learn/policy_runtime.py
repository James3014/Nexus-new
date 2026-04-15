from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional
from .phase_policy import derive_phase_actions, PhaseActions

def load_phase_policy(project_root: Path, task_type: str, risk_level: str) -> PhaseActions:
    """Load and derive the latest phase policy based on SLO state."""
    from nexus.research.learn_mode import LearnModeService
    learn_svc = LearnModeService(project_root)
    slo_summary = learn_svc.read_phase_slo_summary()
    return derive_phase_actions(slo_summary, task_type, risk_level)

def decide_research_engine(project_root: Path, task_type: str, risk_level: str) -> str:
    """Return the chosen engine: baseline, hyper_sprint, or nightshift."""
    actions = load_phase_policy(project_root, task_type, risk_level)
    
    if actions.force_baseline:
        return "baseline"
        
    # Logic: if allow_research is true, default to hyper_sprint for small runs,
    # nightshift for large/batch runs (to be refined in scheduler).
    return "hyper_sprint" if actions.allow_research else "baseline"
