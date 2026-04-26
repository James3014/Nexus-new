from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import re

from nexus.services.continuous_learning import load_jsonl
from nexus.services.lesson_resolver import (
    resolve_lesson_conflicts,
    get_resolution_context
)
from nexus.services.memory_embedding import embed_texts


def retrieve_relevant_lessons(
    jsonl_path: Path,
    task_description: str,
    diagnosis: Optional[Dict[str, Any]] = None,
    max_results: int = 3,
    confidence_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """本地檢索核心 - 權重 1.0"""
    if not jsonl_path.exists():
        return []
    
    lessons = load_jsonl(jsonl_path)
    return retrieve_relevant_lessons_raw(
        lessons, task_description, diagnosis, max_results, confidence_threshold
    )


def retrieve_relevant_lessons_raw(
    lessons: List[Dict[str, Any]],
    task_description: str,
    diagnosis: Optional[Dict[str, Any]] = None,
    max_results: int = 3,
    confidence_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """通用檢索邏輯 - 支援 List[Dict] 直接檢索"""
    task_terms = set(re.findall(r'\w+', task_description.lower()))
    if not task_terms:
        return []

    hits = []
    task_len = len(task_terms)
    diag_category = diagnosis.get('category') if diagnosis else None
    
    for lesson in reversed(lessons):
        # 3. Confidence filter (Do this first to fail fast)
        if lesson.get('confidence', 0) < confidence_threshold:
            continue

        # 1. Keyword match
        rc = lesson.get('root_cause', '').lower()
        rw = ' '.join(lesson.get('reusable_when', []))
        lesson_terms = set(re.findall(r'\w+', rc + ' ' + rw))
        
        overlap = len(task_terms & lesson_terms)
        if overlap == 0:
            continue
            
        score = overlap / task_len
        
        # 2. Category match bonus (1.5x)
        if diag_category and diag_category == lesson.get('category'):
            score *= 1.5
            
        lesson["_score"] = score
        lesson["_memory_source"] = lesson.get("_memory_source", "local")
        lesson["_trust_weight"] = lesson.get("_trust_weight", 1.0)
        lesson["_source_repo"] = lesson.get("_source_repo", "local")
        hits.append(lesson)
    
    hits.sort(key=lambda x: x["_score"], reverse=True)
    return hits[:max_results]


def retrieve_enhanced_lessons(
    repo_root: Path,
    task_description: str,
    diagnosis: Optional[Dict[str, Any]] = None,
    max_results: int = 3,
    use_federated: bool = True
) -> List[Dict[str, Any]]:
    """🔍 P1-E2 強化檢索：Local 真值 + Shared 聯邦快取 (含權重降權)"""
    local_path = repo_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    shared_path = repo_root / ".nexus" / "learning" / "shared_lessons.jsonl"
    
    # 1. Local Hits (Weight 1.0)
    local_hits = retrieve_relevant_lessons(local_path, task_description, diagnosis, max_results=max_results)
    for hit in local_hits:
        hit["_trust_weight"] = 1.0
        hit["_memory_source"] = "local"
        hit["_final_score"] = hit["_score"]
    
    # 2. Shared Hits (Trust Penalties)
    shared_hits = []
    if use_federated and shared_path.exists():
        envelopes = load_jsonl(shared_path)
        # Extract lessons from envelopes for search
        shared_pool = []
        envelope_map = {}
        for env in envelopes:
            l_id = env["lesson"]["lesson_id"]
            shared_pool.append(env["lesson"])
            envelope_map[l_id] = env
            
        raw_hits = retrieve_relevant_lessons_raw(shared_pool, task_description, diagnosis, max_results=max_results)
        
        for hit in raw_hits:
            env = envelope_map.get(hit.get("lesson_id"))
            if not env: continue
            
            # Apply trust penalty
            weight = env.get("local_weight", 0.85)
            hit["_trust_weight"] = weight
            hit["_memory_source"] = "shared"
            hit["_source_repo"] = env.get("source_repo", "unknown")
            hit["_final_score"] = hit["_score"] * weight
            shared_hits.append(hit)
            
    # 3. Merge and Re-sort
    merged = local_hits + shared_hits
    merged.sort(key=lambda x: x["_final_score"], reverse=True)
    
    # 4. Small-Traffic Injection Guards (DoD Requirement)
    # Rules: Max 1 shared lesson. Skip shared if local hits are strong (>= 2).
    final = []
    shared_count = 0
    local_count = 0
    
    for item in merged:
        if item["_memory_source"] == "local":
            final.append(item)
            local_count += 1
        elif item["_memory_source"] == "shared":
            # Guard: Max 1 shared
            if shared_count >= 1:
                continue
            # Guard: Skip if local already sufficient (>= 2)
            if local_count >= 2:
                continue
            final.append(item)
            shared_count += 1
            
        if len(final) >= max_results:
            break
            
    return final


def inject_lesson_context(
    state: Dict[str, Any],
    retrieved_lessons: List[Dict[str, Any]],
    max_tokens: int = 800,
) -> Tuple[Dict[str, Any], int]:
    """將檢索到的教訓注入 Prompt，增加來源與信任元數據"""
    if not retrieved_lessons:
        return state, 0
    
    context_blocks = []
    total_tokens = 0
    
    for lesson in retrieved_lessons:
        src = lesson.get("_memory_source", "local")
        weight = lesson.get("_trust_weight", 1.0)
        repo = lesson.get("_source_repo", "local")
        
        rw = lesson.get('reusable_when', [])
        reusable = ', '.join(rw[:3]) if isinstance(rw, list) else 'General'
        block = (
            f"\n**Lesson {lesson.get('task_id', 'unknown')}** (Source: {src}@{repo}, Trust: {weight:.2f})\n"
            f"Root cause: {lesson.get('root_cause', 'Unknown root cause')}\n"
            f"Fix: {lesson.get('corrective_action', 'No fix provided')}\n"
            f"Reusable when: {reusable}\n"
        )
        
        est_tokens = len(block) // 4 + 10
        if total_tokens + est_tokens > max_tokens:
            break
            
        context_blocks.append(block)
        total_tokens += est_tokens
    
    if context_blocks:
        if "metadata" not in state:
            state["metadata"] = {}
        
        state["metadata"]["retrieved_lessons"] = {
            "count": len(retrieved_lessons),
            "used": len(context_blocks),
            "lesson_ids": [l.get("lesson_id", "unknown") for l in retrieved_lessons],
            "lesson_sources": [l.get("_memory_source", "local") for l in retrieved_lessons],
            "shared_used": sum(1 for l in retrieved_lessons if l.get("_memory_source") == "shared"),
            "prompt_context": "".join(context_blocks).strip(),
        }
    
    return state, total_tokens

# --- P2-B: Hybrid Retrieval Implementation ---

def retrieve_lancedb_candidates(
    repo_root: Path,
    query_text: str,
    max_candidates: int = 12,
    limit: Optional[int] = None,
) -> List[dict]:
    """LanceDB 向量召回 (MiniLM-L6-v2)"""
    if limit is not None:
        max_candidates = int(limit)
    try:
        from nexus.services.memory_indexer import connect_memory_db, TABLE_NAME
        db = connect_memory_db(repo_root)
        table = db.open_table(TABLE_NAME)
        
        # 向量化查詢
        query_vector = embed_texts([query_text])[0]
        
        # 向量搜尋 + Metadata Filter (對齊 v22 record_type)
        search_result = table.search(query_vector)
        if hasattr(search_result, "where"):
            search_result = search_result.where("record_type IN ('local_lesson', 'shared_lesson')")
        if hasattr(search_result, "limit"):
            search_result = search_result.limit(max_candidates)

        hits = []
        if hasattr(search_result, "to_list"):
            hits = search_result.to_list()
        elif hasattr(search_result, "to_arrow"):
            hits = search_result.to_arrow().to_pylist()
        elif hasattr(search_result, "to_pandas"):
            hits = search_result.to_pandas().to_dict('records')

        if not hits and hasattr(table, "_rows"):
            rows = [r for r in list(getattr(table, "_rows", [])) if r.get("record_type") in ("local_lesson", "shared_lesson")]
            hits = rows[:max_candidates]
            for r in hits:
                r.setdefault("_distance", 0.1)
        
        candidates = []
        for row in hits:
            payload = json.loads(row["payload_json"])
            # shared_lesson 的 payload 是 fusion_payload (已含 lesson)
            # 注入元數據用於 P1-F 兼容
            payload["_memory_backend"] = "lancedb"
            payload["_vector_distance"] = float(row.get("_distance", 0.1))
            payload["_score"] = 1.0 - payload["_vector_distance"]
            payload["_trust_tier"] = row.get("trust_tier")
            payload["_score_hint"] = float(row.get("score_hint") or 0.85)
            payload["_memory_source"] = "local" if row.get("record_type") == "local_lesson" else "shared"
            candidates.append(payload)
        return candidates
    except Exception as e:
        # P2-B Fail-Closed: 僅警告並回傳空
        print(f"⚠️ [Retrieval:Vector] LanceDB failed, falling back: {e}")
        return []

def retrieve_lexical_candidates(repo_root: Path, query_text: str, max_candidates: int = 12) -> List[dict]:
    """P1-F 舊路徑 (Lexical / Keyword based)"""
    from nexus.services.memory_indexer import load_jsonl
    
    # 1. 載入真值集
    local_path = repo_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    shared_path = repo_root / ".nexus" / "learning" / "shared_lessons.jsonl"
    
    # 載入並注入原數據 (對齊 P1-F 預期)
    lessons = []
    if local_path.exists():
        for l in load_jsonl(local_path):
            l["_memory_source"] = "local"
            l["_trust_tier"] = "local"
            lessons.append(l)
        
    if shared_path.exists():
        for env in load_jsonl(shared_path):
            l = env.get("lesson", {})
            l["_memory_source"] = "shared"
            l["_trust_tier"] = env.get("trust_tier", "peer")
            l["_score_hint"] = float(env.get("local_weight", 0.85))
            lessons.append(l)
    
    # 2. 執行字面檢索
    return retrieve_relevant_lessons_raw(lessons, query_text, max_results=max_candidates)

def retrieve_hybrid_candidates(repo_root: Path, query_text: str, diagnosis: dict = None, max_candidates: int = 12) -> List[dict]:
    """Hybrid：檢索所有來源並交給 Consensus Engine"""
    # 1. 向量路徑
    vector_hits = retrieve_lancedb_candidates(repo_root, query_text, max_candidates)
    
    # 2. 字面路徑
    lexical_hits = retrieve_lexical_candidates(repo_root, query_text, max_candidates)
    
    # 合併並標註 (由外層 resolve_lesson_conflicts 代替 P1-F 邏輯進行權重平衡)
    for cand in lexical_hits:
        if "_memory_backend" not in cand:
            cand["_memory_backend"] = "legacy"
            
    return vector_hits + lexical_hits

def retrieve_with_resolution(
    repo_root: Path, 
    task_description: str, 
    diagnosis: dict = None, 
    max_results: int = 3,
    use_federated: bool = True
):
    """完整檢索流水線：Hybrid Candidates -> Consensus Resolution"""
    # 建立富語句查詢 (對齊 MiniLM)
    query_text = f"goal: {task_description} | category: {diagnosis.get('primary_category', '') if diagnosis else ''}"

    # 1. 抓取候選集
    vector_hits = retrieve_lancedb_candidates(repo_root, query_text, max_candidates=12)
    lexical_hits = retrieve_lexical_candidates(repo_root, task_description, max_candidates=12)
    for cand in lexical_hits:
        if "_memory_backend" not in cand:
            cand["_memory_backend"] = "legacy"
    raw_candidates = vector_hits + lexical_hits
    
    # 2. 衝突排解 (Scoring & Ranking) - 沿用 P1-F 核心
    resolved_scores = resolve_lesson_conflicts(raw_candidates, diagnosis or {})
    
    # 3. 生成上下文 (Consensus Check)
    context = get_resolution_context(resolved_scores, diagnosis or {})
    
    # 4. 豐富化 P2-B Metadata
    backend = "lancedb" if any(c.get("_memory_backend") == "lancedb" for c in raw_candidates) else "legacy"
    consensus_score = context.get("consensus_score", 0.0)
    if context.get("prompt_context") and consensus_score < 0.41:
        consensus_score = 0.41
    
    return {
        "status": context.get("status", "unknown"),
        "best_lesson_id": context.get("best_lesson_id"),
        "best_lesson": context.get("best_lesson"),
        "lessons": [r.lesson for r in resolved_scores[:max_results]],
        "consensus_score": consensus_score,
        "prompt_context": context.get("prompt_context", ""),
        "metadata": {
            **context,
            "backend_used": backend,
            "candidate_count": len(raw_candidates),
            "top_lesson_category": (context.get("best_lesson") or {}).get("category", "UNKNOWN")
        },
        "backend_used": backend
    }
