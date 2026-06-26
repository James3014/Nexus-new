from pathlib import Path
import os
import json
import logging
from nexus.governance.capability_gate import CapabilityGate
from nexus.core.engine.nexus_transaction import TransactionManager

logger = logging.getLogger(__name__)

class NakedRunError(Exception):
    """當分身未穿戴 Nexus 盔甲時拋出"""
    pass

class SubAgentArmor:
    """
    🛡️ Nexus 分身穿甲核心 (AOS-P5.3)
    負責在平行子代理啟動時強制執行治理協議與物理隔離。
    """
    REQUIRED_ENV = ["NEXUS_ENFORCED", "NEXUS_WORKTREE", "NEXUS_SCOPE"]

    def __init__(self):
        self.gate = None
        self.tx = None
        self.scope = []
        self.worktree = None

    def activate(self, state_root: str) -> 'SubAgentArmor':
        """🎯 啟動穿甲程序：核驗環境並掛載治理組件"""
        logger.info("🛡️ [Armor] Activating Nexus Governance for Sub-agent...")

        # 1. 環境核驗 (Environment Enforcement)
        for key in self.REQUIRED_ENV:
            if not os.getenv(key):
                raise NakedRunError(
                    f"❌ [Armor:REJECT] Sub-agent 裸跑被攔截！缺少核心環境變數: {key}。\n"
                    "請務必透過 SubAgentSpawner 進行物理注入。"
                )

        # 2. 物理隔離核驗 (Worktree Isolation)
        worktree_str = os.getenv("NEXUS_WORKTREE")
        if not worktree_str:
            raise ValueError("NEXUS_WORKTREE environment variable not set")
        self.worktree = Path(worktree_str)
        main_workspace = Path(state_root).resolve()
        
        if self.worktree.resolve() == main_workspace:
            raise PermissionError(
                "❌ [Armor:REJECT] 物理隔離失敗！分身禁止在主工作空間 (Main Workspace) 執行。\n"
                f"Worktree: {self.worktree}"
            )

        # 3. 掛載治理組件 (Governance Mounting)
        self.gate = CapabilityGate()
        self.tx = TransactionManager(str(self.worktree))
        try:
            self.scope = json.loads(os.getenv("NEXUS_SCOPE", "[]"))
        except json.JSONDecodeError:
            self.scope = []

        logger.info(f"✅ [Armor:READY] Sub-agent Armored. Scope: {len(self.scope)} files.")
        return self

    def can_write(self, filepath: str) -> bool:
        """核驗修改目標是否在 Handoff 規定的 Scope 內"""
        if not self.worktree:
            return False
        rel_path = str(Path(filepath).relative_to(self.worktree)) if Path(filepath).is_absolute() else filepath
        return rel_path in self.scope

    def commit_blocked(self):
        """禁止分身直接連動 Git 提交"""
        raise PermissionError(
            "❌ [Armor:BLOCK] 公序良俗攔截：分身禁止直接 Commit！\n"
            "所有變更必須封裝為 OutcomePayload JSON 回傳主代理審計。"
        )

    @property
    def is_enforced(self) -> bool:
        return os.getenv("NEXUS_ENFORCED") == "true"
