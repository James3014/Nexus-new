from typing import Any, Dict, List, Optional, Tuple
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class CommandLockedError(Exception):
    """當指令在當前階段被禁止時拋出"""
    pass

class CommandState(str, Enum):
    """指令集狀態真值 (對位 PXDRAC)"""
    BOOTSTRAP    = "P"  # 電路啟動 / 計畫
    PLANNING     = "X"  # 研究 / 分析
    DIAGNOSING   = "D"  # 診斷
    REPAIRING    = "R"  # 修復 / 寫入
    AUDITING     = "A"  # 審計 / 核驗
    CRYSTALLIZING = "C" # 結晶化 / 提交

# 🚀 物理 DAG 指令矩陣 (Claw-30P1 規約)
DAG_EDGES = {
    CommandState.BOOTSTRAP:    ["read_file", "git_status", "nexus:status", "nexus:upgrade"],
    CommandState.PLANNING:     ["read_file", "git_status", "list_dir", "grep", "rg_search"],
    CommandState.DIAGNOSING:   ["list_dir", "read_file", "run_test", "linter"],
    CommandState.REPAIRING:    ["edit_file", "safe_patch", "nexus:runner"],
    CommandState.AUDITING:     ["git_diff", "pytest", "nexus:parity"],
    CommandState.CRYSTALLIZING: ["git_commit", "nexus:status"]
}

class CommandDAG:
    """
    🕹️ Nexus 指令圖 (AOS-P5.8)
    負責維護指令的物理狀態鎖定，防止 Agent 亂扣板機。
    """
    
    def __init__(self, current_phase: str):
        # 兼容簡寫
        self.state = self._norm_phase(current_phase)

    def validate(self, cmd_name: str) -> bool:
        """🎯 核驗指令執行權限"""
        allowed = DAG_EDGES.get(self.state, [])
        
        # 模糊匹配 (針對 nexus: 前綴)
        base_cmd = cmd_name.split(" ")[0].lower()
        
        if base_cmd in allowed or any(base_cmd in a for a in allowed):
            return True
            
        msg = f"❌ [DAG:LOCKED] 指令 '{cmd_name}' 在 {self.state} 階段被鎖定。請對齊 PXDRAC 流程。"
        logger.error(msg)
        raise CommandLockedError(msg)

    def _norm_phase(self, phase: str) -> CommandState:
        """物理對位"""
        for s in CommandState:
            if s.value == phase:
                return s
        return CommandState.BOOTSTRAP
