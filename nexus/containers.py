from dependency_injector import containers, providers
from pathlib import Path

# 延遲導入服務，避免循環依賴
from nexus.services.git import GitManager
from nexus.services.llm import LLMClient
from nexus.services.linter import Linter
from nexus.services.patcher import SafePatcher
from nexus.services.reporter import Reporter
from nexus.services.workspace import WorkspaceManager
from nexus.services.prompt_builder import PromptBuilder
from nexus.core.commander import Commander
from nexus.core.context_hub import ContextHub
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter

class NexusContainer(containers.DeclarativeContainer):
    """
    🏗️ Nexus Dependency Injection Container
    全域服務註冊中心，管理所有 singleton 與 factory。
    """
    
    config = providers.Configuration()
    
    # 核心基礎服務 (Singletons)
    project_root = providers.Configuration()
    
    state_io = providers.Singleton(
        StateIO,
        project_root=project_root
    )
    
    git = providers.Singleton(GitManager)
    
    linter = providers.Singleton(Linter)
    
    patcher = providers.Singleton(SafePatcher)
    
    reporter = providers.Singleton(Reporter)
    
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
    
    router = providers.Singleton(
        SkillsRouter,
        project_root=project_root
    )
    
    context_hub = providers.Singleton(
        ContextHub,
        project_root=project_root
    )

    commander = providers.Singleton(
        Commander,
        run_dir=project_root,
        state_io=state_io,
        router=router,
        context_hub=context_hub
    )

    # 引擎工廠 (Factory for Orchestrator/Engine)
    from nexus.core.orchestrator import NexusOrchestrator
    from nexus.engine.coordinator import NexusEngine
    
    orchestrator_factory = providers.Factory(
        NexusOrchestrator,
        git=git,
        llm=llm,
        linter=linter,
        patcher=patcher,
        reporter=reporter,
        workspace=workspace,
        router=router,
        commander=commander,
        context_hub=context_hub,
        state_io=state_io
    )

    engine_factory = providers.Factory(
        NexusEngine,
        state_io=state_io,
        commander=commander,
        router=router
    )
