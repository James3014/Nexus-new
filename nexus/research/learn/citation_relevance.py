from __future__ import annotations
import re
from typing import Any, Dict, List

def score_citation_relevance(query: str, claim: str, metadata: Dict[str, Any]) -> float:
    """
    Calculate a relevance score (0.0 to 1.0) for a claim against a query.
    Factors:
    - Lexical overlap (Query words in claim)
    - Source prior (docs/README > logs)
    - Evidence strength (high > low)
    """
    query_words = set(re.findall(r'\w+', query.lower()))
    claim_words = set(re.findall(r'\w+', claim.lower()))
    
    if not query_words:
        return 0.0
        
    # 1. Lexical overlap (Jaccard-like but query-weighted)
    overlap = len(query_words.intersection(claim_words))
    lexical_score = overlap / max(1, len(query_words)) * 1.5
    
    # 2. Source section prior
    source_url = metadata.get("source_url", "").lower()
    source_weight = 1.0
    if any(k in source_url for k in ["readme", "docs", "skill.md", "spec"]):
        source_weight = 1.2
    elif "log" in source_url or "tmp" in source_url:
        source_weight = 0.8
        
    # 3. Evidence strength
    strength = metadata.get("evidence_strength", "medium").lower()
    strength_map = {"high": 1.1, "medium": 1.0, "low": 0.7}
    strength_weight = strength_map.get(strength, 1.0)
    
    final_score = lexical_score * source_weight * strength_weight
    return min(1.0, round(final_score, 4))
