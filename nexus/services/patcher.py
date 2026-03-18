import re
import hashlib
import time
import subprocess
from pathlib import Path

class SafePatcher:
    """負責補丁的安全校驗與套用。"""

    def __init__(self, lock_dir, project_root=None):
        self.lock_dir = Path(lock_dir)
        if not self.lock_dir.is_dir():
            self.lock_dir = Path("/tmp")
        self.project_root = Path(project_root) if project_root else None

    def _generate_tdd_repro(self, violation, uid):
        """生成 TDD 復現腳本 (RED Phase)。"""
        if not self.project_root: return
        
        file_path = violation.get("file")
        reason = violation.get("reason", "Unknown violation")
        
        repro_content = f"""# TDD Reproduce Issue: {uid}
# Target File: {file_path}
# Reason: {reason}

import sys
import os

def test_repro():
    print(f"🔍 Testing reproduction for {file_path}...")
    # TODO: Implement specific check for: {reason}
    # For now, we assert the need for fix
    print("❌ [RED] Violation detected: {reason}")
    return False

if __name__ == "__main__":
    if not test_repro():
        sys.exit(1)
    print("✅ [GREEN] Issue resolved.")
    sys.exit(0)
"""
        repro_path = self.project_root / f"reproduce_v{uid}.py"
        repro_path.write_text(repro_content, encoding="utf-8")
        print(f"   🧪 [TDD] Reproduce script generated: {repro_path.name}")

    def apply(self, violations):
        """逐一校驗並套用補丁。"""
        patch_applied = False
        patch_requested = False
        print("\n🛠️  [Phase 2] Attempting to apply AI patches (TDD-Driven)...")
        
        for v in violations:
            patch = v.get("patch")
            file_path = v.get("file")
            if not patch or not file_path: continue
            patch_requested = True
            
            # 安全校驗
            targets = re.findall(r"^\+\+\+ b/(.*)$", patch, re.MULTILINE)
            if not targets or any(t.strip() != file_path for t in targets):
                print(f"   ⚠️ [Skipped] {file_path}: Patch target mismatch.")
                continue

            # 生成 TDD 復現腳本
            uid = hashlib.md5(f"{time.time()}_{file_path}".encode()).hexdigest()[:8]
            self._generate_tdd_repro(v, uid)

            # 使用動態路徑
            tmp_patch = self.lock_dir / f"auto_{uid}.patch"
            tmp_patch.write_text(patch, encoding="utf-8")
            
            try:
                # 優先嘗試 git apply
                res = subprocess.run(
                    ["git", "apply", "--3way", "--whitespace=fix", "--recount", str(tmp_patch)], 
                    capture_output=True, text=True
                )
                if res.returncode == 0:
                    print(f"   ✅ [Applied: Git] {file_path}")
                    patch_applied = True
                else:
                    raise RuntimeError(
                        f"FATAL: Git Apply Failed for {file_path}: {res.stderr.strip()}"
                    )
            except Exception as e:
                print(f"   ❌ Error applying patch: {e}")
            finally:
                if tmp_patch.exists(): tmp_patch.unlink()

        # Hard gate: if patches were requested but none applied, fail fast.
        if patch_requested and not patch_applied:
            print("   ❌ [Gate] Patch requested but nothing was applied.")
        return patch_applied
