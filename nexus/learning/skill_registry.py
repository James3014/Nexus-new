from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
"""Shared Skill Registry using SQLite.

Pillar 1 of the Cross-Agent Skill Sharing Architecture.
Handles persistence, deduplication, and search for both local and remote skills.
Utilizes WAL mode to support concurrent reads while a node is writing.
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from dataclasses import asdict

from nexus.learning.skill_schema import SkillFrontmatter

logger = logging.getLogger(__name__)

class SkillRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema and enable WAL mode."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id              TEXT PRIMARY KEY,
                    task_id         TEXT NOT NULL,
                    origin_node_id  TEXT NOT NULL DEFAULT 'local',
                    trust_level     TEXT NOT NULL DEFAULT 'auto-generated',
                    task_type       TEXT,
                    keywords        TEXT,
                    description     TEXT,
                    name            TEXT,
                    source          TEXT,
                    plan_strategy   TEXT,
                    winning_hypothesis TEXT,
                    phantom_patterns TEXT,
                    cycle_count     INTEGER DEFAULT 0,
                    cycle_root_cause TEXT,
                    verification_commands TEXT,
                    verification_exit_codes TEXT,
                    embedding_model_version TEXT,
                    repair_success  INTEGER DEFAULT 0,
                    retry_count     INTEGER DEFAULT 0,
                    pattern_reuse_rate REAL DEFAULT 0.0,
                    orchestration_pattern TEXT,
                    context_fingerprint TEXT,
                    decision_boundary TEXT,
                    iaov_steps      TEXT,
                    readiness_checklist TEXT,
                    portability_markers TEXT,
                    languages       TEXT,
                    file_patterns   TEXT,
                    win_rate        REAL DEFAULT 0.0,
                    origin_type     TEXT,
                    external_path   TEXT,
                    has_scripts     INTEGER DEFAULT 0,
                    has_evals       INTEGER DEFAULT 0,
                    trigger_keywords TEXT,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                )
            """)
            # Migration: Ensure v2.0 & Phase 13 columns exist (Safe against duplicates via PRAGMA)
            for col, col_type in [
                ("orchestration_pattern", "TEXT"),
                ("context_fingerprint", "TEXT"),
                ("decision_boundary", "TEXT"), 
                ("iaov_steps", "TEXT"), 
                ("readiness_checklist", "TEXT"), 
                ("portability_markers", "TEXT"),
                ("languages", "TEXT"),
                ("file_patterns", "TEXT"),
                ("win_rate", "REAL DEFAULT 0.0"),
                ("origin_type", "TEXT"),
                ("external_path", "TEXT"),
                ("has_scripts", "INTEGER DEFAULT 0"),
                ("has_evals", "INTEGER DEFAULT 0"),
                ("trigger_keywords", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE skills ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError: pass

            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_type ON skills(task_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trust_level ON skills(trust_level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_origin ON skills(origin_node_id)")

    def upsert(self, skill: SkillFrontmatter, origin_node_id: str = "local") -> None:
        """Insert or replace a skill in the registry."""
        skill_id = f"{origin_node_id}::{skill.task_id}"
        metric = skill.success_metric
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO skills (
                        id, task_id, origin_node_id, trust_level, task_type, keywords,
                        description, name, source, plan_strategy, winning_hypothesis,
                        phantom_patterns, cycle_count, cycle_root_cause, verification_commands,
                        verification_exit_codes, embedding_model_version, repair_success,
                        retry_count, pattern_reuse_rate, orchestration_pattern, 
                        context_fingerprint, decision_boundary, iaov_steps,
                        readiness_checklist, portability_markers, languages, file_patterns, win_rate,
                        origin_type, external_path, has_scripts, has_evals, trigger_keywords, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    skill_id,
                    skill.task_id,
                    origin_node_id,
                    skill.trust_level,
                    skill.task_type,
                    json.dumps(skill.keywords),
                    skill.description,
                    skill.name,
                    skill.source,
                    skill.plan_strategy,
                    skill.winning_hypothesis,
                    json.dumps(skill.phantom_patterns),
                    skill.cycle_count,
                    skill.cycle_root_cause,
                    json.dumps(skill.verification_commands),
                    json.dumps(skill.verification_exit_codes),
                    skill.embedding_model_version,
                    int(metric.repair_success),
                    metric.retry_count,
                    metric.pattern_reuse_rate,
                    skill.orchestration_pattern,
                    skill.context_fingerprint,
                    json.dumps(skill.decision_boundary),
                    json.dumps(skill.iaov_steps),
                    json.dumps(skill.readiness_checklist),
                    json.dumps(skill.portability_markers),
                    json.dumps(skill.languages),
                    json.dumps(skill.file_patterns),
                    float(skill.win_rate),
                    skill.origin_type,
                    skill.external_path,
                    int(bool(skill.has_scripts)),
                    int(bool(skill.has_evals)),
                    json.dumps(skill.trigger_keywords),
                    skill.created_at,
                    now
                ))
        except sqlite3.Error as exc:
            logger.error("skill_registry_upsert_failed [%s]: %s", skill_id, exc)

    def search(
        self,
        query_tokens: set,
        task_type: Optional[str] = None,
        max_results: int = 5,
        exclude_origin: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search skills natively using B-Tree index and LIKE expressions."""
        if not query_tokens and not task_type:
            return []
            
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            conditions = []
            params = []
            
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
                
            if query_tokens:
                # Require at least one matching token in name, desc, or keywords
                likes = []
                for token in query_tokens:
                    # Simple case-insensitive matching in text fields
                    lk = f"%{token}%"
                    likes.extend(["name LIKE ?", "description LIKE ?", "keywords LIKE ?"])
                    params.extend([lk, lk, lk])
                conditions.append(f"({' OR '.join(likes)})")
                
            if exclude_origin:
                conditions.append("origin_node_id != ?")
                params.append(exclude_origin)
                
            query = "SELECT * FROM skills"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
                
            # Prefer higher trust level and recently created
            query += """ 
                ORDER BY 
                  CASE trust_level
                    WHEN 'production' THEN 4
                    WHEN 'tested' THEN 3
                    WHEN 'reviewed' THEN 2
                    ELSE 1
                  END DESC,
                  created_at DESC
                LIMIT ?
            """
            params.append(max_results)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
        return [dict(row) for row in rows]
        
    def search_by_affinity(
        self,
        languages: List[str] = None,
        file_patterns: List[str] = None,
        task_type: Optional[str] = None,
        min_win_rate: float = 0.0,
        max_results: int = 3
    ) -> List[Dict[str, Any]]:
        """Search skills natively prioritizing language, file patterns and win rate."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            conditions = []
            params = []
            
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
                
            if languages:
                lang_likes = []
                for lang in languages:
                    lang_likes.append("languages LIKE ?")
                    params.append(f"%\"{lang}\"%")
                conditions.append(f"({' OR '.join(lang_likes)})")
                
            if file_patterns:
                pat_likes = []
                for pat in file_patterns:
                    pat_likes.append("file_patterns LIKE ?")
                    params.append(f"%\"{pat}\"%")
                conditions.append(f"({' OR '.join(pat_likes)})")

                
            conditions.append("win_rate >= ?")
            params.append(min_win_rate)
                
            query = "SELECT * FROM skills"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
                
            query += """ 
                ORDER BY win_rate DESC,
                  CASE trust_level
                    WHEN 'production' THEN 4
                    WHEN 'tested' THEN 3
                    WHEN 'reviewed' THEN 2
                    ELSE 1
                  END DESC
                LIMIT ?
            """
            params.append(max_results)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
        return [dict(row) for row in rows]
        
    def update_win_rate(self, task_id: str, win_rate: float) -> None:
        """Update the win rate of an existing skill by task_id."""
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("UPDATE skills SET win_rate = ? WHERE task_id = ?", (win_rate, task_id))
        except sqlite3.Error as exc:
            logger.error("skill_registry_update_winrate_failed [%s]: %s", task_id, exc)
        
    def get_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch all node variants of a skill by its task_id (favoring local first)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Ordering ensures 'local' origin comes first (since 'local' < 'node-xxx')
            cursor = conn.execute(
                "SELECT * FROM skills WHERE task_id = ? ORDER BY origin_node_id ASC LIMIT 1",
                (task_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_stats(self) -> Dict[str, Any]:
        """Fast aggregation without scanning file system."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN trust_level='production' THEN 1 ELSE 0 END) as production_skills,
                        SUM(CASE WHEN origin_node_id != 'local' THEN 1 ELSE 0 END) as remote_skills
                    FROM skills
                """)
                row = cursor.fetchone()
                return {
                    "total_skills": row[0] or 0,
                    "production_skills": row[1] or 0,
                    "remote_skills": row[2] or 0
                }
        except sqlite3.Error:
            return {"total_skills": 0, "production_skills": 0, "remote_skills": 0}
