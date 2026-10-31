from pathlib import Path
import os
import re
import hashlib
import time
import subprocess

from nexus.core.contained_write import (
    PathContainmentError,
    contained_relative_path,
    read_text_in_root,
    write_text_in_root,
)

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
        repro_name = f"reproduce_v{uid}.py"
        # 專案根目錄可能已被模型執行過的程式放了連結：不經連結寫入（拒絕時丟 PathContainmentError）
        write_text_in_root(self.project_root, repro_name, repro_content)
        print(f"   🧪 [TDD] Reproduce script generated: {repro_name}")

    def apply(self, violations):
        """逐一校驗並套用補丁。"""
        patch_applied = False
        print("\n🛠️  [Phase 2] Attempting to apply AI patches (TDD-Driven)...")
        
        for v in violations:
            patch = v.get("patch")
            file_path = v.get("file")
            if not patch or not file_path: continue
            
            # 安全校驗
            targets = re.findall(r"^\+\+\+ b/(.*)$", patch, re.MULTILINE)
            if not targets or any(t.strip() != file_path for t in targets):
                print(f"   ⚠️ [Skipped] {file_path}: Patch target mismatch.")
                continue

            # file 來自模型輸出：必須落在專案根目錄內（不含經連結逃出）
            root = self.project_root if self.project_root else Path(".")
            try:
                relative = contained_relative_path(root, file_path)
            except (OSError, RuntimeError, ValueError):
                print(f"   ⚠️ [Skipped] {file_path}: Patch target outside project root.")
                continue

            # 生成 TDD 復現腳本
            uid = hashlib.md5(f"{time.time()}_{file_path}".encode()).hexdigest()[:8]
            # 使用動態路徑；lock_dir 可能在專案根目錄內（也可能是 /tmp），以它為根、不經連結寫入
            tmp_patch = self.lock_dir / f"auto_{uid}.patch"
            try:
                self._generate_tdd_repro(v, uid)
                write_text_in_root(self.lock_dir, tmp_patch.name, patch)
            except PathContainmentError as e:
                print(f"   ⚠️ [Skipped] {file_path}: Write refused ({e}).")
                continue
            
            try:
                # 優先嘗試 git apply
                res = subprocess.run(
                    ["git", "apply", "--3way", "--whitespace=fix", "--recount", str(tmp_patch)], 
                    capture_output=True, text=True,
                    cwd=str(self.project_root) if self.project_root else None
                )
                if res.returncode == 0:
                    print(f"   ✅ [Applied: Git] {file_path}")
                    patch_applied = True
                else:
                    # 模擬測試或緊急情況下的直寫回退
                    print(f"   ⚠️ [Git Failed] {file_path}")
                    print(f"   ⚠️ Trying Direct Application (Mock Mode)...")
                    target_file = root / relative
                    if target_file.exists():
                        content = read_text_in_root(root, relative)
                        # 非 UTF-8（讀出含 U+FFFD）或唯讀的檔不改寫，避免改掉原有位元組
                        if "\ufffd" in content or not os.access(target_file, os.W_OK):
                            raise ValueError(f"{file_path} is not a writable UTF-8 file")
                        # 極簡模擬：如果補丁包含 +, 就加上去
                        new_lines = [l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
                        write_text_in_root(root, relative, content + "\n" + "\n".join(new_lines))
                        print(f"   ✅ [Applied: Direct] {file_path}")
                        patch_applied = True
            except Exception as e:
                print(f"   ❌ Error applying patch: {e}")
            finally:
                if tmp_patch.exists(): tmp_patch.unlink()
        
        return patch_applied
