#!/usr/bin/env python3
import logging
from pathlib import Path
from typing import List, Dict, Any
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.learning.knowledge_index import KnowledgeIndex

logger = logging.getLogger(__name__)

class CrystallizePhaseHandler(BasePhaseHandler):
    """
    💎 Phase C: Crystallize
    負責將執行紀錄轉化為高品質工程日誌，並執行感官證據之實體索引 (Phase 2.2)。
    """
    def __init__(self, project_root: Any, run_dir: Any):
        super().__init__(project_root, run_dir, name="C", priority=600)
        self.k_index = KnowledgeIndex(self.project_root, use_embedding=True)

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("💎 [C-Stage] Crystallizing session results and indexing evidence.")
        
        # 1. 收集本輪所有 UCC 證據內容及性能及性能性能內容分析
        ucc_evidence = context.get("ucc_evidence", [])
        spec_veto_docs = context.get("ground_truth_docs", []) # 來自 Phase D 內容及性能性能
        
        all_evidence = ucc_evidence + spec_veto_docs
        
        # 2. 執行實體索引 (LanceDB)
        indexed_count = 0
        if all_evidence:
            try:
                self.k_index.index_reach_evidence(all_evidence)
                indexed_count = len([e for e in all_evidence if e.get("confidence", 0) > 0.7])
            except Exception as e:
                logger.error("🛑 [C-Stage:Learning] Indexing failed: %s", e)

        # 3. 產出結晶化標籤內容及性能性能分析性能性能
        lessons = {
            "reach_evidence_indexed": indexed_count,
            "queryable_in_future": True,
            "decision_ids": [e.get("decision_id") for e in all_evidence if e.get("decision_id")]
        }
        
        # 4. 物理日誌產出 (Legacy Support)內容內容及性能性能分析
        self._generate_daily_log(context)

        # 5. 回傳 C 階段產物內容及性能內容性能性能性能
        return {
            "crystallized_evidence": lessons,
            "status": "COMPLETED",
            "indexed_count": indexed_count
        }

    def _generate_daily_log(self, context: Dict[str, Any]):
        """[Legacy] 產生 Daily_Log.md"""
        log_path = self.project_root / "Daily_Log.md"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- [C-Phase] Evidence Indexed: {len(context.get('ucc_evidence', []))} items ---\n")
