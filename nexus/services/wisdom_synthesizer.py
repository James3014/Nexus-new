import json
import logging
import os
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone
import lancedb
import pandas as pd
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class WisdomSynthesizer:
    """🧠 Nexus v26.0 Wisdom Synthesizer.
    
    Transforms multiple task-local LessonEvents into generalized Wisdom Rules.
    Stores and indexes synthesized rules in LanceDB for predictive auditing.
    """
    
    def __init__(self, project_root: str = "/Users/jameschen/Workspace/nexus"):
        self.project_root = Path(project_root)
        self.db_path = self.project_root / ".nexus/memory/memory_index.lancedb"
        self.lessons_path = self.project_root / ".nexus/knowledge/lesson_events.jsonl"
        
        # Load embedding model
        # ⚠️ Using all-MiniLM-L6-v2 for <50ms query latency requirement.
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self._init_db()

    def _init_db(self):
        """🛡️ Initialize LanceDB and wisdom_registry table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        
        # Schema: {id, rule_text, vector, ev_ids[], score, created}
        if "wisdom_registry" not in self.db.table_names():
            # Initial dummy data to establish schema
            data = [{
                "id": "bootstrap",
                "rule_text": "Always ensure protocol alignment before construction.",
                "vector": self.model.encode("Always ensure protocol alignment before construction."),
                "ev_ids": ["EV-000"],
                "score": 1.0,
                "created": datetime.now(timezone.utc).isoformat()
            }]
            self.db.create_table("wisdom_registry", data=data)
            logger.info("✅ [Wisdom] Created wisdom_registry table in LanceDB.")

    def sync_all(self) -> Dict[str, Any]:
        """🔄 SYNC: Synthesize all lessons into general rules and update Registry."""
        # 1. Load LessonEvents
        lessons = self._load_lessons()
        if not lessons:
            return {"status": "EMPTY", "rules_synthesized": 0}

        # 2. Cluster Lessons (Basic Heuristic: by category)
        clusters = self._cluster_lessons(lessons)
        
        # 3. Synthesize Rules from clusters
        new_rules = []
        for category, cluster_lessons in clusters.items():
            rule_data = self._synthesize_cluster(category, cluster_lessons)
            if rule_data:
                new_rules.append(rule_data)

        # 4. Filter through MemPalace (L1 Ethical Guard)
        from nexus.services.mem_palace import mem_palace
        mem_palace.sync()
        clean_rules = mem_palace.verify(new_rules)

        # 5. Write to LanceDB
        if clean_rules:
            table = self.db.open_table("wisdom_registry")
            # Convert to DataFrame for LanceDB update
            df = pd.DataFrame(clean_rules)
            table.add(df)
            logger.info(f"✅ [Wisdom] Synthesized and registered {len(clean_rules)} global rules.")

        return {"status": "SUCCESS", "rules_synthesized": len(clean_rules)}

    def _load_lessons(self) -> List[Dict[str, Any]]:
        """🛡️ Load LessonEvents from JSONL."""
        if not self.lessons_path.exists():
            return []
        lessons = []
        with open(self.lessons_path, 'r') as f:
            for line in f:
                try:
                    lessons.append(json.loads(line))
                except Exception:
                    continue
        return lessons

    def _cluster_lessons(self, lessons: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """🛡️ Group lessons into clusters for synthesis."""
        clusters = {}
        for l in lessons:
            cat = l.get("category", "GENERAL")
            if cat not in clusters:
                clusters[cat] = []
            clusters[cat].append(l)
        return clusters

    def _synthesize_cluster(self, category: str, lessons: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """🛡️ Synthesize a group of lessons into a single Wisdom Rule.
        
        ⚠️ In a production scenario, this would use a Gemini summarization call.
        For Phase 4 initialization, we use a structured heuristic synthesis.
        """
        if not lessons:
            return None

        # Heuristic: Find common corrective actions
        actions = [l.get("corrective_action", "") for l in lessons]
        # Most frequent action (simple mode)
        from collections import Counter
        top_action = Counter(actions).most_common(1)[0][0]
        
        # Compose rule text
        rule_text = f"[{category}] {top_action}. Based on successful resolution of {len(lessons)} past instances."
        rule_id = hashlib.sha256(rule_text.encode()).hexdigest()[:12]
        
        ev_ids = list(set([l.get("task_id", "unknown") for l in lessons]))
        
        return {
            "id": f"RULE-{rule_id}",
            "rule_text": rule_text,
            "vector": self.model.encode(rule_text).tolist(), # Needs to be list for LanceDB JSON
            "ev_ids": ev_ids,
            "score": 0.9, # Base confidence for induction
            "created": datetime.now(timezone.utc).isoformat()
        }

# Singleton instance
wisdom_synthesizer = WisdomSynthesizer()
