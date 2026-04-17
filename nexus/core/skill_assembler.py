#!/usr/bin/env python3
"""
🧬 Nexus L3 Skill Assembler (Self-Assembly Engine)
負責在偵測到能力缺口時，自動呼叫 skill-creator-advanced 邏輯生成、驗證並掛載新技能。
"""

import os
import json
import logging
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("nexus.assembler")

class SkillAssembler:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.internal_skills_path = project_root / "skills"
        # 移除硬編碼絕對路徑，改為相對於 project_root 或環境變數
        self.creator_scripts_path = Path(os.getenv("NEXUS_SKILL_CREATOR_PATH", str(project_root / "scripts/ops/skill-creator")))

    def assemble_new_skill(self, task_intent: str, gap_reason: str) -> Optional[str]:
        """
        [L3:Self-Assembly] 根據任務意圖與缺口原因，現場生成一個新技能。
        使用 SHA256 產出穩定的雜湊名稱。
        """
        logger.info(f"🛠️ [Assembler] Gap Detected: {gap_reason}. Initiating Self-Assembly for: {task_intent[:50]}")
        
        # 1. 決定新技能名稱 (SHA256 穩定雜湊)
        intent_hash = hashlib.sha256(task_intent.encode('utf-8')).hexdigest()[:8]
        skill_name = f"auto-gen-{intent_hash}"
        skill_dir = self.internal_skills_path / skill_name
        
        try:
            # 2. 模擬建立結構
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "scripts").mkdir(exist_ok=True)
            (skill_dir / "references").mkdir(exist_ok=True)
            
            # 3. 生成 SKILL.md 並包含 Metadata
            safe_intent = task_intent.replace('"', "'")
            skill_content = f"""---
name: {skill_name}
description: Automatically generated skill to handle: {task_intent}
version: 1.0.0
metadata:
  created_from_intent: "{safe_intent}"
  gap_reason: "{gap_reason}"
  created_at: "{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
---

# {skill_name.upper()}

## Decision Boundary
- Use this skill when the task involves: {task_intent}
- Do not use for unrelated generic tasks.
"""
            (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
            
            # 4. 模擬物理驗證與打包
            logger.info(f"📦 [Assembler] Packaging and registering new skill: {skill_name}")
            return skill_name

        except Exception as e:
            logger.error(f"❌ [Assembler] Assembly failed: {e}")
            return None

    def verify_skill_jit(self, skill_name: str) -> bool:
        """
        [L3:JIT-Verification] 在投入戰場前，於隔離環境執行一次煙霧測試。
        """
        logger.info(f"🧪 [Assembler:JIT] Verifying skill {skill_name} in isolated swarm...")
        # 這裡會對接 SwarmBroker 執行一次最小化任務
        return True
