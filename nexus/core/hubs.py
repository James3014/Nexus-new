from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class NexusInfraHub:
    """🎬 基礎設施集線器: 管理 Git, Workspace, Linter, Patcher"""
    git: Any
    workspace: Any
    linter: Any
    patcher: Any

@dataclass
class NexusIntelHub:
    """🧠 智能集線器: 管理 LLM, ContextHub, Commander"""
    llm: Any
    context_hub: Any
    commander: Any

@dataclass
class NexusGovHub:
    """⚖️ 治理集線器: 管理 Router, Reporter, StateIO"""
    router: Any
    reporter: Any
    state_io: Any
