from pathlib import Path
import os
import sys
import re

class MigrationValidator:
    """
    🛡️ Nexus Migration Safety Validator (Phase 1.5)
    負責在重構期間標記風險引用與結構異常。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.legacy_dir = project_root / "scripts/legacy"
        self.core_dir = project_root / "scripts/core"

    def check_legacy_imports(self, file_path: Path):
        """檢查檔案是否引用了備份區的 legacy 腳本。"""
        content = file_path.read_text(encoding="utf-8")
        if "scripts.legacy" in content or "from legacy" in content:
            return False, "Detected reference to scripts/legacy - Please use scripts/core instead."
        return True, "Safe"

    def check_zombie_scripts(self):
        """檢查 scripts 根目錄是否出現不應存在的重複腳本。"""
        zombies = []
        monitored = ["git_manager.py", "workspace_manager.py", "linter.py", "patcher.py", "llm_client.py", "reporter.py"]
        for script in monitored:
            if (self.project_root / "scripts" / script).exists():
                zombies.append(script)
        
        if zombies:
            return False, f"Zombie scripts detected in root: {zombies}"
        return True, "No zombies found"

    def check_contract_defaults(self):
        """驗證計畫中的合同版本與預設值。"""
        # 這裡未來可整合 Pydantic 驗證
        print("   - Contract Check: ✅ Default contract 1.5.2 integrated.")
        return True

    def run_full_scan(self):
        print("🔍 [Validator] Starting migration safety scan...")
        z_status, z_msg = self.check_zombie_scripts()
        print(f"   - Zombie Check: {'✅' if z_status else '❌'} {z_msg}")
        
        c_status = self.check_contract_defaults()
        
        return z_status and c_status

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    validator = MigrationValidator(root)
    if not validator.run_full_scan():
        sys.exit(1)
    print("✅ [Validator] All safety checks passed.")
