"""Compatibility facade for skill-fit ablation contracts.

New code should import focused modules directly:
- nexus.learning.skill_fit_ablation_core
- nexus.learning.skill_fit_followup
- nexus.learning.skill_fit_promotion
- nexus.learning.governance_mutants
"""

from __future__ import annotations

from nexus.learning.governance_mutants import (  # noqa: F401
    build_governance_candidate_bound_mutant_catalog,
    build_governance_candidate_bound_mutant_matrix,
    build_governance_mutant_live_sealing,
    build_governance_mutant_matrix_preflight,
    build_governance_mutant_promotion_gate,
    write_governance_candidate_bound_mutant_catalog,
    write_governance_candidate_bound_mutant_matrix,
    write_governance_mutant_live_sealing,
    write_governance_mutant_matrix_preflight,
    write_governance_mutant_promotion_gate,
)
from nexus.learning.skill_fit_ablation_core import *  # noqa: F401,F403
from nexus.learning.skill_fit_followup import (  # noqa: F401
    build_governance_candidate_v2_report,
    build_governance_mutant_lane_contract,
    build_governance_taskset_expansion_contract,
    build_research_candidate_v2_report,
    build_research_candidate_v3_report,
    build_research_external_candidate_pool,
    build_research_external_ingest_guard,
    build_research_skill_supply_gap_contract,
    build_research_source_discipline_skill_specs,
    build_skill_fit_cost_phase_contract,
    build_skill_fit_redesign_contract,
    build_skill_fit_row_level_rca,
    write_governance_candidate_v2_report,
    write_governance_mutant_lane_contract,
    write_governance_taskset_expansion_contract,
    write_research_candidate_v2_report,
    write_research_candidate_v3_report,
    write_research_external_candidate_pool,
    write_research_external_ingest_guard,
    write_research_skill_supply_gap_contract,
    write_research_source_discipline_skill_specs,
    write_skill_fit_cost_phase_contract,
    write_skill_fit_redesign_contract,
    write_skill_fit_row_level_rca,
)
from nexus.learning.skill_fit_promotion import (  # noqa: F401
    build_capability_skill_promotion_policy,
    build_skill_discovery_rerun_queue,
    build_skill_fit_completion_gate,
    build_skill_fit_runtime_policy_apply_gate,
    build_skill_fit_runtime_policy_overlay,
    build_skill_fit_runtime_promotion_review,
    build_skill_promotion_threshold_contract,
    select_skill_discovery_replay_row_ids,
    write_capability_skill_promotion_policy,
    write_skill_fit_completion_gate,
    write_skill_fit_runtime_policy_apply_gate,
    write_skill_fit_runtime_promotion_review,
    write_skill_promotion_threshold_contract,
)
from nexus.learning.skill_discovery_lane import (  # noqa: F401
    build_capability_skill_discovery_scheduler,
    write_capability_skill_discovery_scheduler,
)
