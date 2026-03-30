"""Test suite for DiskJanitor cleanup strategies (Part A)."""

import os
import time
import json
import tempfile
import sqlite3
from pathlib import Path

from nexus.learning.disk_policy import DiskPolicy
from nexus.learning.disk_janitor import DiskJanitor
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.embedding_cache import EmbeddingCache

def test_rotate_usage_log():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()
        log_path = skills_dir / ".usage_log.jsonl"
        
        # Write some data
        with open(log_path, "w") as f:
            f.write(json.dumps({"test": 1}) + "\n")
            
        # Mock policy to trigger immediate rotation
        # 0 MB max size forces rotation
        policy = DiskPolicy(max_log_size_mb=0, retention_days=1)
        janitor = DiskJanitor(Path(tmpdir), config=policy)
        
        janitor.rotate_usage_log(skills_dir)
        
        # Verify: The original file should be empty (or re-created empty)
        assert log_path.exists()
        assert log_path.stat().st_size == 0
        
        # Verify: A .gz file should have been created
        gz_files = list(skills_dir.glob("*.jsonl.gz"))
        assert len(gz_files) == 1

def test_evict_embedding_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "cache.json"
        cache = EmbeddingCache(cache_path)
        
        # Override policy for test (max 2 entries)
        cache.config.max_cache_entries = 2
        
        # Add 3 entries with distinct last_accessed
        cache.data["old1"] = {"vector": [1.0], "last_accessed": 100}
        cache.data["old2"] = {"vector": [2.0], "last_accessed": 150} # Should be evicted if only 2 kept? Wait, 100 is oldest.
        cache.data["new1"] = {"vector": [3.0], "last_accessed": 200}
        
        cache.save()
        
        assert len(cache.data) == 2
        assert "new1" in cache.data
        assert "old2" in cache.data
        assert "old1" not in cache.data # The oldest (100) is evicted

def test_prune_registry():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "db"
        registry = SkillRegistry(db_path)
        
        # Insert test records
        now_str = "2026-03-30T00:00:00Z"
        old_str = "2020-01-01T00:00:00Z" # Way over 90 days
        
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO skills (id, task_id, origin_node_id, trust_level, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("old_auto", "TSK-OLD", "local", "auto-generated", old_str, old_str)
            )
            # A 'reviewed' skill should NOT be pruned even if old
            conn.execute(
                "INSERT INTO skills (id, task_id, origin_node_id, trust_level, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("old_rev", "TSK-REV", "local", "reviewed", old_str, old_str)
            )
            conn.execute(
                "INSERT INTO skills (id, task_id, origin_node_id, trust_level, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("new_auto", "TSK-NEW", "local", "auto-generated", now_str, now_str)
            )
            
        janitor = DiskJanitor(Path(tmpdir), registry=registry)
        deleted = janitor.prune_registry()
        
        assert deleted == 1 # Only 'old_auto' should be deleted
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT id FROM skills")
            ids = [row[0] for row in cursor.fetchall()]
            assert "old_auto" not in ids
            assert "old_rev" in ids
            assert "new_auto" in ids

def test_cleanup_archived_skills():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        archived_dir = skills_dir.parent / "archived"
        archived_dir.mkdir(parents=True)
        
        old_file = archived_dir / "old.md"
        old_file.write_text("old")
        
        new_file = archived_dir / "new.md"
        new_file.write_text("new")
        
        # Manually alter mtime to simulate age
        old_time = time.time() - (100 * 86400) # 100 days old
        os.utime(old_file, (old_time, old_time))
        
        policy = DiskPolicy(retention_days=90)
        janitor = DiskJanitor(Path(tmpdir), config=policy)
        
        deleted = janitor.cleanup_archived_skills(skills_dir)
        
        assert deleted == 1
        assert not old_file.exists()
        assert new_file.exists()
