from typing import Any, Dict, List, Optional
from enum import Enum

class Phase(str, Enum):
    P = "plan"        # Planner
    X = "research"    # External Research
    D = "diagnose"    # Diagnosis & Triage
    R = "repair"      # Coding & Patching
    A = "audit"       # Verification & Testing
    C = "crystallize" # Commit & Lesson Capture

# 🧬 Composio P0: 語義工具分組 (JIT Injection)
SKILL_GROUPS: Dict[Phase, List[str]] = {
    Phase.P: ["read_file", "git_status", "list_dir", "view_file", "nexus:lookup-skill"],
    Phase.X: ["read_file", "search_web", "grep_search", "view_file", "read_resource"],
    Phase.D: ["read_file", "grep_search", "run_command", "view_file", "list_dir", "command_status"],
    Phase.R: ["read_file", "replace_file_content", "multi_replace_file_content", "write_to_file", "run_command", "safe_patch"],
    Phase.A: ["read_file", "run_command", "view_file", "git_diff", "command_status", "pytest"],
    Phase.C: ["run_command", "write_to_file", "write_memory", "git_commit"]
}

PHASE_TOOLS: Dict[Phase, List[str]] = SKILL_GROUPS

class CapabilityGate:
    """
    🛡️ Nexus 動態能力閘門
    治理 Agent 的工具權限，實現物理隔離。
    """
    def __init__(self):
        # 兜底：所有內建工具列表 (用於隱藏/黑名單對比)
        self.ALL_TOOLS = [
            "read_file", "replace_file_content", "multi_replace_file_content",
            "write_to_file", "run_command", "search_web", "grep_search",
            "view_file", "list_dir", "git_status", "git_diff", "command_status",
            "write_memory", "read_memory"
        ]

    def _normalize_phase(self, phase_str: Optional[str]) -> Optional[str]:
        """Normalize nullable phase input into a non-empty token."""
        if not isinstance(phase_str, str):
            return None
        normalized = phase_str.strip()
        return normalized or None

    def get_tools(self, phase_str: Optional[str]) -> List[str]:
        """獲取特定階段的合法工具清單"""
        normalized = self._normalize_phase(phase_str)
        if normalized is None:
            return PHASE_TOOLS[Phase.P]
        try:
            # 優先轉換為 Phase 枚舉 (名稱匹配)
            phase_upper = normalized.upper()
            if phase_upper in Phase.__members__:
                return PHASE_TOOLS[Phase[phase_upper]]
            
            # 其次透過值匹配，取代原本的 O(N) 迴圈
            return PHASE_TOOLS[Phase(normalized.lower())]
        except (KeyError, ValueError):
            return PHASE_TOOLS[Phase.P]

    def build_tools_json(self, phase_str: Optional[str]) -> Dict[str, Any]:
        """建立符合 PromptBuilder 格式的工具定義"""
        tools = self.get_tools(phase_str)
        tools_set = set(tools)
        return {
            "available_tools": tools,
            "hidden_tools": [t for t in self.ALL_TOOLS if t not in tools_set],
            "phase": self._normalize_phase(phase_str) or Phase.P.value
        }

    def managed_toolsets(self, phase_str: Optional[str]) -> List[str]:
        """🎯 Composio P0: 獲取 JIT 精簡工具集"""
        return self.get_tools(phase_str)
