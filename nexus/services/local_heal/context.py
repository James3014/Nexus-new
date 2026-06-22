import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from nexus.services.local_heal.errors import PatchError

@dataclass
class GovernanceContext:
    """🛡️ Nexus Governance & Probe Metadata (Fail-closed / Accountability)"""
    expected_stop_layer: str = "verification"
    expected_reason_family: str = "SOLVED"
    probe_goal: str = "general-repair"
    
    # Audit Signals
    gate_exit: str = "unknown"
    actual_reason_family: str = "unknown"
    stop_layer_matched: bool = False
    family_matched: bool = False

from nexus.services.local_heal.interface import RepairPlan, LocalizedFile

@dataclass
class OperationalContext:
    """⚙️ Nexus Operational State (Artifacts / Evidence)"""
    instance_id: str
    repo_dir: Path
    problem_statement: str
    
    # Memory control (BMF5: memory_enabled flag)
    memory_enabled: bool = True  # Set to False for nexus_memory_off arm

    # Phase 1: Reproduction
    repro_script: str = ""
    repro_evidence: str = ""
    reproduced: bool = False
    
    # Phase 2: Planning
    plan: Optional[RepairPlan] = None
    reasoning_mode: str = "INTUITIVE"
    
    # Phase 3: Localization
    localized_files: List[LocalizedFile] = field(default_factory=list)
    
    # Phase 4: Targeted Edit
    system_prompt: str = ""
    user_prompt: str = ""
    attempt: int = 1
    max_tries: int = 3
    final_patch: str = ""
    repair_specification: str = ""  # 🛡️ 規格中心修復：邏輯修復意圖 (Intent-based)
    errors: List[PatchError] = field(default_factory=list)
    model_decisions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Phase 5: Verification
    evaluation_report: str = ""
    hidden_verifier_passed: bool = False
    solve_eligible: bool = False
    
    # Common
    failure_reason: str = ""
    receipt_path: str = ""
    runner_completed: bool = False
    python_executable: str = ""
    auto_heal_enabled: bool = False
    skip_reproduction: bool = False
    wall_time_sec: float = 0.0
    token_telemetry_status: str = "not_applicable"
    token_total_estimated: int = 0
    syntax_gate_passed: bool = True
    prompt_variant_id: str = "default"
    refusal_detected: bool = False
    empty_response: bool = False
    env_denoise: Dict[str, Any] = field(default_factory=dict)
    env_resolution: Dict[str, Any] = field(default_factory=dict)
    run_group: str = ""

    # T1.6: Semantic retry telemetry
    _semantic_retry_telemetry: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HealContext:
    """🧬 Unified Nexus Heal Context (Composition of Operational & Governance)"""
    op: OperationalContext
    gov: GovernanceContext
    
    @property
    def instance_id(self): return self.op.instance_id
    
    # For backward compatibility during refactoring
    def __getattr__(self, name):
        if hasattr(self.op, name):
            return getattr(self.op, name)
        if hasattr(self.gov, name):
            return getattr(self.gov, name)
        raise AttributeError(f"HealContext has no attribute {name}")
