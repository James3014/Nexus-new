from pathlib import Path
"""Test suite for Cross-Agent Skill Sharing Infrastructure.

Contains verification for:
1. SQLite SkillRegistry operations (upsert, search, stats)
2. SkillExchange Trust Demotion protocol
3. Federated KnowledgeIndex (search_all)
"""

import tempfile
import os
import json
import sqlite3
from dataclasses import asdict

import pytest

from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
from nexus.learning import skill_registry as skill_registry_module
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_exchange import SkillExchange
from nexus.learning.skill_store import SkillStore
from nexus.learning.knowledge_index import KnowledgeIndex


def _create_mock_skill(task_id: str, desc: str, trust: str) -> SkillFrontmatter:
    metric = SkillSuccessMetric(repair_success=True, retry_count=1)
    return SkillFrontmatter(
        name=task_id,
        description=desc,
        task_id=task_id,
        success_metric=metric,
        trust_level=trust,
        task_type="python-bugfix",
        keywords=["django", "orm"]
    )


def test_registry_upsert_and_stats():
    """Verify SQLite registry upsert, conflict resolution, and stats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "shared_skills.db"
        registry = SkillRegistry(db_path)
        
        # 1. Insert local skill
        skill1 = _create_mock_skill("TSK-1", "Local skill 1", "reviewed")
        registry.upsert(skill1, origin_node_id="local")
        
        # 2. Insert remote skill
        skill2 = _create_mock_skill("TSK-2", "Remote skill 2", "production")
        registry.upsert(skill2, origin_node_id="node-xyz")
        
        # 3. Assert stats
        stats = registry.get_stats()
        assert stats["total_skills"] == 2
        assert stats["production_skills"] == 1
        assert stats["remote_skills"] == 1
        
        # 4. Search
        res = registry.search(query_tokens={"django"}, task_type="python-bugfix")
        assert len(res) == 2
        assert res[0]["trust_level"] == "production" # Ordered by trust


def test_registry_write_guard_receipt_uses_wal_and_blocks_unqueued_concurrency():
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SkillRegistry(Path(tmpdir) / "shared_skills.db")

        clean = registry.build_write_guard_receipt()
        concurrent = registry.build_write_guard_receipt(concurrent_writer_count=3)

        assert clean["status"] == "PASS"
        assert clean["wal_status"] == "PASS"
        assert concurrent["status"] == "RETURN"
        assert "write_queue_not_pass" in concurrent["blockers"]
        assert "backoff_not_pass" in concurrent["blockers"]


def test_skill_registry_upsert_retries_sqlite_busy_then_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "shared_skills.db"
    registry = SkillRegistry(db_path)
    skill = _create_mock_skill("TSK-RETRY", "Retryable skill", "reviewed")
    original_connect = skill_registry_module.sqlite3.connect
    execute_calls = {"count": 0}

    class FlakyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            execute_calls["count"] += 1
            if execute_calls["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            with original_connect(db_path, timeout=10.0) as conn:
                return conn.execute(*args, **kwargs)

    monkeypatch.setattr(skill_registry_module.sqlite3, "connect", lambda *_args, **_kwargs: FlakyConnection())

    registry.upsert(skill)

    monkeypatch.setattr(skill_registry_module.sqlite3, "connect", original_connect)
    assert registry.get_by_task_id("TSK-RETRY")["description"] == "Retryable skill"
    assert registry.last_sqlite_retry_receipt is not None
    assert registry.last_sqlite_retry_receipt["status"] == "PASS"
    assert registry.last_sqlite_retry_receipt["attempts"] == 2
    assert registry.last_sqlite_retry_receipt["operation_name"] == "skill_registry_upsert"


def test_skill_registry_upsert_keeps_non_busy_errors_fail_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    registry = SkillRegistry(tmp_path / "shared_skills.db")

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("database disk image is malformed")

    monkeypatch.setattr(skill_registry_module.sqlite3, "connect", lambda *_args, **_kwargs: BrokenConnection())

    with pytest.raises(sqlite3.OperationalError, match="malformed"):
        registry.upsert(_create_mock_skill("TSK-BROKEN", "Broken db", "reviewed"))

    assert registry.last_sqlite_retry_receipt is not None
    assert registry.last_sqlite_retry_receipt["status"] == "RETURN"
    assert registry.last_sqlite_retry_receipt["attempts"] == 1
    assert registry.last_sqlite_retry_receipt["blockers"] == ["sqlite_error_not_retryable"]


def test_exchange_trust_demotion():
    """Verify remote skills are capped at 'reviewed'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "shared_skills.db"
        registry = SkillRegistry(db_path)
        store = SkillStore(Path(tmpdir))
        exchange = SkillExchange(store, registry)
        
        # Node XYZ creates a 'production' skill
        skill_remote = _create_mock_skill("TSK-99", "Super skill", "production")
        registry.upsert(skill_remote, origin_node_id="node-xyz")
        
        # Local node pulls it
        pulled = exchange.pull_from_registry(
            query_tokens={"django"},
            requesting_node_id="local"
        )
        
        assert len(pulled) == 1
        # The iron rule: remote production -> local reviewed
        assert pulled[0].trust_level == "reviewed"
        assert pulled[0].success_metric.repair_success == False
        assert pulled[0].success_metric.retry_count == 0


