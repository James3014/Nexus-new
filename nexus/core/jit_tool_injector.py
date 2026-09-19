from typing import Any, Dict, List, Optional, Tuple
import logging
from nexus.contracts.devspace_tool_authority import canonicalize_tool_intents
from nexus.core.state_contracts import NexusState

logger = logging.getLogger(__name__)

class JITToolInjector:
    """🧬 Nexus v26.0 JIT Managed Toolsets (Composio AO Dimension 2)
    
    具現化「動態工具遮罩」。根據當前子任務 Goal 僅注入必要工具。
    實作 MAX_TOKEN_PER_SHARD = 15,000 強制硬上限。
    """
    
    MAX_TOKEN_PER_SHARD = 15000
    
    @classmethod
    def apply_mask(cls, subtask_goal: str, all_tools: List[str]) -> List[str]:
        """根據子任務目標進行動態過濾"""
        logger.info(f"🎭 [JIT] Applying Tool Mask for Goal: {subtask_goal}")
        
        # 標籤化篩選 (Mock 實作：僅示範隔離效果)
        if "測試" in subtask_goal or "核驗" in subtask_goal:
            return [t for t in all_tools if "test" in t or "read" in t]
        if "具現" in subtask_goal or "修復" in subtask_goal:
            return [t for t in all_tools if "write" in t or "edit" in t or "replace" in t]
            
        return all_tools[:5] # 預設最小集合以防 Token 噪音

    @classmethod
    def apply_canonical_mask(cls, task_statement: str, candidate_tools: List[str]) -> List[str]:
        """Narrow an already-authorized DevSpace canonical tool-intent set.

        This path is separate from the legacy apply_mask() contract. It can only
        remove intents from the supplied candidate set and never consults route,
        provider, model, profile, or catalog state.
        """
        candidates = list(canonicalize_tool_intents(candidate_tools, field="candidate_tools"))
        text = " ".join(str(task_statement or "").lower().replace("_", " ").split())

        single_file = any(
            phrase in text
            for phrase in ("single file", "single-file", "one file", "this file", "one specific file")
        )
        read_only = any(
            phrase in text
            for phrase in ("read only", "read-only", "only read", "read this file", "inspect this file")
        )
        if single_file and read_only and "workspace.read" in candidates:
            return ["workspace.read"]

        search_terms = ("search", "find", "locate", "inspect", "review", "analyze", "analyse")
        verify_terms = ("test", "verify", "audit", "check", "run", "command")
        mutation_terms = (
            "implement", "fix", "repair", "patch", "write", "edit", "modify", "refactor", "build"
        )
        if any(term in text for term in mutation_terms):
            return candidates
        if any(term in text for term in verify_terms):
            allowed = {
                "workspace.read", "workspace.search_text", "workspace.search_paths",
                "workspace.list", "process.execute",
            }
            return [tool for tool in candidates if tool in allowed]
        if any(term in text for term in search_terms):
            allowed = {
                "workspace.read", "workspace.search_text", "workspace.search_paths", "workspace.list"
            }
            return [tool for tool in candidates if tool in allowed]
        return candidates

    @classmethod
    def check_token_quota(cls, current_usage: int):
        """🛡️ Token 硬上限核驗 (P4 規則)"""
        if current_usage >= cls.MAX_TOKEN_PER_SHARD:
            logger.error(f"🛑 [JIT:COST] Token 消耗 {current_usage} 超過分片配額 {cls.MAX_TOKEN_PER_SHARD}!")
            return False
        return True
