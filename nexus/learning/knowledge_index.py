import re
import math
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from nexus.learning.skill_store import SkillStore
from nexus.learning.skill_schema import SkillFrontmatter
import json
import yaml

class KnowledgeIndex:
    def __init__(self, workspace_root: Path):
        self.store = SkillStore(workspace_root)
        
    def _tokenize(self, text: str) -> set:
        if not text:
            return set()
        words = re.findall(r'\w+', text.lower())
        # Filter too small words
        return {w for w in words if len(w) > 2}

    def search_similar(self, task_desc: str, top_k: int = 3, threshold: float = 0.1) -> List[Tuple[SkillFrontmatter, float]]:
        """
        Search for similar learned skills based on a TF-IDF style keyword intersection metric.
        Returns a list of tuples containing (SkillFrontmatter, score).
        """
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
            
            # Simple TF-IDF proxy: Score is based on intersection ratio over document size
            # Jaccard index similarity
            union = query_tokens.union(doc_tokens)
            score = len(intersection) / len(union) if union else 0.0
            
            # Boost if task type explicitly matches in the query
            if fm.task_type and fm.task_type.lower() in query_tokens:
                score *= 1.5
                
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
        except Exception:
            pass
            
        return None
