import shutil
import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

class SelectorRollback:
    """
    🧬 AutoResearch 安全選優與回滾器 (v1.3 Semantic Hardened)
    職責：物理執行候選變更套用與非破壞性回滾，實施語義路徑隔離。
    """
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.backup_root = (self.workspace / ".nexus" / "backups").resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def _safe_resolve(self, sub_path: str) -> Optional[Path]:
        """語義路徑核驗：使用 is_relative_to 封殺前綴繞過風險"""
        try:
            target = (self.workspace / sub_path).resolve()
            if target.is_relative_to(self.workspace):
                return target
            logger.error("🚫 [Security] Path containment breach blocked: %s", sub_path)
            return None
        except Exception:
            return None

    def backup_scope(self, candidate_id: str, scope: List[str]):
        backup_dir = self.backup_root / candidate_id
        backup_dir.mkdir(exist_ok=True)
        for file_path in scope:
            target = self._safe_resolve(file_path)
            if target and target.exists():
                rel_path = target.relative_to(self.workspace)
                dst = backup_dir / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dst)
                logger.info("🛡️ [Rollback] Backed up: %s", rel_path)

    def restore_scope(self, candidate_id: str, scope: List[str]) -> bool:
        backup_dir = self.backup_root / candidate_id
        if not backup_dir.exists(): return False
        for file_path in scope:
            target = self._safe_resolve(file_path)
            if not target: continue
            rel_path = target.relative_to(self.workspace)
            src = backup_dir / rel_path
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            elif target.exists():
                target.unlink()
        return True

    def promote_candidate(self, candidate_id: str, candidate_src_root: Path, scope: List[str]) -> bool:
        logger.info("🚀 [Selector] Promoting candidate %s...", candidate_id)
        candidate_src_root = candidate_src_root.resolve()
        try:
            for file_path in scope:
                target_dst = self._safe_resolve(file_path)
                if not target_dst: return False
                src_file = (candidate_src_root / file_path).resolve()
                if not src_file.is_relative_to(candidate_src_root):
                    logger.error("🚫 [Security] Malicious candidate path blocked: %s", file_path)
                    return False
                if src_file.exists():
                    target_dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, target_dst)
            return True
        except Exception as e:
            logger.error("❌ [Selector] Promotion failed: %s", e)
            return False
