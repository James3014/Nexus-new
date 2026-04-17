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
        [L3:JIT-Verification] 在投入戰場前，進行物理結構與格式驗證。
        """
        logger.info(f"🧪 [Assembler:JIT] Verifying skill {skill_name}...")
        
        skill_dir = self.internal_skills_path / skill_name
        failure_reason = None
        
        try:
            # 1. 檢查目錄
            if not skill_dir.exists():
                failure_reason = f"Skill directory {skill_name} not found."
            
            # 2. 檢查核心檔案
            elif not (skill_dir / "SKILL.md").exists():
                failure_reason = "SKILL.md is missing."
            
            # 3. 檢查 YAML 格式
            else:
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                if not content.startswith("---"):
                    failure_reason = "SKILL.md is missing YAML frontmatter."
                
                # 簡單驗證 YAML 是否包含必要欄位 (可擴充使用 PyYAML)
                if "name:" not in content or "description:" not in content:
                    failure_reason = "SKILL.md missing name or description in frontmatter."

            if failure_reason:
                logger.error(f"❌ [Assembler:JIT] Verification FAILED for {skill_name}: {failure_reason}")
                # 寫入失敗原因供回溯
                (skill_dir / "jit_failure.log").write_text(failure_reason, encoding="utf-8")
                return False
            
            logger.info(f"✅ [Assembler:JIT] Verification PASSED for {skill_name}.")
            return True

        except Exception as e:
            logger.error(f"❌ [Assembler:JIT] Crash during verification: {e}")
            return False

    def generate_jit_report(self, skill_names: List[str], report_path: Path):
        """
        [P2-2] 產出 Skill JIT 驗證報表。
        """
        results = []
        for name in skill_names:
            passed = self.verify_skill_jit(name)
            results.append({
                "skill_name": name,
                "passed": passed,
                "error": None if passed else (self.internal_skills_path / name / "jit_failure.log").read_text() if (self.internal_skills_path / name / "jit_failure.log").exists() else "Unknown"
            })
            
        report = {
            "jit_validation_pass_rate": sum(1 for r in results if r["passed"]) / len(results) if results else 1.0,
            "unsafe_skill_promoted": sum(1 for r in results if not r["passed"]),
            "results": results
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
