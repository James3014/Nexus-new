import os
import logging
import subprocess
from pathlib import Path

from nexus.core.hardened_git import (
    repository_config_can_start_a_program,
    repository_is_rooted_at,
    run_hardened_git,
)

logger = logging.getLogger(__name__)

class TransactionManager:
    """
    🧬 Nexus 交易式執行中樞 (v22 Eternal)
    負責 Phase R 的物理隔離與 Phase A 的原子提交。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.staging_dir = self.project_root / ".nexus" / "staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.staging_dir / "transaction_history.json"

    def stage_patch(self, task_id: str, diff: str):
        """將變更暫存到 staging 區"""
        logger.info("📦 [Transaction] Staging patch for task: %s", task_id)
        patch_path = self.staging_dir / f"{task_id}.patch"
        patch_path.write_text(diff)
        return patch_path

    def audit_rollback(self, task_id: str):
        """物理回滾：Audit 失敗時強制回溯至任務起點"""
        logger.warning("🚨 [Transaction] Audit FAILED for %s. Triggering PHYSICAL ROLLBACK!", task_id)
        # The workspace holds the audited agent's edits, so git runs hardened and only in a
        # repository rooted at project_root.
        root = self.project_root.resolve()
        if not repository_is_rooted_at(root) or repository_config_can_start_a_program(root):
            logger.error("❌ [Transaction] Rollback FAILED: unsafe git repository: %r", str(root))
            return False
        try:
            # 物理回滾到 HEAD
            run_hardened_git(root, "reset", "--hard", "HEAD").check_returncode()
            # 清理未追蹤檔案
            run_hardened_git(root, "clean", "-fd").check_returncode()
            logger.info("✅ [Transaction] Rollback SUCCESS. Workspace cleared.")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("❌ [Transaction] Rollback FAILED: %s", e)
            return False

    def commit_if_passed(self, task_id: str, message: str = ""):
        """原子提交：Audit 通過後物理鎖定變更"""
        logger.info("💎 [Transaction] Audit PASSED for %s. Committing changes...", task_id)
        commit_msg = message or f"fix({task_id}): automated nexus repair (AOS-P0-P1)"
        try:
            subprocess.run(["git", "-C", str(self.project_root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(self.project_root), "commit", "-m", commit_msg], check=True)
            logger.info("✅ [Transaction] Commit SUCCESS. SHA-1 locked.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error("❌ [Transaction] Commit FAILED: %s", e)
            return False

    def get_status(self) -> dict:
        """獲取交易系統狀態"""
        return {
            "status": "ACTIVE",
            "staging_path": str(self.staging_dir),
            "governance": "L5.7_ETERNAL"
        }
