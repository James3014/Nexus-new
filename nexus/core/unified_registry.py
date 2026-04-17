from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_store import SkillStore
from nexus.learning.external_skill_loader import ExternalSkillLoader
from nexus.learning.skill_schema import SkillFrontmatter

logger = logging.getLogger(__name__)

@dataclass
class AssetManifest:
    skills_count: int = 0
    models_configured: int = 0
    policies_count: int = 0
    last_refresh: str = ""
    health: Dict[str, str] = field(default_factory=dict)

class UnifiedRegistry:
    """🧬 Nexus v4.0: 統一資產註冊表 (Single Source of Truth)
    職責：整合 SkillRegistry, SkillStore 與靜態配置，提供統一查詢接口。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.registry_path = project_root / ".nexus" / "state" / "skills.db"
        self.registry = SkillRegistry(self.registry_path)
        self.store = SkillStore(project_root)
        self.war_armor_path = project_root / "nexus" / "skills" / "war-armor.json"
        
        # 初始化外部載入器
        self.external_loader = ExternalSkillLoader(
            self.registry, 
            [Path.home() / ".agents" / "skills"]
        )

    def get_status(self) -> AssetManifest:
        stats = self.registry.get_stats()
        
        # 讀取 war-armor
        models_count = 0
        if self.war_armor_path.exists():
            try:
                data = json.loads(self.war_armor_path.read_text())
                models_count = len(data)
            except: pass
            
        # 讀取策略數
        policy_path = self.project_root / ".nexus" / "knowledge" / "policy_memory.jsonl"
        policies_count = 0
        if policy_path.exists():
            policies_count = len(policy_path.read_text().splitlines())

        return AssetManifest(
            skills_count=stats["total_skills"],
            models_configured=models_count,
            policies_count=policies_count,
            last_refresh=datetime.now(timezone.utc).isoformat(),
            health={
                "registry": "OK" if self.registry_path.exists() else "MISSING",
                "store": "OK" if (self.project_root / "skills" / "learned").exists() else "MISSING",
                "war_armor": "OK" if self.war_armor_path.exists() else "MISSING"
            }
        )

    def find_best_skill(self, task_desc: str, task_type: str = "unknown") -> Optional[SkillFrontmatter]:
        """綜合查詢最佳技能"""
        tokens = set(task_desc.lower().split())
        results = self.registry.search(tokens, task_type=task_type, max_results=1)
        if results:
            # 這裡需要將 dict 轉回 SkillFrontmatter，但 registry 回傳的是 dict
            # 我們可以用 registry 的 get_by_task_id，它會回傳 dict，
            # 然後在 exchange 中有 _row_to_skill 邏輯。
            # 直接從 registry 獲取 row
            return self.registry.get_by_task_id(results[0]["task_id"])
        return None

    def refresh(self):
        """執行全量同步"""
        logger.info("🛠️ [UnifiedRegistry] Starting full asset refresh...")
        # 1. 同步外部技能
        self.external_loader.scan_and_register()
        # 2. 目前 SkillStore 與 Registry 的同步由 SkillExchange 負責，
        # 在此可擴展自定義邏輯。
        logger.info("✅ [UnifiedRegistry] Refresh complete.")
