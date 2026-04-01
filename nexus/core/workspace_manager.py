import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class WorkspaceManager:
    """🧬 Nexus v26.0 空間分片 (Composio AO Dimension 1)
    
    具現化 git_worktree_sharding。支援 10 個並行 Agent 隔離。
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.worktree_base = self.project_root.parent / "nexus_shards"
        self.worktree_base.mkdir(parents=True, exist_ok=True)

    def create_worktree_shard(self, shard_id: str, branch_name: str = "main"):
        """為單一子任務分片具現化隔離的 Git Worktree"""
        shard_path = self.worktree_base / f"{shard_id}"
        
        logger.info(f"🌿 [Workspace] Creating Git Worktree: {shard_path}")
        
        if shard_path.exists():
            logger.warning(f"⚠️ [Workspace] Shard path {shard_path} already exists. Removing...")
            subprocess.run(["git", "worktree", "remove", "--force", str(shard_path)], cwd=str(self.project_root))
            
        try:
            # 建立物理隔離的 Worktree (Dimension 1)
            subprocess.run([
                "git", "worktree", "add", "-b", f"feature/shard-{shard_id}", 
                str(shard_path), branch_name
            ], cwd=str(self.project_root), check=True)
            
            logger.info(f"✅ [Workspace] Shard {shard_id} isolated at {shard_path}")
            return str(shard_path)
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ [Workspace] Failed to create worktree: {e}")
            return None

    def cleanup_shard(self, shard_id: str):
        """資源回收：物理刪除 Worktree"""
        shard_path = self.worktree_base / f"{shard_id}"
        logger.info(f"🧹 [Workspace] Cleaning up Shard: {shard_id}")
        
        if shard_path.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(shard_path)], cwd=str(self.project_root))
            return True
        return False
