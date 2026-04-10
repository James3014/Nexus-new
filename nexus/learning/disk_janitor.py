from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
"""DiskJanitor unified cleanup service.

Addresses Black Zone #6: Disk Footprint Growth.
Provides systematic cleanup logic for:
- JSONL log rotation using gzip
- SQLite registry pruning and VACUUM
- Archived skills expiration
Note: Embedding cache LRU eviction is typically handled directly within the cache 
class on save(), but could be orchestrated here.
"""

import os
import gzip
import time
import shutil
import logging

from nexus.learning.disk_policy import DiskPolicy

logger = logging.getLogger(__name__)

class DiskJanitor:
    def __init__(self, workspace_root: Path, registry=None, config: Optional[DiskPolicy] = None):
        self.workspace_root = workspace_root
        self.registry = registry
        self.config = config or DiskPolicy.from_env()

    def run_all(self, skills_dir: Path) -> Dict[str, Any]:
        """Execute all cleanup strategies and return a summary report."""
        report = {}
        try:
            report["rotated_logs"] = self.rotate_usage_log(skills_dir)
        except Exception as e:
            logger.warning("disk_janitor_rotate_log_failed task_id=unknown skill_id=unknown trace_id=unknown: %s", e)
            report["rotated_logs"] = -1

        try:
            report["pruned_registry"] = self.prune_registry()
        except Exception as e:
            logger.warning("disk_janitor_prune_registry_failed task_id=unknown skill_id=unknown trace_id=unknown: %s", e)
            report["pruned_registry"] = -1

        try:
            report["cleaned_archives"] = self.cleanup_archived_skills(skills_dir)
        except Exception as e:
            logger.warning("disk_janitor_clean_archives_failed task_id=unknown skill_id=unknown trace_id=unknown: %s", e)
            report["cleaned_archives"] = -1

        return report

    def rotate_usage_log(self, skills_dir: Path):
        """Rotate .usage_log.jsonl to .usage_log.YYYYMMDD.jsonl and optionally gzip."""
        log_path = skills_dir / ".usage_log.jsonl"
        now = time.time()
        retention_seconds = self.config.retention_days * 86400
        deleted_count = 0

        if log_path.exists():
            max_bytes = int(self.config.max_log_size_mb * 1024 * 1024)
            if log_path.stat().st_size > max_bytes:
                stamp = time.strftime("%Y%m%d", time.localtime(now))
                rotated = skills_dir / f".usage_log.{stamp}.jsonl"
                if rotated.exists():
                    rotated = skills_dir / f".usage_log.{stamp}.{int(now)}.jsonl"
                shutil.move(str(log_path), str(rotated))
                with open(rotated, "rb") as src, gzip.open(f"{rotated}.gz", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                rotated.unlink(missing_ok=True)
                log_path.touch()

        for gz_file in skills_dir.glob(".usage_log.*.jsonl.gz"):
            if now - gz_file.stat().st_mtime > retention_seconds:
                gz_file.unlink()
                deleted_count += 1
                
        return deleted_count

    def prune_registry(self) -> int:
        """SQLite Registry pruning.
        DELETE FROM skills WHERE trust_level = 'auto-generated' AND updated_at < (NOW - days)
        VACUUM if deleted rows > vacuum_threshold.
        Returns deleted row count.
        """
        if not self.registry or getattr(self.registry, "db_path", None) is None:
            return 0
            
        import sqlite3
        from datetime import datetime, timedelta, timezone
        
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=self.config.retention_days)).isoformat()
        
        deleted_count = 0
        deleted_excess_count = 0
        
        try:
            with sqlite3.connect(self.registry.db_path) as conn:
                # 1. Age-based pruning for auto-generated
                cursor = conn.execute(
                    "DELETE FROM skills WHERE trust_level = 'auto-generated' AND updated_at < ?", 
                    (cutoff_date,)
                )
                deleted_count = cursor.rowcount
                
                # 2. Soft-cap pruning: if total rows > max_registry_rows, prune oldest
                cursor = conn.execute("SELECT COUNT(*) FROM skills")
                total_rows = cursor.fetchone()[0]
                amount_to_delete = total_rows - self.config.max_registry_rows
                
                if amount_to_delete > 0:
                    cursor = conn.execute(
                        """DELETE FROM skills WHERE id IN (
                            SELECT id FROM skills ORDER BY trust_level ASC, updated_at ASC LIMIT ?
                        )""",
                        (amount_to_delete,)
                    )
                    deleted_excess_count = cursor.rowcount
                
                total_deleted = deleted_count + deleted_excess_count
                
                if total_deleted > self.config.vacuum_threshold:
                    conn.execute("VACUUM")
                    
                return total_deleted
        except Exception as e:
            logger.warning("prune_registry_failed task_id=unknown skill_id=unknown trace_id=unknown [%s]: %s", self.registry.db_path, e)
            return 0

    def cleanup_archived_skills(self, skills_dir: Path) -> int:
        """Delete skills/archived/ *.md files older than retention_days.
        Returns number of deleted files.
        """
        archived_dir = skills_dir.parent / "archived"
        if not archived_dir.exists():
            return 0
            
        deleted_count = 0
        now = time.time()
        retention_seconds = self.config.retention_days * 86400
        
        for md_file in archived_dir.glob("*.md"):
            if now - md_file.stat().st_mtime > retention_seconds:
                md_file.unlink()
                deleted_count += 1
                
        return deleted_count
