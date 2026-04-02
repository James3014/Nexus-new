from typing import Any, Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
import re
from datetime import datetime, timezone
from nexus.learning.skill_schema import SkillFrontmatter

class SearchStrategy(ABC):
    """
    Abstract base class for search strategies in KnowledgeIndex.
    """
    @abstractmethod
    def search(self, store: Any, query: str, top_k: int, threshold: float, **kwargs) -> List[Tuple[SkillFrontmatter, float]]:
        pass

    def apply_boosts(self, fm: SkillFrontmatter, score: float, task_type: Optional[str] = None) -> float:
        """Shared boost logic for all search strategies."""
        # Task Type Boost
        if task_type and fm.task_type and fm.task_type.lower() == task_type.lower():
            score *= 1.2
            
        # Trust Level Boost
        trust_boost = {"production": 1.3, "tested": 1.15, "reviewed": 1.05, "auto-generated": 1.0}
        score *= trust_boost.get(fm.trust_level, 1.0)
        
        # Crystal Decay
        if fm.last_used_at:
            try:
                dt = datetime.fromisoformat(fm.last_used_at.replace("Z", "+00:00"))
                days_idle = (datetime.now(timezone.utc) - dt).days
                if days_idle > 30:
                    weeks_over = (days_idle - 30) / 7
                    decay_factor = max(0.5, 1.0 - 0.05 * weeks_over)
                    score *= decay_factor
            except ValueError:
                import logging
                logging.getLogger(__name__).debug("skill_decay_parse_failed: %s", fm.task_id)

        # Verification Completeness Boost
        if fm.verification_exit_codes and all(c == 0 for c in fm.verification_exit_codes):
            score *= 1.1
            
        return score

class KeywordSearchStrategy(SearchStrategy):
    def __init__(self, tokenize_func):
        self.tokenize = tokenize_func

    def search(self, store: Any, query: str, top_k: int, threshold: float, **kwargs) -> List[Tuple[SkillFrontmatter, float]]:
        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []
            
        skill_files = store.list_learned_skills()
        scored_skills = []
        task_type = kwargs.get("task_type")
        
        for filename in skill_files:
            fm = store.get_skill_summary(filename)
            if not fm:
                continue
            
            doc_tokens = self.tokenize(fm.description).union(
                {kw.lower() for kw in fm.keywords}
            ).union(self.tokenize(fm.name))
            
            if not doc_tokens:
                continue
                
            intersection = query_tokens.intersection(doc_tokens)
            if not intersection:
                continue
                
            idf_score = sum(1.0 / (1.0 + len(doc_tokens)) for _ in intersection)
            tf_score = len(intersection) / len(query_tokens) if query_tokens else 0.0
            score = (tf_score + idf_score) / 2.0
            
            # Legacy keyword boost
            if fm.task_type and fm.task_type.lower() in query_tokens:
                score *= 1.5
                
            score = self.apply_boosts(fm, score, task_type)
            
            if score >= threshold:
                scored_skills.append((fm, score))
                
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        return scored_skills[:top_k]

class SemanticSearchStrategy(SearchStrategy):
    def __init__(self, model, cache, np_module, model_version: str):
        self.model = model
        self.cache = cache
        self.np = np_module
        self.model_version = model_version

    def search(self, store: Any, query: str, top_k: int, threshold: float, **kwargs) -> List[Tuple[SkillFrontmatter, float]]:
        if not self.model or not self.cache:
            return []
            
        q_emb = self.model.encode(query)
        skill_files = store.list_learned_skills()
        scored_skills = []
        task_type = kwargs.get("task_type")
        
        for filename in skill_files:
            fm = store.get_skill_summary(filename)
            if not fm:
                continue
                
            # Version match check
            if getattr(fm, "embedding_model_version", "") and fm.embedding_model_version != self.model_version:
                if hasattr(self.cache, 'invalidate'):
                    self.cache.invalidate(fm.task_id)
                
            skill_text = f"{fm.name} {fm.description} {' '.join(fm.keywords)}"
            s_emb = self.cache.get_or_compute(fm.task_id, skill_text, self.model)
            
            # Cosine similarity
            score = float(self.np.dot(q_emb, s_emb) / (self.np.linalg.norm(q_emb) * self.np.linalg.norm(s_emb)))
            
            score = self.apply_boosts(fm, score, task_type)
            
            if score >= threshold:
                scored_skills.append((fm, score))
                
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        return scored_skills[:top_k]
