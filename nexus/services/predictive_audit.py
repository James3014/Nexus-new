import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone
import lancedb
import pandas as pd
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class PredictiveAuditor:
    """⚖️ Nexus v26.0 Predictive Auditor.
    
    Performs risk assessment by comparing proposed implementation packs
    against synthesized Wisdom Rules in LanceDB.
    """
    
    def __init__(self, project_root: str = str(__import__("pathlib").Path(__file__).resolve().parents[2])):
        self.project_root = Path(project_root)
        self.db_path = self.project_root / ".nexus/memory/memory_index.lancedb"
        
        # Consistent embedding model for alignment
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self._init_db()

    def _init_db(self):
        """🛡️ Connect to wisdom_registry table."""
        try:
            self.db = lancedb.connect(str(self.db_path))
            if "wisdom_registry" not in self.db.table_names():
                logger.warning("⚠️ [Auditor] wisdom_registry table not found. Run 'nexus wisdom sync' first.")
                self.table = None
            else:
                self.table = self.db.open_table("wisdom_registry")
        except Exception as e:
            logger.error(f"❌ [Auditor] Failed to connect to LanceDB: {e}")
            self.table = None

    def audit_risk(self, pack_data: Dict[str, Any]) -> Dict[str, Any]:
        """🔍 AUDIT: Calculate risk score for a given implementation pack."""
        if not self.table:
            return {
                "task_id": pack_data.get("task_id", "unknown"),
                "risk_score": 0.0,
                "status": "PROCEED",
                "findings": [],
                "recommendation": "MONITORED_EXECUTION",
                "message": "Wisdom Registry unreachable.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # 1. Extract implementation intent
        intent = pack_data.get("planner_output", {}).get("goal", "unknown intent")
        intent_vector = self.model.encode(intent).tolist()

        # 2. Query LanceDB (Vector Search)
        # We look for rules with high semantic similarity to the current intent
        hits = self.table.search(intent_vector).limit(5).to_pandas()

        # 3. Calculate Weighted Risk Score
        risks = []
        max_score = 0.0
        
        for _, hit in hits.iterrows():
            # LanceDB vector search returns 'distance', we convert to similarity
            # (Note: dist=0 means exact match, dist=1+ means less similar)
            similarity = 1.0 - (hit.get("_distance", 1.0) / 2.0)
            
            # Apply Wisdom Weighting (Aged rules have lower weight)
            # Logic: score * weight
            weight = hit.get("score", 1.0)
            weighted_similarity = similarity * weight
            
            if weighted_similarity > 0.6: # Risk threshold
                risk_item = {
                    "rule_id": hit.get("id"),
                    "rule_text": hit.get("rule_text"),
                    "similarity": round(weighted_similarity, 3),
                    "evidence_ids": hit.get("ev_ids", []),
                    "severity": "HIGH" if weighted_similarity > 0.8 else "MEDIUM"
                }
                risks.append(risk_item)
                max_score = max(max_score, weighted_similarity)

        # 4. Compile Audit Report
        report = {
            "task_id": pack_data.get("task_id", "unknown"),
            "risk_score": round(max_score, 3),
            "status": "BLOCK" if max_score > 0.8 else "PROCEED",
            "findings": risks,
            "recommendation": "AUTO_REPLAN" if max_score > 0.8 else "MONITORED_EXECUTION",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"⚖️ [Auditor] Audit complete. Risk Score: {report['risk_score']} | Status: {report['status']}")
        return report

# Singleton instance
predictive_auditor = PredictiveAuditor()
