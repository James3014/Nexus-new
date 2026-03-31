from enum import Enum
from typing import List, Dict, Any

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

    def get_tools(self, phase_str: str) -> List[str]:
        """獲取特定階段的合法工具清單"""
        try:
            # 轉換為 Phase 枚舉 (支援簡稱與全稱)
            if phase_str.upper() in Phase.__members__:
                phase = Phase[phase_str.upper()]
            else:
                # 模糊匹配
                found = [p for p in Phase if p.value == phase_str.lower()]
                phase = found[0] if found else Phase.P
                
            return PHASE_TOOLS.get(phase, PHASE_TOOLS[Phase.P])
        except Exception:
            return PHASE_TOOLS[Phase.P]

    def build_tools_json(self, phase_str: str) -> Dict[str, Any]:
        """建立符合 PromptBuilder 格式的工具定義"""
        tools = self.get_tools(phase_str)
        return {
            "available_tools": tools,
            "hidden_tools": [t for t in self.ALL_TOOLS if t not in tools],
            "phase": phase_str
        }
    def managed_toolsets(self, phase_str: str) -> List[str]:
        """🎯 Composio P0: 獲取 JIT 精簡工具集"""
        return self.get_tools(phase_str)
