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
        
        self._outcome_mtime: float = 0.0
        self._usage_mtime: float = 0.0
        self._conn: Optional[sqlite3.Connection] = None
        self._use_sqlite = True
        
        try:
            import sqlite3
            self._conn = sqlite3.connect(":memory:")
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outcomes (
                    skill_id TEXT,
                    pass INTEGER,
                    status TEXT,
                    evidence_refs TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usages (
                    skill_id TEXT,
                    used_at TEXT
                )
            """)
            self._conn.commit()
        except Exception:
            self._use_sqlite = False
    
    def _load(self) -> None:
        """Load all skill memory data with mtime checks."""
        import os
        outcome_path = self.project_root / ".nexus/metrics/skill_outcome_events.jsonl"
        skills_dir = self.project_root / ".agents/skills"
        usage_path = skills_dir / ".usage_log.jsonl"
        
        current_outcome_mtime = 0.0
        current_usage_mtime = 0.0
        
        try:
            if outcome_path.exists():
                current_outcome_mtime = os.path.getmtime(outcome_path)
            if usage_path.exists():
                current_usage_mtime = os.path.getmtime(usage_path)
        except Exception:
            pass
            
        # Check if cache is still valid
        if self._loaded and current_outcome_mtime == self._outcome_mtime and current_usage_mtime == self._usage_mtime:
            return
            
        # Cache stats
        self._outcome_mtime = current_outcome_mtime
        self._usage_mtime = current_usage_mtime
        
        # Clear caches
        self._outcome_cache.clear()
        self._usage_cache.clear()
        
        if self._use_sqlite and self._conn:
            try:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM outcomes")
                cursor.execute("DELETE FROM usages")
                self._conn.commit()
            except Exception:
                self._use_sqlite = False
                
        # 1. Load outcome events
        if outcome_path.exists():
            try:
                with outcome_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                self._outcome_cache.append(data)
                                if self._use_sqlite and self._conn:
                                    cursor = self._conn.cursor()
                                    evidence_refs_str = json.dumps(data.get("evidence_refs", []))
                                    cursor.execute(
                                        "INSERT INTO outcomes (skill_id, pass, status, evidence_refs) VALUES (?, ?, ?, ?)",
                                        (
                                            data.get("skill_id"),
                                            1 if data.get("pass") else 0,
                                            data.get("status"),
                                            evidence_refs_str
                                        )
                                    )
                            except (json.JSONDecodeError, Exception):
                                continue
                if self._use_sqlite and self._conn:
                    self._conn.commit()
            except Exception:
                pass
        
        # 2. Load usage events
        if usage_path.exists():
            try:
                with usage_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                self._usage_cache.append(data)
                                if self._use_sqlite and self._conn:
                                    cursor = self._conn.cursor()
                                    cursor.execute(
                                        "INSERT INTO usages (skill_id, used_at) VALUES (?, ?)",
                                        (data.get("skill_id"), data.get("used_at"))
                                    )
                            except (json.JSONDecodeError, Exception):
                                continue
                if self._use_sqlite and self._conn:
                    self._conn.commit()
            except Exception:
                pass
        
        self._loaded = True
    
    def query_skill_history(self, skill_id: str, task_context: str = "") -> SkillHistoryRecord:
        """Query history for a specific skill."""
        self._load()
        
        if self._use_sqlite and self._conn:
            try:
                cursor = self._conn.cursor()
                
                # Success rate
                cursor.execute(
                    "SELECT COUNT(*) as total, SUM(pass) as passed FROM outcomes WHERE skill_id = ?",
                    (skill_id,)
                )
                row = cursor.fetchone()
                total = row["total"] if row else 0
                passed = row["passed"] if row and row["passed"] is not None else 0
                success_rate = passed / total if total > 0 else 0.0
                
                # Failure modes
                cursor.execute(
                    "SELECT status, COUNT(*) as cnt FROM outcomes WHERE skill_id = ? AND pass = 0 AND status IS NOT NULL GROUP BY status ORDER BY cnt DESC LIMIT 3",
                    (skill_id,)
                )
                failure_modes = [r["status"] for r in cursor.fetchall() if r["status"]]
                
                # Reuse count & last used
                cursor.execute(
                    "SELECT COUNT(*) as reuse_cnt, MAX(used_at) as last_used FROM usages WHERE skill_id = ?",
                    (skill_id,)
                )
                row = cursor.fetchone()
                reuse_count = row["reuse_cnt"] if row else 0
                last_used = row["last_used"] if row and row["last_used"] else ""
                
                # Evidence refs
                cursor.execute(
                    "SELECT evidence_refs FROM outcomes WHERE skill_id = ? AND pass = 1 AND evidence_refs IS NOT NULL",
                    (skill_id,)
                )
                evidence_refs = []
                for r in cursor.fetchall():
                    try:
                        refs = json.loads(r["evidence_refs"])
                        if isinstance(refs, list):
                            evidence_refs.extend(refs)
                    except Exception:
                        pass
                
                trust_level = self._get_trust_level(skill_id)
                
                return SkillHistoryRecord(
                    skill_id=skill_id,
                    recent_success_rate=success_rate,
                    recent_failure_modes=failure_modes,
                    last_used_at=last_used,
                    reuse_count=reuse_count,
                    trust_level=trust_level,
                    evidence_refs=list(set(evidence_refs))
                )
            except Exception:
                # Fallback to list-based in case of sqlite error
                pass
                
        # List-based fallback logic
        skill_outcomes = [e for e in self._outcome_cache if e.get("skill_id") == skill_id]
        skill_usage = [e for e in self._usage_cache if e.get("skill_id") == skill_id]
        
        total = len(skill_outcomes)
        passed = sum(1 for e in skill_outcomes if e.get("pass", False))
        success_rate = passed / total if total > 0 else 0.0
        
        failure_modes = []
        for e in skill_outcomes:
            if not e.get("pass", False) and e.get("status"):
                failure_modes.append(e["status"])
        failure_modes = [f[0] for f in Counter(failure_modes).most_common(3)]
        
        last_used = ""
        if skill_usage:
            last_used = skill_usage[-1].get("used_at", "")
            
        evidence_refs = []
        for e in skill_outcomes:
            if e.get("pass") and e.get("evidence_refs"):
                evidence_refs.extend(e["evidence_refs"])
        
        trust_level = self._get_trust_level(skill_id)
        
        return SkillHistoryRecord(
            skill_id=skill_id,
            recent_success_rate=success_rate,
            recent_failure_modes=failure_modes,
            last_used_at=last_used,
            reuse_count=len(skill_usage),
            trust_level=trust_level,
            evidence_refs=list(set(evidence_refs))
        )
    
    def query_contextual_skill_candidates(
        self, task_context: str, top_k: int = 5
    ) -> List[SkillHistoryRecord]:
        """Find relevant skills based on task context."""
        self._load()
        
        all_skills = set()
        for e in self._outcome_cache:
            if e.get("skill_id"):
                all_skills.add(e["skill_id"])
        for e in self._usage_cache:
            if e.get("skill_id"):
                all_skills.add(e["skill_id"])
        
        candidates = []
        for skill_id in all_skills:
            record = self.query_skill_history(skill_id, task_context)
            # Relevance heuristic: success rate * min(usage count, 10)
            record.matched_context_score = record.recent_success_rate * min(record.reuse_count, 10)
            candidates.append(record)
        
        candidates.sort(key=lambda x: -x.matched_context_score)
        return candidates[:top_k]
    
    def query_failure_patterns(self, skill_id: str, task_context: str = "") -> List[str]:
        """Get failure patterns for a skill."""
        self._load()
        
        if self._use_sqlite and self._conn:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT status, COUNT(*) as cnt FROM outcomes WHERE skill_id = ? AND pass = 0 AND status IS NOT NULL GROUP BY status ORDER BY cnt DESC LIMIT 5",
                    (skill_id,)
                )
                return [r["status"] for r in cursor.fetchall() if r["status"]]
            except Exception:
                pass
                
        skill_outcomes = [e for e in self._outcome_cache if e.get("skill_id") == skill_id]
        failure_patterns = []
        for e in skill_outcomes:
            if not e.get("pass", False):
                status = e.get("status", "")
                if status:
                    failure_patterns.append(status)
        return [f[0] for f in Counter(failure_patterns).most_common(5)]
    
    def _get_trust_level(self, skill_id: str) -> str:
        """Get trust level from skill frontmatter."""
        skills_dir = self.project_root / ".agents/skills"
        skill_path = skills_dir / f"{skill_id}.md"
        
        if not skill_path.exists():
            return "auto-generated"
        
        try:
            content = skill_path.read_text(encoding="utf-8")
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
