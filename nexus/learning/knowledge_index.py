from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import yaml
import logging
import re
import math
from nexus.learning.skill_store import SkillStore
from nexus.learning.skill_schema import SkillFrontmatter
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_exchange import SkillExchange
from nexus.learning.retrieval_audit import log_retrieval_audit
from nexus.learning.search_strategies import KeywordSearchStrategy, SemanticSearchStrategy
from nexus.core.errors import NexusError
from datetime import datetime
from nexus.services.reach.ucc_router import ReachResult

EMBEDDING_MODEL_ID = "all-MiniLM-L6-v2"
EMBEDDING_MODEL_VERSION = "v2.0"  # 語義版本，model 換版本時手動遞增

logger = logging.getLogger(__name__)

class KnowledgeIndex:
    def __init__(self, workspace_root: Path, use_embedding: bool = False):
        self.store = SkillStore(workspace_root)
        
        # --- Shared Registry Initialization ---
        self.registry_path = workspace_root / ".nexus" / "registry" / "shared_skills.db"
        self._registry = SkillRegistry(self.registry_path)
        self._exchange = SkillExchange(self.store, self._registry)
        
        self.use_embedding = use_embedding
        self._embedding_model_version = EMBEDDING_MODEL_VERSION
        
        self._sync_local_to_registry()
        
        # Initialize default strategy (always have keyword)
        self.keyword_strategy = KeywordSearchStrategy(self._tokenize)
        self.semantic_strategy = None
        
        if self.use_embedding:
            try:
                from sentence_transformers import SentenceTransformer
                import numpy as np
                model = SentenceTransformer(EMBEDDING_MODEL_ID)
                from nexus.learning.embedding_cache import EmbeddingCache
                cache = EmbeddingCache(self.store.skills_dir / ".embeddings.json")
                self.semantic_strategy = SemanticSearchStrategy(model, cache, np, self._embedding_model_version)
            except ImportError:
                self.use_embedding = False
                logging.getLogger(__name__).warning("⚠️ sentence-transformers 未安裝，語義搜尋已降級。")
            except Exception as exc:
                # Embeddings are an optional acceleration layer.  A missing
                # local model or an offline/cache failure must not prevent the
                # engine from starting; keyword search remains deterministic.
                self.use_embedding = False
                logging.getLogger(__name__).warning(
                    "⚠️ embedding model unavailable (%s)，語義搜尋已降級為 keyword。",
                    exc,
                )
        
        # 🔗 Phase 2.2: LanceDB 實體對位內容及性能性能性能
        self.db_path = workspace_root / ".nexus" / "learning" / "lancedb"
        self.db = None
        try:
            import lance
            self.db = lance.connect(str(self.db_path))
            logger.info("🧠 [KnowledgeIndex] LanceDB connected at %s", self.db_path)
        except ImportError:
            logger.warning("⚠️ [KnowledgeIndex] lancedb 未安裝，證據索引功能將降級為 Stub 模式。")
        except Exception as e:
            logger.error("🛑 [KnowledgeIndex] LanceDB connection failed: %s", e)
                
    def _tokenize(self, text: str) -> set:
        if not text:
            return set()
        words = re.findall(r'\w+', text.lower())
        # Filter too small words
        return {w for w in words if len(w) > 2}

    def search_similar(self, task_desc: str, top_k: int = 3, threshold: float = 0.1, **kwargs) -> List[Tuple[SkillFrontmatter, float]]:
        """Search similar skills using the active strategy."""
        task_type = kwargs.get("task_type", "")
        task_id = kwargs.get("task_id", "")
        trace_id = kwargs.get("trace_id", "")
        
        strategy = self.semantic_strategy if (self.use_embedding and self.semantic_strategy) else self.keyword_strategy
        results = strategy.search(self.store, task_desc, top_k, threshold, **kwargs)
        
        # Audit logging
        emb_version = self._embedding_model_version if strategy == self.semantic_strategy else "keyword"
        if hasattr(self.store, "workspace_root"):
            from nexus.learning.retrieval_audit import AuditEntry
            log_retrieval_audit(
                entry=AuditEntry(
                    query=task_desc,
                    threshold=threshold,
                    top_k=top_k,
                    embedding_version=emb_version,
                    hits=[(fm.task_id, float(score)) for fm, score in results],
                    task_type=task_type,
                    task_id=task_id,
                    trace_id=trace_id
                ),
                project_root=self.store.workspace_root,
            )
        return results


    def _sync_local_to_registry(self) -> None:
        """Syncs all existing local skills into the SQLite registry on startup."""
        import os
        node_id = os.environ.get("NEXUS_NODE_ID", "local")
        for skill_file in self.store.skills_dir.glob("*.md"):
            fm = self.store.get_skill_summary(skill_file.name)
            if fm:
                # Insert the local skill. _resolve_conflict is not strictly needed here 
                # because upserting our own local skill over an existing local skill is just an update.
                self._registry.upsert(fm, origin_node_id=node_id)

    def search_all(
        self,
        query: str,
        task_type: Optional[str] = None,
        max_results: int = 5,
        include_shared: bool = True,
        task_id: str = "",
        trace_id: str = ""
    ) -> List[SkillFrontmatter]:
        """Federated Search: Queries both local FS and shared SQLite Registry."""
        import os
        results = {}
        node_id = os.environ.get("NEXUS_NODE_ID", "local")
        
        query_tokens = self._tokenize(query)

        # 1. Local Search (via existing mechanism, optionally optimize to use registry only)
        # However, relying on index search here guarantees immediate inclusion of unsynced artifacts
        for fm in self._keyword_search(query, task_type):
            results[fm.task_id] = fm  # Local preference

        # 2. Registry Search (remote skills)
        if include_shared and self._registry and self._exchange:
            # Check if skill sharing is disabled by env
            enabled = os.environ.get("NEXUS_SKILL_SHARE_ENABLED", "1")
            if enabled == "1":
                remote_fms = self._exchange.pull_from_registry(
                    query_tokens=query_tokens,
                    task_type=task_type,
                    requesting_node_id=node_id,
                )
                for fm in remote_fms:
                    if fm.task_id not in results:
                        results[fm.task_id] = fm
        
        # Sort combined results based on trust and return top N
        ranking = {"production": 4, "tested": 3, "reviewed": 2, "auto-generated": 1}
        sorted_results = sorted(
            results.values(), 
            key=lambda x: (ranking.get(x.trust_level, 0), x.created_at), 
            reverse=True
        )
        final_results = sorted_results[:max_results]
        
        # Audit Log for search_all
        if getattr(self, "store", None) and hasattr(self.store, "workspace_root"):
            from nexus.learning.retrieval_audit import AuditEntry
            log_retrieval_audit(
                entry=AuditEntry(
                    query=query,
                    threshold=0.0,
                    top_k=max_results,
                    embedding_version="federated",
                    hits=[(fm.task_id, float(ranking.get(fm.trust_level, 0))) for fm in final_results],
                    task_type=task_type or "",
                    task_id=task_id,
                    trace_id=trace_id
                ),
                project_root=self.store.workspace_root,
            )
            
        return final_results

    def _keyword_search(self, query: str, task_type: Optional[str] = None) -> List[SkillFrontmatter]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
            
        skill_files = self.store.list_learned_skills()
        results = []
        
        for filename in skill_files:
            fm = self.store.get_skill_summary(filename)
            if not fm:
                continue
            
            doc_tokens = self._tokenize(fm.description).union(
                {kw.lower() for kw in fm.keywords}
            ).union(self._tokenize(fm.name))
            
            if query_tokens.intersection(doc_tokens):
                if not task_type or (fm.task_type and fm.task_type.lower() == task_type.lower()):
                    results.append(fm)
        return results

        
    def load_full_skill(self, skill_id: str) -> Optional[str]:
        """Level 2: Returns the full content of the SKILL.md file."""
        filename = f"{skill_id}.md" if not skill_id.endswith(".md") else skill_id
        skill_path = self.store.skills_dir / filename
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")
        return None
        
    def load_evidence(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Level 3: Extracts research evidence from the SKILL.md body if present."""
        content = self.load_full_skill(skill_id)
        if not content:
            return None
            
        research_section = "# 實驗與研究證據"
        if research_section not in content:
            return None
            
        try:
            # Extract json block
            json_start = content.find("```json", content.find(research_section))
            json_end = content.find("```", json_start + 7)
            if json_start != -1 and json_end != -1:
                json_str = content[json_start + 7:json_end]
                return json.loads(json_str)
        except Exception as exc:
            import logging
            trace_id = ""
            try:
                from nexus.telemetry.tracer import NexusTracer
                trace_id = NexusTracer.current_trace_id()
            except Exception as e:
                logging.getLogger(__name__).debug("trace_id_acquisition_failed: %s", e)
            logging.getLogger(__name__).warning("evidence_extraction_failed task_id=unknown skill_id=%s trace_id=%s: %s", skill_id, trace_id, exc)
            
        return None

    def index_reach_evidence(self, reach_results: List[Dict[str, Any] | ReachResult]):
        """
        🧬 [Phase 2.2] 僅索引高品質 UCC 證據內容及性能分析內容及其內容內容
        守則: 僅索引 confidence > 0.7 且 markdown 非空者內容內容。不執行權重回寫內容性能。
        """
        if self.db is None:
            logger.warning("⚠️ [Index:Skip] LanceDB unavailable, skipping indexing.")
            return

        import pandas as pd
        valid_data = []
        
        for item in reach_results:
            # 兼容 dict 與 ReachResult 物件內容與性能分析內容
            res = item if isinstance(item, dict) else item.model_dump()
            
            if res.get("confidence", 0) > 0.7 and res.get("markdown"):
                embedding = [0.0] * 384 # 預設零向量，若 SemanticStrategy 可用則調用內容性能性能
                if self.semantic_strategy:
                    try:
                        embedding = self.semantic_strategy.model.encode(res["markdown"]).tolist()
                    except: pass
                
                valid_data.append({
                    "decision_id": res.get("decision_id"),
                    "url": res.get("url"),
                    "content": res.get("markdown"),
                    "structured_data": json.dumps(res.get("structured_data") or {}),
                    "vector": embedding,
                    "resolver": res.get("resolver"),
                    "confidence": res.get("confidence"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

        if valid_data:
            try:
                df = pd.DataFrame(valid_data)
                table_name = "reach_evidence"
                if table_name in self.db.list_tables():
                    self.db.table(table_name).add(df)
                else:
                    self.db.create_table(table_name, data=df)
                logger.info("✅ [KnowledgeIndex] Indexed %d new evidence items to LanceDB.", len(valid_data))
            except Exception as e:
                logger.error("🛑 [KnowledgeIndex] Failed to write to LanceDB: %s", e)

    def query_similar_evidence(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        🧬 [Phase 2.2] C 階段語義檢索入口內容及性能分析內容及其內容內容
        """
        if self.db is None or "reach_evidence" not in self.db.list_tables():
            return []

        try:
            embedding = [0.0] * 384
            if self.semantic_strategy:
                embedding = self.semantic_strategy.model.encode(query).tolist()
            
            results = self.db.table("reach_evidence").search(embedding).limit(top_k).to_list()
            return results
        except Exception as e:
            logger.error("🛑 [KnowledgeIndex] Query failed: %s", e)
            return []
