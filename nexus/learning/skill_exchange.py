"""Skill Exchange Protocol implementation.

Pillar 2 of the Cross-Agent Skill Sharing Architecture.
Implements the push/pull synchronization between the local FS SkillStore 
and the global SQLite SkillRegistry, enforcing Trust Demotion rules for remote skills.
"""

import json
from typing import List, Optional, Dict, Any
import logging

from nexus.learning.skill_store import SkillStore
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric

logger = logging.getLogger(__name__)

class SkillExchange:
    # 信任降權鐵律：遠端不管多強，進到本機最高只能當作 reviewed 參考
    TRUST_DEMOTION_MAP = {
        "production": "reviewed",
        "tested": "reviewed",
        "reviewed": "reviewed",
        "auto-generated": "auto-generated",
    }

    def __init__(self, store: SkillStore, registry: SkillRegistry):
        self.store = store
        self.registry = registry

    def push_local_to_registry(self, task_id: str, node_id: str = "local") -> bool:
        """Push a local skill to the shared registry."""
        filename = f"{task_id}.md"
        local_fm = self.store.get_skill_summary(filename)
        if not local_fm:
            logger.warning("push_failed: Local skill %s not found", filename)
            return False
            
        existing_row = self.registry.get_by_task_id(task_id)
        if existing_row:
            if not self._resolve_conflict(existing_row, local_fm, incoming_is_local=True):
                # The registry already has a superior or equivalent local skill, won't overwrite
                return False

        self.registry.upsert(local_fm, origin_node_id=node_id)
        return True

    def pull_from_registry(
        self, 
        query_tokens: set, 
        task_type: Optional[str] = None,
        max_results: int = 5,
        requesting_node_id: str = "local"
    ) -> List[SkillFrontmatter]:
        """Pull skills from registry, applying trust demotion to foreign skills."""
        raw_rows = self.registry.search(
            query_tokens=query_tokens, 
            task_type=task_type, 
            max_results=max_results,
            exclude_origin=requesting_node_id # Optional: avoid repeating pull of own skills
        )
        
        results = []
        for row in raw_rows:
            fm = self._row_to_skill(row)
            is_remote = row.get("origin_node_id") != requesting_node_id
            
            if is_remote:
                fm = self._apply_trust_demotion(fm)
            results.append(fm)
            
        return results

    def _apply_trust_demotion(self, fm: SkillFrontmatter) -> SkillFrontmatter:
        """Apply Trust Demotion protocol to remote skills."""
        original_level = fm.trust_level
        new_level = self.TRUST_DEMOTION_MAP.get(original_level, "auto-generated")
        if new_level != original_level:
            fm.trust_level = new_level
            # A remote skill loses its usage count advantage because it hasn't been verified locally
            fm.success_metric.retry_count = 0
            fm.success_metric.repair_success = False
        return fm

    def _resolve_conflict(self, existing: Dict[str, Any], incoming: SkillFrontmatter, incoming_is_local: bool) -> bool:
        """Determine if we should overwrite the existing node in the registry.
        True to overwrite, False to skip.
        """
        trust_ranking = {"auto-generated": 0, "reviewed": 1, "tested": 2, "production": 3}
        
        exist_trust = trust_ranking.get(existing.get("trust_level", "auto-generated"), 0)
        inc_trust = trust_ranking.get(incoming.trust_level, 0)
        
        if inc_trust > exist_trust:
            return True
        elif inc_trust == exist_trust:
            exist_origin = existing.get("origin_node_id", "local")
            # If trust levels are same, local node wins
            if incoming_is_local and exist_origin != "local":
                return True
        return False

    def _row_to_skill(self, row: Dict[str, Any]) -> SkillFrontmatter:
        """Hydrate SQLite row to SkillFrontmatter object."""
        try:
            kw = json.loads(row.get("keywords", "[]"))
        except (json.JSONDecodeError, TypeError):
            kw = []
            
        try:
            pp = json.loads(row.get("phantom_patterns", "[]"))
        except (json.JSONDecodeError, TypeError):
            pp = []
            
        try:
            vc = json.loads(row.get("verification_commands", "[]"))
        except (json.JSONDecodeError, TypeError):
            vc = []
            
        try:
            vec = json.loads(row.get("verification_exit_codes", "[]"))
        except (json.JSONDecodeError, TypeError):
            vec = []

        metric = SkillSuccessMetric(
            repair_success=bool(row.get("repair_success", 0)),
            retry_count=row.get("retry_count", 0),
            pattern_reuse_rate=row.get("pattern_reuse_rate", 0.0)
        )
        
        return SkillFrontmatter(
            name=row.get("name", row.get("task_id", "")),
            description=row.get("description", ""),
            task_id=row.get("task_id", ""),
            source=row.get("source", "nexus-auto-crystal"),
            trust_level=row.get("trust_level", "auto-generated"),
            task_type=row.get("task_type", "unknown"),
            keywords=kw,
            created_at=row.get("created_at", ""),
            plan_strategy=row.get("plan_strategy", ""),
            winning_hypothesis=row.get("winning_hypothesis", ""),
            phantom_patterns=pp,
            cycle_count=row.get("cycle_count", 0),
            cycle_root_cause=row.get("cycle_root_cause", ""),
            verification_commands=vc,
            verification_exit_codes=vec,
            embedding_model_version=row.get("embedding_model_version", ""),
            success_metric=metric
        )
