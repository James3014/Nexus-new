"""
P1-F: Lesson Conflict Resolution (Consensus Engine)
處理多來源教訓衝突，輸出最佳修復路徑與共識分數。
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

def days_since_utc(timestamp_iso: str) -> float:
    """計算自教訓產生至今的天數"""
    try:
        ts_str = timestamp_iso.replace("Z", "+00:00")
        ts = datetime.fromisoformat(ts_str)
        delta = datetime.now(timezone.utc) - ts
        return max(0.0, delta.total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 999.0  # 過期推定

@dataclass
class ResolutionScore:
    lesson: Dict[str, Any]
    final_score: float
    components: Dict[str, float]
    trust_tier: str
    semantic_bonus: float = 1.0

def extract_source_metadata(lesson: Dict[str, Any]) -> Dict[str, Any]:
    """從 P1-E2 Envelope 或本地 Mock 中提取來源元數據"""
    # 如果 lesson 已經帶有 _memory_source (from retrieval), 直接使用
    return {
        "trust_tier": lesson.get("_trust_tier", "local"),
        "source_type": lesson.get("_memory_source", "local"),
        "source_repo": lesson.get("_source_repo", "local")
    }

def compute_conflict_score(lesson: Dict[str, Any], diagnosis: Dict[str, Any], source_meta: Dict[str, Any]) -> ResolutionScore:
    """加權衝突分數計算 (P1-F 核心演算法)"""
    base_conf = lesson.get("confidence", 0.7)
    
    # 1. Category match (權重 1.5)
    # v22: LOGIC/SECURITY 優先於 DATA/CONFIG
    target_cat = diagnosis.get("primary_category") or diagnosis.get("category")
    cat_weight = 1.5 if lesson.get("category") == target_cat else 1.0
    
    # 2. Recency (衰減 1.0 -> 0.4, 90 天窗口)
    days_old = days_since_utc(lesson.get("timestamp_utc", ""))
    recency_weight = max(0.4, 1.0 - min(days_old / 90.0, 1.0))
    
    # 3. Outcome quality (success: 1.3, partial: 1.0, failure: 0.3)
    outcome_map = {"success": 1.3, "partial": 1.0, "failure": 0.3}
    outcome_weight = outcome_map.get(lesson.get("outcome", "unknown"), 0.5)
    
    # 4. Source trust (local: 1.0, peer: 0.85, eternal: 0.80)
    trust_map = {"local": 1.0, "peer": 0.85, "eternal": 0.80}
    trust_weight = trust_map.get(source_meta.get("trust_tier", "local"), 0.7)
    
    # 5. Specificity (具備 reusable_when 條件則獎勵 1.2)
    specificity_weight = 1.2 if lesson.get("reusable_when") else 1.0
    
    # 6. Semantic Alignment (P2-B: 向量召回權重處理)
    # 如果是向量召回，根據 _score (0-1) 給予額外權重提升
    semantic_bonus = 1.0
    if "_score" in lesson:
        # 將 0.0-1.0 的向量分數映射至 1.0-1.2 的權重獎勵
        semantic_bonus = 1.0 + (float(lesson.get("_score", 0)) * 0.2)
    
    final = base_conf * cat_weight * recency_weight * outcome_weight * trust_weight * specificity_weight * semantic_bonus
    
    return ResolutionScore(
        lesson=lesson,
        final_score=round(final, 4),
        components={
            "base_confidence": base_conf,
            "category_bonus": cat_weight,
            "recency_decay": round(recency_weight, 2),
            "outcome_impact": outcome_weight,
            "trust_tier": trust_weight,
            "specificity_bonus": specificity_weight,
            "semantic_bonus": round(semantic_bonus, 2)
        },
        trust_tier=source_meta.get("trust_tier", "local"),
        semantic_bonus=round(semantic_bonus, 2)
    )

def resolve_lesson_conflicts(lessons: List[Dict[str, Any]], diagnosis: Dict[str, Any]) -> List[ResolutionScore]:
    """多角衝突排解與共識排序"""
    if not lessons:
        return []
    
    results = []
    for lesson in lessons:
        source_meta = extract_source_metadata(lesson)
        score = compute_conflict_score(lesson, diagnosis, source_meta)
        results.append(score)
    
    # 依 final_score 降序排列
    results.sort(key=lambda x: x.final_score, reverse=True)
    
    # TODO: 實作 P1-Fdiversity_selection (避免被單一類別霸佔)
    return results[:3]

def get_resolution_context(resolved: List[ResolutionScore], diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """獲取最終共識上下文與回退狀態"""
    # Fail-Closed: 低分回退策略 (< 0.3)
    MIN_CONSENSUS_THRESHOLD = 0.3
    
    if not resolved or resolved[0].final_score < MIN_CONSENSUS_THRESHOLD:
        return {
            "status": "low_consensus",
            "fallback": "pure_research",
            "consensus_score": resolved[0].final_score if resolved else 0.0,
            "prompt_context": "⚠️ [Consensus:FAIL] No high-confidence lessons found. Defaulting to first-principles reasoning."
        }
    
    best = resolved[0]
    lesson = best.lesson
    
    # 建立詳細內文塊
    content_block = (
        f"✅ [Consensus:OK] Priority Lesson {lesson.get('task_id', 'Unknown')} (Consensus: {best.final_score:.2f})\n"
        f"Root cause: {lesson.get('root_cause', 'N/A')}\n"
        f"Fix: {lesson.get('corrective_action', 'N/A')}\n"
    )
    
    return {
        "status": "high_consensus",
        "consensus_score": best.final_score,
        "best_lesson_id": lesson.get("lesson_id"),
        "best_lesson": lesson,
        "score_breakdown": best.components,
        "alternatives": [asdict(r) for r in resolved[1:3]],
        "prompt_context": content_block.strip()
    }
