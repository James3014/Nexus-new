#!/usr/bin/env python3
import os
import uuid
import fcntl
import shutil
import subprocess
import typing
from pathlib import Path

# 🔗 核心技能路徑 (Phase 3 & 6)
KB_DIR = os.getenv("NEXUS_KB_DIR", "/Users/jameschen/Downloads/obsidian/知識庫")
CONTEXT_INJECTOR_BIN = os.getenv("MUSE_CORE_CONTEXT_INJECTOR", "")
FLASH_INGEST_BIN = os.getenv("MUSE_CORE_FLASH_INGEST", "")
UV_BIN = shutil.which("uv") or "uv"



class WorkspacePermissionError(Exception):
    """當無法訪問專案根目錄或沙盒路徑時拋出。"""
    pass


class WorkspaceManager:
    """
    🧬 Lvl 17 Workspace Isolation Protocol (Commander Mode)
    Ensures zero Git Index contention by using dynamic, UUID-based worktrees.
    """

    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        
        # 🛡️ Preflight: 檢查基礎權限 (Fail-Closed)
        if not os.access(self.project_root, os.R_OK | os.W_OK):
             raise WorkspacePermissionError(f"Sandbox projection requires RW access to {self.project_root}")
             
        self.workspace_base = Path(os.getenv("NEXUS_WORKSPACE_BASE", "/tmp/codex-workspaces"))
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        self.lock_file = Path(os.getenv("NEXUS_WORKSPACE_LOCK", "/tmp/codex-loop-merge.lock"))
        self.lock_file.touch(exist_ok=True)

    def prepare_physical_sandbox(self, run_dir: Path) -> Path:
        """
        🏗️ 物理沙盒投影 (Phase 0 Refactor)
        負責任務專屬目錄建立、Symbolic Links 與配置檔案投影。
        """
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 配置投影 (Copy)
        for config_name in ['pytest.ini', 'pyproject.toml', '.env']:
            src = self.project_root / config_name
            if src.exists():
                shutil.copy2(src, run_dir / config_name)
        
        # 2. 核心目錄 Symlink (Zero-copy link)
        for dir_name in ['tests', '.venv']:
            src = self.project_root / dir_name
            tgt = run_dir / dir_name
            if src.exists() and not tgt.exists():
                tgt.symlink_to(src)
        
        return run_dir

    def lease(self, task_id: typing.Optional[str] = None,
            branch_name: typing.Optional[str] = None):
        """租借一個全新、隔離的 Git 工作位面。"""
        task_id = (task_id or str(uuid.uuid4()))[:8]
        branch_name = branch_name or f"isolated/task-{task_id}"
        work_path = self.workspace_base / task_id

        print(f"🏗️ [Provisioning] Leasing workspace: {task_id} at {work_path}")

        # 建立隔離分支與 Worktree
        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(work_path), "HEAD"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
            )

            injector_bin = CONTEXT_INJECTOR_BIN or (
                Path(KB_DIR) / "01_Persona/scripts/inject_context.py"
            )
            if injector_bin and os.path.exists(injector_bin):
                print("🧠 [Injection] Syncing brain context to sandbox...")
                res = subprocess.run(
                    ["python3", injector_bin], capture_output=True, text=True
                )
                if res.returncode == 0:
                    (work_path / "CONTEXT_SYNC.md").write_text(
                        res.stdout, encoding="utf-8"
                    )
                    print("✅ [Injection] CONTEXT_SYNC.md generated in sandbox.")
            else:
                print(
                    f"⚠️ [Injection Warning] Context injector not found at {injector_bin}. Skipping brain sync."
                )

            return task_id, branch_name, work_path
        except subprocess.CalledProcessError as e:
            print(f"❌ [FAILED] Lease failed: {e.stderr.decode()}")
            return None, None, None

    def sync_staged_to_sandbox(self, sandbox_path):
        """將主工作區的 Staged 內容同步至沙盒。"""
        patch_file = Path(os.getenv("NEXUS_SYNC_PATCH", "/tmp/codex_sync.patch"))
        try:
            # 1. 在主工作區產出 Patch
            with open(patch_file, "w") as f:
                subprocess.run(
                    ["git", "diff", "--staged"],
                    cwd=self.project_root,
                    stdout=f,
                    check=True,
                )

            # 2. 在沙盒套用 Patch
            if patch_file.stat().st_size > 0:
                subprocess.run(
                    ["git", "apply", str(patch_file)], cwd=sandbox_path, check=True
                )
                subprocess.run(["git", "add", "."], cwd=sandbox_path, check=True)
                print("🔄 [Sync] Staged changes migrated to sandbox.")
            return True
        except Exception as e:
            print(f"⚠️ [Sync Error] {e}")
            return False

    def harvest(self, branch_name, sandbox_path):
        """原子化收割：排隊合併回主幹。"""
        print(f"🚜 [Harvesting] Attempting to merge {branch_name}...")

        # 使用 fcntl 進行實體鎖定
        lock_f = open(self.lock_file, "w")
        try:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            print("🔒 [Lock] Acquired Merge Lock. Procedding with Atomic Harvest.")

            # 1. 確保隔離區已 Commit (R8-3 Step 1)
            self._ensure_sandbox_committed(sandbox_path)

            # 2. 🛡️ 生產準備：獲取主分支最新狀態 (R8-3 Step 2)
            self._prepare_main_for_merge()

            # 3. 執行原子化合併 (R8-3 Step 3)
            merge_success = self._execute_merge(branch_name)

            if merge_success:
                # 🛡️ Lvl 18 Phase 6: 結晶任務委派 (R8-3 Step 4)
                self._trigger_flash_crystallization()
                return True
            return False
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)
            lock_f.close()

    def _ensure_sandbox_committed(self, sandbox_path: Path):
        """確保隔離工作區的所有變更都已提交。"""
        subprocess.run(
            ["git", "commit", "-m", "fix(isolation): automated audit pass"],
            cwd=sandbox_path, capture_output=True,
        )

    def _prepare_main_for_merge(self):
        """獲取主分支最新狀態並 Rebase，確保原子化對齊。"""
        print("🔄 [Harvest] Reversing parity check (Fetching latest main)...")
        subprocess.run(["git", "checkout", "main"], cwd=self.project_root, capture_output=True)
        subprocess.run(["git", "fetch", "origin", "main"], cwd=self.project_root, capture_output=True)
        subprocess.run(["git", "rebase", "origin/main"], cwd=self.project_root, capture_output=True)

    def _execute_merge(self, branch_name: str) -> bool:
        """執行正式合併。"""
        res = subprocess.run(
            ["git", "merge", branch_name, "--no-ff", "-m", f"Merge isolated task: {branch_name}"],
            cwd=self.project_root, capture_output=True, text=True,
        )
        if res.returncode == 0:
            print(f"✅ [SUCCESS] Task {branch_name} harvested and merged.")
            return True
        else:
            print(f"❌ [CONFLICT] Merge failed: {res.stderr}")
            subprocess.run(["git", "merge", "--abort"], cwd=self.project_root)
            return False

    def _trigger_flash_crystallization(self):
        """觸發非同步經驗結晶。"""
        flash_bin = FLASH_INGEST_BIN or (Path(KB_DIR) / "01_Operations/scripts/flash_ingest_v2.py")
        if flash_bin and os.path.exists(flash_bin):
            print("💎 [Flash] Triggering asynchronous brain crystallization...")
            cmd = ["nohup", UV_BIN, "run", "--with", "lancedb", "--with", "pandas", "--with", "requests", flash_bin]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)

    def cleanup(self, task_id, branch_name):
        """銷毀位面，回歸平靜。"""
        work_path = self.workspace_base / task_id
        if work_path.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(work_path), "--force"],
                cwd=self.project_root,
            )
            subprocess.run(["git", "branch", "-D", branch_name], cwd=self.project_root)
            print(f"🧹 [Cleanup] Workspace {task_id} destroyed.")
