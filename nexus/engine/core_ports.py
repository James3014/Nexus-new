"""Engine-side bindings for the ports declared in ``nexus.core.layer_ports`` (#1923).

The dependency points engine -> core: this module registers engine
collaborators on the core-owned port registry. Each module is imported
lazily when core resolves the port, exactly as the previous in-function
imports inside ``nexus.core`` did, so import cost, monkeypatching and
import-failure handling at the call sites are unchanged.
"""

from __future__ import annotations

from nexus.core.layer_ports import bind_lazy_ports

# port name -> (engine module, attribute); an empty attribute binds the module itself
CORE_ENGINE_PORTS: dict[str, tuple[str, str]] = {
    # nexus.core.capability_executor_registry
    "research.ResearchPhaseHandler": ("nexus.engine.phases.research", "ResearchPhaseHandler"),
    "autoreason.AutoreasonService": ("nexus.engine.autoreason_service", "AutoreasonService"),
    "autoreason.AutoreasonCandidate": ("nexus.engine.autoreason_service", "AutoreasonCandidate"),
    "battle_swarm.BattleSwarm": ("nexus.engine.battle_swarm", "BattleSwarm"),
    "sandbox_runner.SandboxRunner": ("nexus.engine.sandbox_runner", "SandboxRunner"),
    "sandbox_runner.run_confined_test": (
        "nexus.engine.confined_test_runner",
        "run_confined_test",
    ),
    "swarm_run.run_bounded_swarm": ("nexus.engine.swarm_run", "run_bounded_swarm"),
    "ultra_review.UltraReviewService": ("nexus.engine.ultra_review_service", "UltraReviewService"),
    "pregate.detect_project_language": ("nexus.engine.cli_pregate", "detect_project_language"),
    "pregate.run_cli_pregate": ("nexus.engine.cli_pregate", "run_cli_pregate"),
    "harness.build_harness_preflight_sensor": (
        "nexus.engine.harness_sensors",
        "build_harness_preflight_sensor",
    ),
    "ddtree.DDTreeAdapter": ("nexus.engine.ddtree_adapter", "DDTreeAdapter"),
    "completion.enforcer_module": ("nexus.engine.completion_enforcer", ""),
    "judge.DeterministicFakeJudgeProvider": (
        "nexus.engine.llm_judge_providers",
        "DeterministicFakeJudgeProvider",
    ),
    "judge.JudgeProviderUnavailable": (
        "nexus.engine.llm_judge_providers",
        "JudgeProviderUnavailable",
    ),
    "judge.OllamaJudgeProvider": (
        "nexus.engine.llm_judge_providers",
        "OllamaJudgeProvider",
    ),
    "judge.build_judge_providers_from_env": (
        "nexus.engine.llm_judge_providers",
        "build_judge_providers_from_env",
    ),
    "asi.ASIConstraintExtractor": ("nexus.engine.asi_constraints", "ASIConstraintExtractor"),
    "forecast.ForecastGateService": ("nexus.engine.forecast_gate_service", "ForecastGateService"),
    "forecast.get_self_healing_selector": (
        "nexus.engine.self_healing_selector",
        "get_self_healing_selector",
    ),
    # nexus.core.commander
    "audit.AuditPhaseHandler": ("nexus.engine.phases.audit", "AuditPhaseHandler"),
    # nexus.core.learning_steward (resolved at import time)
    "openseeker.MIN_EVOLUTION_STEPS": ("nexus.engine.openseeker_alignment", "MIN_EVOLUTION_STEPS"),
    # nexus.core.capability_selector
    "planner.CapabilityPlanner": ("nexus.engine.capability_planner", "CapabilityPlanner"),
    # nexus.core.router
    "receipts.attested_receipt_dict": ("nexus.engine.capability_receipts", "attested_receipt_dict"),
    # nexus.core.drone_engine (#2936: drone BASH runs local-model output in the OS sandbox)
    "model_output.run_model_command_string": (
        "nexus.engine.model_output_sandbox",
        "run_model_command_string",
    ),
}


def install_core_engine_ports() -> None:
    """Bind every engine collaborator core uses. Idempotent."""
    bind_lazy_ports(CORE_ENGINE_PORTS)
