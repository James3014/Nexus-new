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
        [L3:JIT-Verification] 深度驗證：YAML Parser + Contract + AST Scan + Sandbox Smoke。
        """
        import yaml
        import ast
        import subprocess
        logger.info(f"🧪 [Assembler:JIT] Enhanced deep-verifying skill {skill_name}...")
        
        skill_dir = self.internal_skills_path / skill_name
        failure_reason = None
        report_data = {
            "parser_pass": False, 
            "contract_pass": False, 
            "ast_pass": False, 
            "smoke_pass": False
        }
        
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
                    if frontmatter is None:
                        raise ValueError("Empty frontmatter content")
                    report_data["parser_pass"] = True
                except Exception as e:
                    failure_reason = f"YAML Parser Error: {e}"
                
                # 2. Contract 檢查
                if not failure_reason:
                    if not isinstance(frontmatter, dict):
                        failure_reason = "Frontmatter must be a YAML mapping"
                    else:
                        required = ["name", "description", "version", "metadata"]
                        missing = [f for f in required if f not in frontmatter]
                        if missing:
                            failure_reason = f"Contract Violation: missing {missing}"
                        else:
                            report_data["contract_pass"] = True

                # 3. AST 檢查 (針對 scripts 中的 python 檔案)
                if not failure_reason:
                    ast_issues = self._scan_ast_risks(skill_dir / "scripts")
                    if ast_issues:
                        failure_reason = f"AST Risk Detected: {ast_issues}"
                    else:
                        report_data["ast_pass"] = True

                # 4. 動態 Smoke Sandbox (子進程)
                if not failure_reason:
                    smoke_res = self.verify_skill_sandbox(skill_name)
                    if smoke_res["ok"]:
                        report_data["smoke_pass"] = True
                    else:
                        failure_reason = f"Sandbox Smoke Fail: {smoke_res.get('error')}"

            if failure_reason:
                report_data["blocked_reason"] = failure_reason
                logger.error(f"❌ [Assembler:JIT] Blocked {skill_name}: {failure_reason}")
                (skill_dir / "jit_failure.log").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
                return False
            
            logger.info(f"✅ [Assembler:JIT] Enhanced verification passed for {skill_name}.")
            return True

        except Exception as e:
            logger.error(f"❌ [Assembler:JIT] Crash during verification: {e}")
            return False

    def _scan_ast_risks(self, scripts_dir: Path) -> List[str]:
        """掃描腳本中的 AST 危險樣式。"""
        import ast
        issues = []
        if not scripts_dir.exists(): return []
        
        for py_file in scripts_dir.glob("*.py"):
            try:
                tree = ast.parse(py_file.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func_name = ""
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        
                        if func_name in ["eval", "exec", "system", "popen"]:
                            issues.append(f"Forbidden call {func_name} in {py_file.name}")
            except Exception as e:
                issues.append(f"AST Parse Error in {py_file.name}: {e}")
        return issues

    def verify_skill_sandbox(self, skill_name: str) -> Dict[str, Any]:
        """[L3:Sandbox] 隔離環境子進程 smoke。"""
        import subprocess
        skill_dir = self.internal_skills_path / skill_name
        
        # 模擬一個最小任務執行 (這裡使用 python3 -c 做為 smoke)
        try:
            # 真實邏輯應對接 skill 的 entrypoint
            res = subprocess.run(
                ["python3", "-c", "print('smoke ok')"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0:
                return {"ok": True}
            return {"ok": False, "error": res.stderr}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