def test_exchange_conflict_resolution():
    """Locally generated skills have precedence over remote skills of same trust level."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SkillRegistry(Path(tmpdir) / "db")
        store = SkillStore(Path(tmpdir))
        exchange = SkillExchange(store, registry)
        
        # Scenario 1: Remote is highly trusted (production), local is weak (auto-generated)
        existing = {"trust_level": "auto-generated", "origin_node_id": "local"}
        incoming = _create_mock_skill("X", "desc", "production") 
        # (Assuming pull_from_registry handles demotion to reviewed first, but the raw logic check:)
        assert exchange._resolve_conflict(existing, incoming, incoming_is_local=False) == True
        
        # Scenario 2: Remote is reviewed, local is reviewed -> Local wins (don't overwrite)
        existing = {"trust_level": "reviewed", "origin_node_id": "local"}
        incoming = _create_mock_skill("X", "desc", "reviewed")
        assert exchange._resolve_conflict(existing, incoming, incoming_is_local=False) == False
        
        # Scenario 3: Remote reviewed is in DB, local reviewed comes in -> Local overwrites remote
        existing = {"trust_level": "reviewed", "origin_node_id": "remote"}
        incoming = _create_mock_skill("X", "desc", "reviewed")
        assert exchange._resolve_conflict(existing, incoming, incoming_is_local=True) == True


def test_federated_search_deduplication():
    """Ensure KnowledgeIndex merges FS and Registry properly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["NEXUS_SKILL_SHARE_ENABLED"] = "1"
        root_path = Path(tmpdir)
        index = KnowledgeIndex(root_path, use_embedding=False)
        
        # 1. Create a local skill in FS directly (mocking manual drop or prior existence)
        skill_path = root_path / "skills" / "learned" / "TSK-LOCAL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        # Using simple frontmatter that skill_artifact builds
        local_content = "---\nname: TSK-LOCAL\ndescription: \"FS skill django\"\nsource: local\ntrust_level: tested\ntask_type: fix\ntask_id: TSK-LOCAL\nkeywords: [\"django\"]\nsuccess_metric:\n  repair_success: true\n  retry_count: 1\n  pattern_reuse_rate: 0.0\n---"
        skill_path.write_text(local_content)
        
        # 2. Put a remote skill in registry
        remote_skill = _create_mock_skill("TSK-REMOTE", "Registry skill django", "production")
        remote_skill.task_type = "fix"
        index._registry.upsert(remote_skill, origin_node_id="node-remote")
        
        # 3. Put exact same local skill as remote variant in registry (simulating sync delay)
        duplicate_remote = _create_mock_skill("TSK-LOCAL", "Override FS skill django", "production")
        index._registry.upsert(duplicate_remote, origin_node_id="node-other")

        # 4. Search all
        results = index.search_all("django", task_type="fix", include_shared=True)
        
        # Deduplication must occur: Only 2 unique task_ids
        task_ids = {r.task_id for r in results}
        assert len(task_ids) == 2
        assert "TSK-LOCAL" in task_ids
        assert "TSK-REMOTE" in task_ids
        
        # The returned TSK-LOCAL should be from FS (local Preference), its trust is 'tested' NOT 'production'
        fs_res = next(r for r in results if r.task_id == "TSK-LOCAL")
        assert fs_res.trust_level == "tested"
        
        # The remote skill is demoted to 'reviewed'
        rem_res = next(r for r in results if r.task_id == "TSK-REMOTE")
        assert rem_res.trust_level == "reviewed"
