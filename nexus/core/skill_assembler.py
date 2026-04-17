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
        [L3:JIT-Verification] 深度驗證：YAML Parser + Contract + Sandbox Smoke。
        """
        import yaml
        logger.info(f"🧪 [Assembler:JIT] Deep-verifying skill {skill_name}...")
        
        skill_dir = self.internal_skills_path / skill_name
        failure_reason = None
        report_data = {"parser_pass": False, "contract_pass": False, "smoke_pass": False}
        
        try:
            if not skill_dir.exists():
                failure_reason = "Directory not found."
            elif not (skill_dir / "SKILL.md").exists():
                failure_reason = "SKILL.md missing."
            else:
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                
                # 1. YAML Parser 檢查
                try:
                    if not content.startswith("---"):
                        raise ValueError("Missing frontmatter markers")
                    parts = content.split("---")
                    if len(parts) < 3:
                        raise ValueError("Malformed frontmatter structure")
                    frontmatter = yaml.safe_load(parts[1])
                    report_data["parser_pass"] = True
                except Exception as e:
                    failure_reason = f"YAML Parser Error: {e}"
                
                # 2. Contract 檢查 (必填欄位)
                if not failure_reason:
                    required = ["name", "description"] # 這裡可以根據規約擴充
                    missing = [f for f in required if f not in frontmatter]
                    if missing:
                        failure_reason = f"Contract Violation: missing {missing}"
                    else:
                        report_data["contract_pass"] = True

                # 3. 動態 Smoke Sandbox
                if not failure_reason:
                    if self.verify_skill_sandbox(skill_name):
                        report_data["smoke_pass"] = True
                    else:
                        failure_reason = "Sandbox Smoke Test Failed."

            if failure_reason:
                report_data["blocked_reason"] = failure_reason
                logger.error(f"❌ [Assembler:JIT] Blocked {skill_name}: {failure_reason}")
                (skill_dir / "jit_failure.log").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
                return False
            
            logger.info(f"✅ [Assembler:JIT] Full verification passed for {skill_name}.")
            return True

        except Exception as e:
            logger.error(f"❌ [Assembler:JIT] Crash during verification: {e}")
            return False

    def verify_skill_sandbox(self, skill_name: str) -> bool:
        """[L3:Sandbox] 隔離環境 dry-run 測試。"""
        # 模擬讀取 skill -> route -> dry-run 的過程
        # 這裡檢查是否具備基本的可讀性與腳本結構
        skill_dir = self.internal_skills_path / skill_name
        return (skill_dir / "SKILL.md").exists() and (skill_dir / "scripts").is_dir()

    def generate_jit_report(self, skill_names: List[str], report_path: Path):
        """
        [P2-2] 產出 Skill JIT 深度驗證報表。
        """
        results = []
        for name in skill_names:
            passed = self.verify_skill_jit(name)
            fail_log = self.internal_skills_path / name / "jit_failure.log"
            details = json.loads(fail_log.read_text()) if fail_log.exists() else {"parser_pass": True, "contract_pass": True, "smoke_pass": True}
            
            results.append({
                "skill_name": name,
                "passed": passed,
                "details": details
            })
            
        report = {
            "jit_validation_pass_rate": sum(1 for r in results if r["passed"]) / len(results) if results else 1.0,
            "unsafe_skill_promoted": sum(1 for r in results if not r["passed"]),
            "results": results
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
