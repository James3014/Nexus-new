from typing import Any, Dict, List, Optional, Tuple, TypedDict

class PipelineMetadata(TypedDict, total=False):
    # --- Pipeline 執行狀態 ---
    task_description: str
    pipeline_success: bool
    pipeline_outcome: Dict[str, Any]
    pipeline_terminal_state: str
    
    # --- Nexus v19 Evolution (Swarm & SOTA) ---
    swarm_mode: bool
    task_graph_nodes: int
    orchestration_pattern: str

    # --- 階段決策 ---
    phase_decisions: Dict[str, str]
    phase_skills: Dict[str, str]
    inherited_plan_strategy: str
    research_route: Dict[str, Any]

    # --- 審計結果 ---
    last_review_status: str
    last_patch_generated: bool
    last_patch_apply_success: bool
    last_no_change_reason: str
    last_proof_type: str
    last_proof_value: str
    sandbox_mode: str
    rejection_history: List[str]
    key_findings: List[str]
    metadata: Dict[str, Any]
    
    # --- JEPA Governance (Elite P2) ---
    sim_lewm: bool
    lewm_sim_status: str
    lewm_prediction_cost: float
    lewm_rejected_cost: float
    benchmark_run: bool
    auto_repair_enabled: bool
    task_type: str
    response_mode: str

    # --- Phantom Guard ---
    phantom_success_reason: str
    known_phantom_patterns: List[str]
    phantom_pattern_history: List[str]
    require_strict_proof: bool
    anti_hallucination_checks: int
    anti_hallucination_block_count: int
    anti_hallucination_pass_count: int

    # --- Escalation ---
    escalation_count: int
    escalation_triggered: bool
    escalation_root_cause: str
    human_review_required: bool
    human_review_reason: str

    # --- Pregate & Sentinel (v2.8 Neural) ---
    neural_veto: Optional[bool]
    neural_reason: Optional[str]
    pregate_skip: bool
    pregate_skip_reason: str
    cli_pregate_results: List[Dict[str, Any]]
    verification_commands: List[str]
    verification_exit_codes: List[int]

    # --- Learning ---
    matched_skills_count: int
    skill_context_loaded: str
    prior_winning_hypotheses: List[str]
    research_pack_path: str

    # --- Health ---
    health_snapshot: Dict[str, Any]
    self_heal_cycle: Dict[str, Any]
    auto_repair_last_result: Dict[str, Any]

    # --- Outcome ---
    nexus_outcome_v2: Dict[str, Any]
    plan_strategy_used: str
    cycle_root_cause: str
    cycle_analysis: Dict[str, Any]
    
    # --- Context & Chat (Phase 10) ---
    chat_history: List[Dict[str, Any]]
