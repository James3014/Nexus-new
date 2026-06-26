from typing import Any, Dict, List, Optional

class KnowledgeInjector:
    """
    🧬 Nexus Knowledge Injector (v25 Decoupled)
    負責從 SkillRegistry、MemPalace 與 WisdomVault 提取並注入先驗知識，物理剝離 ContextHub。
    """
    def __init__(self, skill_registry=None, mem_palace=None, wisdom_vault=None):
        self.skill_registry = skill_registry
        self.mem_palace = mem_palace
        self.wisdom_vault = wisdom_vault

    def recommend_skills(self, task_desc: str, target_files: Optional[List[str]] = None) -> List[Dict]:
        """向 SkillRegistry 檢索高勝率技能"""
        if not self.skill_registry:
            return []
            
        target_files = target_files or []
        _EXT_LANG_MAP = {".py": "python", ".rs": "rust", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".go": "go"}
        
        languages = set()
        file_patterns = set()
        
        for f in target_files:
            if f and "." in f:
                ext = f[f.rfind("."):]
                file_patterns.add(f"*{ext}")
                lang = _EXT_LANG_MAP.get(ext)
                if lang:
                    languages.add(lang)
                    
        candidates = self.skill_registry.search_by_affinity(
            languages=list(languages),
            file_patterns=list(file_patterns),
            min_win_rate=0.3,
            max_results=5
        )
        
        if self.mem_palace:
            candidates = self.mem_palace.verify(candidates)
            constraints = self.mem_palace.get_skill_constraints()
            
            _STOPWORDS = {"禁止", "使用", "不能", "不可", "禁用", "避免", "forbid", "不允許", "優先", "必須", "require", "prefer"}
            
            def _extract_keywords(phrase: str) -> List[str]:
                import re as _re
                tokens = _re.split(r"[\s,，\u3000]+", phrase.lower())
                return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 1]
            
            forbid_kws = []
            for f in constraints.get("forbid", []): forbid_kws.extend(_extract_keywords(f))
            prefer_kws = []
            for p in constraints.get("prefer", []): prefer_kws.extend(_extract_keywords(p))
            
            filtered = []
            for cand in candidates:
                content = str(cand).lower()
                if any(kw in content for kw in forbid_kws): continue
                filtered.append(cand)
                
            def score_cand(c):
                cnt = str(c).lower()
                return sum(1 for kw in prefer_kws if kw in cnt)
                
            filtered.sort(key=score_cand, reverse=True)
            candidates = filtered
            
        return [{
            "skill_id": c.get("task_id", ""),
            "name": c.get("name", ""),
            "winning_hypothesis": c.get("winning_hypothesis", ""),
            "win_rate": c.get("win_rate", 0.0)
        } for c in candidates[:3]]

    def inject_wisdom_prior(self, task_desc: str, target_files: List[str]) -> Dict[str, Any]:
        """從 WisdomVault 檢索歷史智慧"""
        if not self.wisdom_vault:
            return {}

        query = f"{task_desc} files:{' '.join(target_files[:3])}"
        try:
            results = self.wisdom_vault.search_wisdom(query, limit=3)
            if results is None or results.empty: return {}

            def extract_score(text: str) -> float:
                lines = text.split("\n")
                for line in lines:
                    if "Audit Score:" in line:
                        try: return float(line.split(":")[1].strip())
                        except: pass
                return 0.0

            top = results.iloc[0]
            battle_history = []
            for _, r in results.iterrows():
                battle_history.append({
                    "strategy": r.get("task", ""),
                    "score": extract_score(r.get("resolution", ""))
                })
                
            return {
                "prior_strategy": top.get("task", ""),
                "prior_confidence": float(top.get("_distance", 0.5)),
                "battle_history": battle_history,
                "suggestion": top.get("resolution", "")
            }
        except Exception:
            return {}
