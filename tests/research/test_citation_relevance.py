import pytest
from nexus.research.learn.citation_relevance import score_citation_relevance

def test_citation_relevance_lexical_match():
    query = "L5.7 Eternal"
    claim = "This system uses L5.7 Eternal standards."
    score = score_citation_relevance(query, claim, {"source_url": "readme.md", "evidence_strength": "high"})
    assert score > 0.8

def test_citation_relevance_low_match():
    query = "how to bake cake"
    claim = "Nexus core P0 stages."
    score = score_citation_relevance(query, claim, {"source_url": "log.txt", "evidence_strength": "low"})
    assert score < 0.3
