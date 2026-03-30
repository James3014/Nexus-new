from dependency_injector import containers, providers
from pathlib import Path

# 延遲導入服務，避免循環依賴
from nexus.services.git import GitManager
from nexus.services.gateway import BattlesuitGateway as LLMClient
from nexus.services.linter import Linter
from nexus.services.patcher import SafePatcher
from nexus.services.reporter import Reporter
from nexus.services.workspace import WorkspaceManager
from nexus.services.prompt_builder import PromptBuilder
from nexus.services.reviewer import GatewayReviewLoop
from nexus.core.commander import Commander
from nexus.core.context_hub import ContextHub
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter
from nexus.core.hubs import NexusInfraHub, NexusIntelHub, NexusGovHub
from nexus.services.memory import MemoryService
from nexus.services.predictor import Predictor
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.engine.phases.research import ResearchPhaseHandler
from nexus.engine.phases.repair import RepairPhaseHandler

def _create_nexus_engine(**kwargs):
    from nexus.engine.coordinator import NexusEngine
    from nexus.engine.config import EngineConfig
    
    # 提取 EngineConfig 所需的參數
    import inspect
    sig = inspect.signature(EngineConfig)
    config_keys = sig.parameters.keys()
    
    config_args = {k: kwargs.pop(k) for k in config_keys if k in kwargs}
    config = EngineConfig(**config_args)
    
    return NexusEngine(config=config, **kwargs)


class NexusContainer(containers.DeclarativeContainer):
    """
    🏗️ Nexus Dependency Injection Container
    全域服務註冊中心，管理所有 singleton 與 factory。
    """
    
    config = providers.Configuration()
    
    # 核心基礎服務 (Singletons)
    project_root = providers.Configuration()
    run_dir = providers.Configuration() # Phase C: Track run_dir in container
    
    state_io = providers.Singleton(
        StateIO,
        project_root=project_root,
        run_dir=run_dir
    )
    
    git = providers.Singleton(GitManager)
    
    predictor = providers.Singleton(Predictor)
    
    memory_service = providers.Singleton(
        MemoryService,
        project_root=project_root,
        run_dir=run_dir
    )

    router = providers.Singleton(
        SkillsRouter,
        project_root=project_root,
        run_dir=run_dir
    )

    linter = providers.Singleton(Linter)
    
    patcher = providers.Singleton(
        SafePatcher,
        lock_dir=project_root,
        project_root=project_root
    )
    
    reporter = providers.Singleton(
        Reporter,
        project_root=project_root,
        run_dir=run_dir
    )

    workspace = providers.Singleton(
        WorkspaceManager,
        project_root=project_root
    )
    
    prompt_builder = providers.Singleton(
        PromptBuilder,
        project_root=project_root
    )
    
    llm = providers.Singleton(
        LLMClient,
        project_root=project_root
    )

    context_hub = providers.Singleton(
        ContextHub,
        project_root=project_root,
        memory_service=memory_service,
        run_dir=run_dir
    )

    commander = providers.Singleton(
        Commander,
        run_dir=run_dir,
        state_io=state_io,
        router=router,
        context_hub=context_hub
    )

    # 引擎工廠 (Factory for Orchestrator/Engine)

    def _create_orchestrator(**kwargs):
        from nexus.core.orchestrator import NexusOrchestrator
        from nexus.core.config import OrchestratorConfig
        import inspect
        sig = inspect.signature(OrchestratorConfig)
        config_keys = sig.parameters.keys()
        config_args = {k: kwargs.pop(k) for k in config_keys if k in kwargs}
        config = OrchestratorConfig(**config_args)
        # 過濾 DI 框架注入的非業務參數 (如 scope)
        import inspect
        orchestrator_sig = inspect.signature(NexusOrchestrator.__init__)
        valid_keys = set(orchestrator_sig.parameters.keys()) - {"self"}
        extra_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return NexusOrchestrator(config=config, **extra_kwargs)

    infra_hub = providers.Factory(
        NexusInfraHub,
        git=git,
        workspace=workspace,
        linter=linter,
        patcher=patcher
    )

    intel_hub = providers.Factory(
        NexusIntelHub,
        llm=llm,
        context_hub=context_hub,
        commander=commander
    )

    gov_hub = providers.Factory(
        NexusGovHub,
        router=router,
        reporter=reporter,
        state_io=state_io
    )

    orchestrator_factory = providers.Factory(
        _create_orchestrator,
        infra=infra_hub,
        intel=intel_hub,
        gov=gov_hub
    )

    research_phase = providers.Factory(
        ResearchPhaseHandler,
        project_root=project_root,
        run_dir=run_dir
    )
    
    repair_phase = providers.Factory(
        RepairPhaseHandler,
        project_root=project_root,
        run_dir=run_dir,
        router=router,
        orchestrator_factory=orchestrator_factory.provider
    )

    planner_phase = providers.Factory( 
        PlannerPhaseHandler,
        project_root=project_root,
        run_dir=run_dir,
        predictor=predictor
    )

    from nexus.engine.phases.diagnose import DiagnosticPhaseHandler
    diagnostic_phase = providers.Factory(
        DiagnosticPhaseHandler,
        project_root=project_root,
        run_dir=run_dir,
        hub=context_hub
    )

    engine_factory = providers.Factory(
        _create_nexus_engine,
        project_root=project_root,
        run_dir=run_dir,
        state_io=state_io,
        commander=commander,
        router=router,
        reporter=reporter,
        phases=providers.Dict(
            P=planner_phase,
            X=research_phase,
            D=diagnostic_phase,
            R=repair_phase
        )
    )
