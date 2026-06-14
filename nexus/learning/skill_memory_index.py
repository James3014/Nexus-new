"""Skill Memory Query Layer: unified read-model for skill history and context injection."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class SkillHistoryRecord:
    """Compact skill history record for context injection."""
    skill_id: str
    matched_context_score: float = 0.0
    recent_success_rate: float = 0.0
    recent_failure_modes: List[str] = field(default_factory=list)
    last_used_at: str = ""
    reuse_count: int = 0
    trust_level: str = "auto-generated"
    evidence_refs: List[str] = field(default_factory=list)
    advice_note_codes: List[str] = field(default_factory=list)


class SkillMemoryIndex:
    """Unified read-model for skill memory queries.
    
    Reads from:
    1. skill_outcome_events.jsonl (outcome events)
    2. .usage_log.jsonl (usage events)
    3. skill frontmatter (trust levels)
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._outcome_cache: List[Dict[str, Any]] = []
        self._usage_cache: List[Dict[str, Any]] = []
        self._loaded = False
    
    def _load(self) -> None:
        """Load all skill memory data."""
        if self._loaded:
            return
        
        # Load outcome events
        outcome_path = self.project_root / ".nexus/metrics/skill_outcome_events.jsonl"
        if outcome_path.exists():
            try:
                with outcome_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                self._outcome_cache.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except Exception:
                pass
        
        # Load usage events
        skills_dir = self.project_root / ".agents/skills"
        usage_path = skills_dir / ".usage_log.jsonl"
        if usage_path.exists():
            try:
                with usage_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                self._usage_cache.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except Exception:
                pass
        
        self._loaded = True
    
    def query_skill_history(self, skill_id: str, task_context: str = "") -> SkillHistoryRecord:
        """Query history for a specific skill."""
        self._load()
        
        # Filter outcome events for this skill
        skill_outcomes = [e for e in self._outcome_cache if e.get("skill_id") == skill_id]
        
        # Filter usage events for this skill
        skill_usage = [e for e in self._usage_cache if e.get("skill_id") == skill_id]
        
        # Calculate success rate
        total = len(skill_outcomes)
        passed = sum(1 for e in skill_outcomes if e.get("pass", False))
        success_rate = passed / total if total > 0 else 0.0
        
        # Extract failure modes
        failure_modes = []
        for e in skill_outcomes:
            if not e.get("pass", False) and e.get("status"):
                failure_modes.append(e["status"])
        failure_modes = list(Counter(failure_modes).most_common(3))
        
        # Get last used time
        last_used = ""
        if skill_usage:
            last_used = skill_usage[-1].get("used_at", "")
        
        # Get trust level from frontmatter
        trust_level = self._get_trust_level(skill_id)
        
        return SkillHistoryRecord(
            skill_id=skill_id,
            recent_success_rate=success_rate,
            recent_failure_modes=[f[0] for f in failure_modes],
            last_used_at=last_used,
            reuse_count=len(skill_usage),
            trust_level=trust_level,
        )
    
    def query_contextual_skill_candidates(
        self, task_context: str, top_k: int = 5
    ) -> List[SkillHistoryRecord]:
        """Find relevant skills based on task context."""
        self._load()
        
        # Get all unique skill IDs
        all_skills = set()
        for e in self._outcome_cache:
            if e.get("skill_id"):
                all_skills.add(e["skill_id"])
        for e in self._usage_cache:
            if e.get("skill_id"):
                all_skills.add(e["skill_id"])
        
        # Query each skill and rank by relevance
        candidates = []
        for skill_id in all_skills:
            record = self.query_skill_history(skill_id, task_context)
            # Simple relevance: success rate * reuse count
            record.matched_context_score = record.recent_success_rate * min(record.reuse_count, 10)
            candidates.append(record)
        
        # Sort by score and return top_k
        candidates.sort(key=lambda x: -x.matched_context_score)
        return candidates[:top_k]
    
    def query_failure_patterns(self, skill_id: str, task_context: str = "") -> List[str]:
        """Get failure patterns for a skill."""
        self._load()
        
        skill_outcomes = [e for e in self._outcome_cache if e.get("skill_id") == skill_id]
        
        failure_patterns = []
        for e in skill_outcomes:
            if not e.get("pass", False):
                status = e.get("status", "")
                if status:
                    failure_patterns.append(status)
        
        return list(Counter(failure_patterns).most_common(5))
    
    def _get_trust_level(self, skill_id: str) -> str:
        """Get trust level from skill frontmatter."""
        skills_dir = self.project_root / ".agents/skills"
        skill_path = skills_dir / f"{skill_id}.md"
        
        if not skill_path.exists():
            return "auto-generated"
        
        try:
            content = skill_path.read_text(encoding="utf-8")
            # Parse frontmatter
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.split("\n"):
                    if line.strip().startswith("trust_level:"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        
        return "auto-generated"
    
    def build_context_injection(self, skill_id: str, task_context: str = "") -> str:
        """Build context string for injection into advisor prompt."""
        record = self.query_skill_history(skill_id, task_context)
        
        if record.reuse_count == 0:
            return ""
        
        lines = [f"[Skill History: {skill_id}]"]
        lines.append(f"Success rate: {record.recent_success_rate:.1%}")
        lines.append(f"Used {record.reuse_count} times")
        if record.recent_failure_modes:
            lines.append(f"Failure modes: {', '.join(record.recent_failure_modes[:3])}")
        if record.trust_level != "auto-generated":
            lines.append(f"Trust level: {record.trust_level}")
        
        return "\n".join(lines)
