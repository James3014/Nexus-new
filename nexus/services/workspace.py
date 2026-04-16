from pathlib import Path
#!/usr/bin/env python3
import os
import logging
import uuid
import fcntl
import shutil
import subprocess
import typing

# 🔗 核心技能路徑 (Phase 3 & 6)
KB_DIR = os.getenv("NEXUS_KB_DIR", "/Users/jameschen/Downloads/obsidian/知識庫")
CONTEXT_INJECTOR_BIN = os.getenv("MUSE_CORE_CONTEXT_INJECTOR", "")
FLASH_INGEST_BIN = os.getenv("MUSE_CORE_FLASH_INGEST", "")
UV_BIN = shutil.which("uv") or "uv"
logger = logging.getLogger(__name__)



class WorkspacePermissionError(Exception):
    """當無法訪問專案根目錄或沙盒路徑時拋出。"""
    pass


class WorkspaceManager:
    def _acquire_workspace_lock(self, workspace_path: Path, timeout_sec: int = 10) -> bool:
        lock_file = workspace_path / ".lock"
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                # Atomic creation of lock file
                lock_file.touch(exist_ok=False)
                return True
            except FileExistsError:
                time.sleep(0.5)
        return False

    def _release_workspace_lock(self, workspace_path: Path):
        lock_file = workspace_path / ".lock"
        if lock_file.exists():
            lock_file.unlink()

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
        """🛡️ Nexus Workspace Leasing (v24.0 Hardened)"""
        # 🧬 Ensure uniqueness by combining task_id with a shortened UUID
        explicit_task = bool(task_id)
        task_id = (task_id or "nexus-task")
        unique_id = task_id if explicit_task else f"{task_id[:16]}-{str(uuid.uuid4())[:4]}"
        branch_name = branch_name or f"isolated/task-{unique_id}"
        
        # 🐝 [P1 Optimization] Swarm Reuse strategy
        # 優先尋找並租用 .nexus-swarm-* 目錄，避免 git worktree add 的開銷
        swarm_dirs = sorted([d for d in self.project_root.glob(".nexus-swarm-*") if d.is_dir()])
        if swarm_dirs:
            try:
                from nexus.research.swarm_broker import SwarmBroker
                broker = SwarmBroker(self.project_root)
                swarm_path = broker.acquire(timeout_sec=5.0)
                if swarm_path:
                    print(f"🐝 [Swarm-Reuse] Leasing existing sandbox: {swarm_path.name}")
                    # 切換到目標分支
                    subprocess.run(["git", "checkout", "main"], cwd=swarm_path, capture_output=True)
                    subprocess.run(["git", "checkout", "-b", branch_name], cwd=swarm_path, check=True, capture_output=True)
                    
                    # 標記此 workspace 為 swarm 類型以便 cleanup 處理
                    (swarm_path / ".swarm_lease").write_text(branch_name, encoding="utf-8")
                    
                    self._sync_brain_to_path(swarm_path)
                    return task_id, branch_name, swarm_path
            except Exception as e:
                logger.warning(f"⚠️ [Swarm-Reuse] Failed to acquire swarm, falling back: {e}")

        work_path = self.workspace_base / unique_id
        print(f"🏗️ [Provisioning] Leasing workspace: {task_id} at {work_path}")

        # 建立隔離分支與 Worktree (Optimized Index Handling)
        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(work_path), "HEAD"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
                timeout=45
            )

            self._sync_brain_to_path(work_path)

            # Auto-GC after successful lease to avoid interfering with call order expectations.
            self._auto_gc()
            
            return task_id, branch_name, work_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"❌ [FAILED] Lease failed or timed out: {e}")
            return None, None, None

    def _sync_brain_to_path(self, work_path: Path):
        """同步大腦上下文到指定路徑。"""
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

    def _auto_gc(self):
        """🧹 Automatic Garbage Collection for stale sandboxes (>24h)."""
        import time
        now = time.time()
        for folder in self.workspace_base.glob("*"):
            if folder.is_dir():
                if now - folder.stat().st_mtime > 86400:
                    try:
                        logger.info(f"🧹 [Auto-GC] Pruning stale workspace: {folder.name}")
                        subprocess.run(["git", "worktree", "remove", "--force", str(folder)], cwd=self.project_root, capture_output=True)
                    except Exception:
                        pass

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
        # 1. 檢查是否為 Swarm 租約
        for swarm_dir in self.project_root.glob(".nexus-swarm-*"):
            lease_file = swarm_dir / ".swarm_lease"
            if lease_file.exists():
                if lease_file.read_text(encoding="utf-8").strip() == branch_name:
                    from nexus.research.swarm_broker import SwarmBroker
                    broker = SwarmBroker(self.project_root)
                    lease_file.unlink()
                    broker.release(swarm_dir)
                    print(f"🧹 [Cleanup] Swarm sandbox {swarm_dir.name} released.")
                    return

        # 2. 原有的 Worktree 清理邏輯
        work_path = self.workspace_base / task_id
        if work_path.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(work_path), "--force"],
                cwd=self.project_root,
            )
            subprocess.run(["git", "branch", "-D", branch_name], cwd=self.project_root, capture_output=True)
            print(f"🧹 [Cleanup] Workspace {task_id} destroyed.")
