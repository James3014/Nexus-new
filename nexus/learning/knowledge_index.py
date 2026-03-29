import re
import math
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from nexus.learning.skill_store import SkillStore
from nexus.learning.skill_schema import SkillFrontmatter
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_exchange import SkillExchange
import json
import yaml
import logging
from nexus.learning.retrieval_audit import log_retrieval_audit

EMBEDDING_MODEL_ID = "all-MiniLM-L6-v2"
EMBEDDING_MODEL_VERSION = "v2.0"  # 語義版本，model 換版本時手動遞增

class KnowledgeIndex:
    def __init__(self, workspace_root: Path, use_embedding: bool = False):
        self.store = SkillStore(workspace_root)
        
        # --- Shared Registry Initialization ---
        self.registry_path = workspace_root / ".nexus" / "registry" / "shared_skills.db"
        self._registry = SkillRegistry(self.registry_path)
        self._exchange = SkillExchange(self.store, self._registry)
        
        self.use_embedding = use_embedding
        self._model = None
        self._cache = None
        self._embedding_model_version = EMBEDDING_MODEL_VERSION
        
        self._sync_local_to_registry()
        
        if self.use_embedding:
            try:
                from sentence_transformers import SentenceTransformer
                import numpy as np
                self._model = SentenceTransformer(EMBEDDING_MODEL_ID)
                from nexus.learning.embedding_cache import EmbeddingCache
                self._cache = EmbeddingCache(self.store.skills_dir / ".embeddings.json")
                self.np = np
            except ImportError:
                self.use_embedding = False
                import logging
                logging.getLogger(__name__).warning("⚠️ sentence-transformers 未安裝，語義搜尋已降級為關鍵字模式。 安裝方式：uv add sentence-transformers")
                
    def _tokenize(self, text: str) -> set:
        if not text:
            return set()
        words = re.findall(r'\w+', text.lower())
        # Filter too small words
        return {w for w in words if len(w) > 2}

    def search_similar(self, task_desc: str, top_k: int = 3, threshold: float = 0.1, task_type: str = "", task_id: str = "", trace_id: str = "") -> List[Tuple[SkillFrontmatter, float]]:
        """
        Search for similar learned skills based on a TF-IDF style keyword intersection metric or embeddings.
        Returns a list of tuples containing (SkillFrontmatter, score).
        """
        if self.use_embedding and self._model and self._cache:
            results = self._embedding_search(task_desc, top_k, threshold, task_type)
            embedded = True
        else:
            results = self._keyword_search_legacy(task_desc, top_k, threshold, task_type)
            embedded = False
            
        emb_version = getattr(self._cache, "CURRENT_MODEL_VERSION", "unknown") if embedded else "keyword"
            
        # Retrieval Audit Log
        if getattr(self, "store", None) and hasattr(self.store, "workspace_root"):
            log_retrieval_audit(
                project_root=self.store.workspace_root,
                query=task_desc,
                threshold=threshold,
                top_k=top_k,
                embedding_version=emb_version,
                hits=[(fm.task_id, float(score)) for fm, score in results],
                task_type=task_type,
                task_id=task_id,
                trace_id=trace_id
            )
        return results

    def _embedding_search(self, task_desc: str, top_k: int, threshold: float, task_type: str) -> List[Tuple[SkillFrontmatter, float]]:
        q_emb = self._model.encode(task_desc)
        skill_files = self.store.list_learned_skills()
        scored_skills = []
        
        for filename in skill_files:
            fm = self.store.get_skill_summary(filename)
            if not fm:
                continue
                
            # 版本一致性校驗
            if getattr(fm, "embedding_model_version", "") and fm.embedding_model_version != getattr(self, "_embedding_model_version", ""):
                import logging
                logging.getLogger(__name__).warning(
                    "⚠️ Skill %s 的 embedding 版本 (%s) 與當前模型 (%s) 不一致，強制重新計算",
                    fm.name, fm.embedding_model_version, getattr(self, "_embedding_model_version", "")
                )
                if hasattr(self._cache, 'invalidate'):
                    self._cache.invalidate(fm.task_id)
                elif hasattr(self._cache, '_cache') and fm.task_id in self._cache._cache:
                    del self._cache._cache[fm.task_id]
                    self._cache._save()
                
            skill_text = f"{fm.name} {fm.description} {' '.join(fm.keywords)}"
            s_emb = self._cache.get_or_compute(fm.task_id, skill_text, self._model)
            
            # cosine similarity
            score = float(self.np.dot(q_emb, s_emb) / (self.np.linalg.norm(q_emb) * self.np.linalg.norm(s_emb)))
            
            if fm.task_type and task_type and fm.task_type.lower() == task_type.lower():
                score *= 1.2
                
            # Trust Level Boost（偏好驗證條件更完整的技能）
            trust_boost = {"production": 1.3, "tested": 1.15, "reviewed": 1.05, "auto-generated": 1.0}
            score *= trust_boost.get(fm.trust_level, 1.0)
            
            # Crystal Decay: 超過 30 天未命中 → 衰減 5%/週
            if getattr(fm, "last_used_at", None):
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromisoformat(fm.last_used_at.replace("Z", "+00:00"))
                    days_idle = (datetime.now(timezone.utc) - dt).days
                    if days_idle > 30:
                        weeks_over = (days_idle - 30) / 7
                        decay_factor = max(0.5, 1.0 - 0.05 * weeks_over)  # 最低衰減至 50%
                        score *= decay_factor
                except ValueError as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        "⚠️ 解析 Skill %s (task_id: %s) 的 datetime 失敗: %s",
                        fm.name, fm.task_id, e
                    )

            # Verification Completeness Boost
            if fm.verification_exit_codes and all(c == 0 for c in fm.verification_exit_codes):
                score *= 1.1
                
            if score >= threshold:
                scored_skills.append((fm, score))
                
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        return scored_skills[:top_k]

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
            log_retrieval_audit(
                project_root=self.store.workspace_root,
                query=query,
                threshold=0.0,
                top_k=max_results,
                embedding_version="federated",
                hits=[(fm.task_id, float(ranking.get(fm.trust_level, 0))) for fm in final_results],
                task_type=task_type or "",
                task_id=task_id,
                trace_id=trace_id
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

    def _keyword_search_legacy(self, task_desc: str, top_k: int, threshold: float, task_type: str) -> List[Tuple[SkillFrontmatter, float]]:
        query_tokens = self._tokenize(task_desc)
        if not query_tokens:
            return []
            
        skill_files = self.store.list_learned_skills()
        scored_skills = []
        
        for filename in skill_files:
            fm = self.store.get_skill_summary(filename)
            if not fm:
                continue
            
            # Combine skill description and its keywords for scoring
            doc_tokens = self._tokenize(fm.description).union(
                {kw.lower() for kw in fm.keywords}
            ).union(self._tokenize(fm.name))
            
            if not doc_tokens:
                continue
                
            intersection = query_tokens.intersection(doc_tokens)
            
            if not intersection:
                continue
                
            # Simple TF-IDF proxy: Score is based on intersection ratio over document size
            idf_score = sum(1.0 / (1.0 + len(doc_tokens)) for _ in intersection)
            tf_score = len(intersection) / len(query_tokens) if query_tokens else 0.0
            score = (tf_score + idf_score) / 2.0
            
            # Boost if task type explicitly matches in the query
            if fm.task_type and fm.task_type.lower() in query_tokens:
                score *= 1.5
                
            if fm.task_type and task_type and fm.task_type.lower() == task_type.lower():
                score *= 1.2
                
            if score >= threshold:
                scored_skills.append((fm, score))
                
        # Sort by score descending
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        return scored_skills[:top_k]
        
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
            except Exception:
                pass
            logging.getLogger(__name__).warning("evidence_extraction_failed task_id=unknown skill_id=%s trace_id=%s: %s", skill_id, trace_id, exc)
            
        return None
