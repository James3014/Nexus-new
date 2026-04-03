import pytest
from datetime import datetime, timezone, timedelta
from nexus.services.lesson_resolver import (
    compute_conflict_score, 
    resolve_lesson_conflicts, 
    get_resolution_context,
    days_since_utc
)

@pytest.fixture
def mock_diagnosis():
    return {"primary_category": "LOGIC", "category": "LOGIC"}

@pytest.fixture
def base_lesson():
    return {
        "lesson_id": "sha-1",
        "task_id": "task-1",
        "category": "LOGIC",
        "confidence": 0.8,
        "timestamp_utc": (datetime.now(timezone.utc)).isoformat(),
        "outcome": "success",
        "schema_version": "lesson_event.v1",
        "reusable_when": ["auth"]
    }

def test_days_since_utc_accuracy():
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=10)).isoformat()
    assert round(days_since_utc(ts)) == 10

def test_compute_conflict_score_category_bonus(base_lesson, mock_diagnosis):
    # Match: 1.5x
    score_match = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    
    # Mismatch: 1.0x
    base_lesson["category"] = "DATA"
    score_mismatch = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    
    assert score_match.final_score > score_mismatch.final_score

def test_compute_conflict_score_recency_decay(base_lesson, mock_diagnosis):
    # New: ~1.0x
    score_new = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    
    # Old (90 days): ~0.4x
    old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    base_lesson["timestamp_utc"] = old_ts
    score_old = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    
    assert score_new.final_score > score_old.final_score
    assert score_old.components["recency_decay"] == 0.4

def test_compute_conflict_score_trust_tiers(base_lesson, mock_diagnosis):
    score_local = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    score_peer = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "peer"})
    score_eternal = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "eternal"})
    
    assert score_local.final_score > score_peer.final_score > score_eternal.final_score

def test_compute_conflict_score_specificity_bonus(base_lesson, mock_diagnosis):
    # Specific: 1.2x
    score_spec = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    
    # General: 1.0x
    base_lesson["reusable_when"] = []
    score_gen = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    
    assert score_spec.final_score > score_gen.final_score

def test_get_resolution_context_low_consensus_fallback(mock_diagnosis):
    # Empty or low score
    res = get_resolution_context([], mock_diagnosis)
    assert res["status"] == "low_consensus"
    assert "fallback" in res

def test_get_resolution_context_high_consensus_sucess(base_lesson, mock_diagnosis):
    score = compute_conflict_score(base_lesson, mock_diagnosis, {"trust_tier": "local"})
    res = get_resolution_context([score], mock_diagnosis)
    
    assert res["status"] == "high_consensus"
    assert res["consensus_score"] == score.final_score
    assert res["best_lesson_id"] == "sha-1"

def test_resolve_lesson_conflicts_ranking(base_lesson, mock_diagnosis):
    l1 = base_lesson.copy()
    l2 = base_lesson.copy()
    l2["lesson_id"] = "sha-2"
    l2["confidence"] = 0.5 # Lower confidence
    
    resolved = resolve_lesson_conflicts([l1, l2], mock_diagnosis)
    assert resolved[0].lesson["lesson_id"] == "sha-1"
    assert resolved[1].lesson["lesson_id"] == "sha-2"
