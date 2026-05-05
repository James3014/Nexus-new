from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

from nexus.core.state_io import StateIO
from nexus.services.workspace import WorkspaceManager
from nexus.core.policy_loader import PolicyLoader
from nexus.core.gate_evaluator import GateEvaluator
from nexus.core.metrics_aggregator import MetricsAggregator
from nexus.governance.hardened_validator import NexusHardenedValidator
from nexus.learning.lewm_predictor import LeWMPredictor
from nexus.services.memory import MemoryService
from nexus.engine.hub import NexusHub
from nexus.learning.skill_registry import SkillRegistry
from nexus.engine.federation import FederationLayer
from nexus.learning.vector_cache import VectorCache
from nexus.learning.sota_searcher import SOTASearcher
from nexus.core.neural_aggregator import NexusNeuralAggregator
from nexus.engine.planner_graph import HierarchicalGraphPlanner
from scripts.engine.nexus_transaction import TransactionManager

def build_engine_components(config: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    project_root = config.project_root
    run_dir = config.run_dir or (project_root / ".nexus" / "runs" / "engine")
    run_dir.mkdir(parents=True, exist_ok=True)
    
    env = os.getenv("NEXUS_ENV", "dev")
    policy = PolicyLoader.load(str(project_root), env=env)
    
    from nexus.learning.latent_predictor_v20 import get_latent_forecaster
    from nexus.engine.self_healing_selector import get_self_healing_selector
    from nexus.core.policy_manager import PolicyManager
    from nexus.engine.metrics.token_accumulator import TokenAccumulator
    from nexus.engine.health.evaluator import HealthEvaluator
    from nexus.engine.policies.research_policy import ResearchPolicy
    from nexus.services.mem_palace import MemPalace
    from nexus.research.wisdom.wisdom_vault import WisdomVault
    from nexus.core.belief_engine import BeliefEngine
    from nexus.core.context_hub import ContextDependencies, ContextHub
    from nexus.core.knowledge_injector import KnowledgeInjector
    from nexus.core.commander import Commander
    from nexus.engine.battle_swarm import BattleSwarm
    from nexus.engine.reflex_loop import ReflexLoop
    from nexus.engine.phase_executors import (
        build_diagnose_executor,
        build_plan_executor,
        build_research_executor,
    )
    from nexus.services.prompt_builder import PromptBuilder

    state_io = StateIO(project_root, run_dir=run_dir)
    workspace_mgr = WorkspaceManager(project_root)
    
    memory = MemoryService(project_root)
    hub = NexusHub(project_root)
    mem_palace = MemPalace(str(project_root))
    wisdom_vault = WisdomVault(str(project_root))
    belief_engine = BeliefEngine(project_root / ".nexus" / "belief_state.json")
    
    registry_path = project_root / ".nexus" / "registry" / "shared_skills.db"
    skill_registry = SkillRegistry(registry_path) if registry_path.exists() else None
    prompt_builder = PromptBuilder(str(project_root))
    knowledge_injector = KnowledgeInjector(
        skill_registry=skill_registry,
        mem_palace=mem_palace,
        wisdom_vault=wisdom_vault,
    )
    
    context_hub = kwargs.get("context_hub") or ContextHub(
        str(project_root),
        run_dir=str(run_dir),
        skill_registry=skill_registry,
        mem_palace=mem_palace,
        deps=ContextDependencies(
            memory_service=memory,
            wisdom_vault=wisdom_vault,
            belief_engine=belief_engine,
            knowledge_injector=knowledge_injector,
            prompt_builder=prompt_builder,
        ),
        strict_deps=True,
    )
    
    commander = kwargs.get("commander")
    if commander is None:
        commander = Commander(
            run_dir=run_dir,
            state_io=state_io,
            router=kwargs.get("router"),
            context_hub=context_hub,
        )
        
    if not hasattr(hub, "assemble_feature_pack"):
        hub.assemble_feature_pack = context_hub.assemble_feature_pack

    phase_executors = kwargs.get("phase_executors") or {
        "P": build_plan_executor(project_root, run_dir),
        "X": build_research_executor(project_root, run_dir),
        "D": build_diagnose_executor(project_root, run_dir, hub=hub),
    }

    components = {
        "run_dir": run_dir,
        "state_io": state_io,
        "workspace_mgr": workspace_mgr,
        "policy": policy,
        "gate_eval": GateEvaluator(policy),
        "metrics_agg": MetricsAggregator(),
        "validator": NexusHardenedValidator(),
        "latent_forecaster": get_latent_forecaster(str(project_root)),
        "ash_selector": get_self_healing_selector(str(project_root), env=env),
        "memory": memory,
        "belief_engine": belief_engine,
        "hub": hub,
        "policy_manager": PolicyManager(str(project_root), run_dir=str(run_dir)),
        "accumulator": TokenAccumulator(),
        "health_evaluator": HealthEvaluator(),
        "research_policy": ResearchPolicy(),
        "mem_palace": mem_palace,
        "skill_registry": skill_registry,
        "wisdom_vault": wisdom_vault,
        "prompt_builder": prompt_builder,
        "knowledge_injector": knowledge_injector,
        "context_hub": context_hub,
        "commander": commander,
        "battle_swarm": BattleSwarm(str(project_root), run_dir=str(run_dir)),
        "reflex_loop": ReflexLoop(str(project_root), memory_service=memory),
        "reporter": kwargs.get("reporter", hub),
        "phase_executors": phase_executors,
        "phases": kwargs.get("phases", {"P": "Planner", "D": "Diagnose", "R": "Repair", "X": "Research"}),
        "federation": FederationLayer(project_root),
        "vector_cache": VectorCache(project_root / ".nexus" / "vector_db"),
        "neural_aggregator": NexusNeuralAggregator(),
        "hardened_validator": NexusHardenedValidator(),
        "swarm_planner": HierarchicalGraphPlanner(project_root),
        "transaction_mgr": TransactionManager(project_root),
    }
    
    # Delayed Searcher init
    components["sota_searcher"] = SOTASearcher(components["vector_cache"])
    
    return components
