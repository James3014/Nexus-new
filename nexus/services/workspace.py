#!/usr/bin/env python3
import os
import uuid
import fcntl
import shutil
import subprocess
from pathlib import Path

# 🔗 核心技能路徑 (Phase 3 & 6)
KB_DIR = "/Users/jameschen/Downloads/obsidian/知識庫"
CONTEXT_INJECTOR_BIN = os.getenv("MUSE_CORE_CONTEXT_INJECTOR", "")
FLASH_INGEST_BIN = os.getenv("MUSE_CORE_FLASH_INGEST", "")
UV_BIN = shutil.which("uv") or "uv"


class WorkspaceManager:
    """
    🧬 Lvl 17 Workspace Isolation Protocol (Commander Mode)
    Ensures zero Git Index contention by using dynamic, UUID-based worktrees.
    """

    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        # 🛡️ v9 Hardening: Avoid /tmp due to macOS Seatbelt/Isolation
        self.workspace_base = self.project_root / ".nexus" / "workspaces"
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.project_root / ".nexus" / "workspace_merge.lock"
        self.lock_file.touch(exist_ok=True)

    def lease(self, task_id: str = None, branch_name: str = None):
        """租借一個全新、隔離的 Git 工作位面。"""
        task_id = task_id or str(uuid.uuid4())[:8]
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
        patch_file = Path("/tmp/codex_sync.patch")
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

        # 使用 fcntl 進行實體鎖定，防止並行 Merge 衝突
        lock_f = open(self.lock_file, "w")
        try:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            print("🔒 [Lock] Acquired Merge Lock. Procedding with Atomic Harvest.")

            # 1. 確保隔離區已 Commit (若有 Staged)
            subprocess.run(
                ["git", "commit", "-m", "fix(isolation): automated audit pass"],
                cwd=sandbox_path,
                capture_output=True,
            )

            # 2. 🛡️ 戰略準備：合併前先獲取主分支最新狀態並 Rebase (原子化對齊)
            print("🔄 [Harvest] Reversing parity check (Fetching latest main)...")
            # 強制切換回 main 並拉取最新，確保合併目標正確
            subprocess.run(
                ["git", "checkout", "main"], cwd=self.project_root, capture_output=True
            )
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=self.project_root,
                capture_output=True,
            )
            subprocess.run(
                ["git", "rebase", "origin/main"],
                cwd=self.project_root,
                capture_output=True,
            )

            # 3. 執行原子化合併
            res = subprocess.run(
                [
                    "git",
                    "merge",
                    branch_name,
                    "--no-ff",
                    "-m",
                    f"Merge isolated task: {branch_name}",
                ],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )

            if res.returncode == 0:
                print(f"✅ [SUCCESS] Task {branch_name} harvested and merged.")

                # 🛡️ Lvl 18 Phase 6: 閃電記憶對位 (Flash Crystallization)
                flash_bin = FLASH_INGEST_BIN or (
                    Path(KB_DIR) / "01_Operations/scripts/flash_ingest_v2.py"
                )
                if flash_bin and os.path.exists(flash_bin):
                    print("💎 [Flash] Triggering asynchronous brain crystallization...")
                    # 使用 nohup 背景執行，確保不阻塞主線
                    cmd = [
                        "nohup",
                        UV_BIN,
                        "run",
                        "--with",
                        "lancedb",
                        "--with",
                        "pandas",
                        "--with",
                        "requests",
                        flash_bin,
                    ]
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        preexec_fn=os.setpgrp,
                    )

                return True
            else:
                print(f"❌ [CONFLICT] Merge failed: {res.stderr}")
                subprocess.run(["git", "merge", "--abort"], cwd=self.project_root)
                return False
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)
            lock_f.close()

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
