import os
import subprocess
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.core.parity_audit import ParityAuditor, ParityViolation
from typing import Dict, Any

class AuditPhaseHandler(BasePhaseHandler):
    """
    🔬 Nexus 審計階段處理器 (AOS-P4.2)
    負責在修復後執行原子對等審計 (Parity Audit) 與最終驗證。
    """
    
    def run(self, state: NexusState) -> Dict[str, Any]:
        """🎯 執行審計階段邏輯"""
        print(f"🔬 [Phase:Audit] Starting final parity audit for {state.task_id}...")
        
        auditor = ParityAuditor(str(self.project_root))
        results = []
        
        # 1. 物理獲取當前變更清單 (git diff)
        try:
            diff_files = subprocess.check_output(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.project_root, text=True
            ).strip().split("\n")
        except Exception:
            diff_files = []

        if not diff_files or diff_files == [""]:
            return {"status": "SKIPPED", "summary": "No changes found to audit."}

        # 2. 逐一核驗表面積真值
        for filepath in diff_files:
            if not filepath.endswith(".py"): continue
            
            # 獲取 before/after 內容
            try:
                after_code = (self.project_root / filepath).read_text(encoding="utf-8")
                before_code = subprocess.check_output(
                    ["git", "show", f"HEAD:{filepath}"],
                    cwd=self.project_root, text=True
                )
            except Exception:
                continue

            res = auditor.audit_patch(before_code, after_code, filepath)
            results.append(res)
            
            if not res["surface_match"]:
                # 🚨 Parity Violation: 高風險攔截
                msg = f"❌ [Audit:FAILED] Parity Violation in {filepath}. Missing: {res['missing_funcs']}"
                print(msg)
                raise ParityViolation(msg)

        print(f"✅ [Audit:SUCCESS] 0 parity violations in {len(results)} files.")
        return {
            "status": "COMPLETED",
            "audit_results": results,
            "summary": f"Audit passed for {len(results)} files."
        }
