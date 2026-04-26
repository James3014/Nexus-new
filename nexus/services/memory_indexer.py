"""
P2-A: LanceDB Memory Indexer
負責從 .nexus 知識真值中提取並索引化向量資料，具備配額管理與冪等性。
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import logging
import lancedb
from lancedb.pydantic import Vector, LanceModel
from datetime import datetime, timezone, timedelta

from nexus.services.memory_embedding import embed_texts, EMBED_DIM

# 配置
TABLE_NAME = "memory_index"
DB_CORE_PATH = ".nexus/memory/memory_index.lancedb"

# 配額 (Disk Quotas)
QUOTA_RUN_MANIFESTS = 50
QUOTA_OUTCOME_EVENTS = 1000
_DB_CACHE: Dict[str, Any] = {}

class IndexerError(RuntimeError):
    pass

def stable_hash(*parts: str) -> str:
    """生成穩定 ID 用於冪等 Upsert"""
    joined = "||".join(str(p or "") for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()

def connect_memory_db(repo_root: Path):
    db_path = repo_root / DB_CORE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    key = str(db_path.resolve())
    if key not in _DB_CACHE:
        _DB_CACHE[key] = lancedb.connect(str(db_path))
    return _DB_CACHE[key]

# P2-A Schema 定義 (對齊 v22 治理欄位)
class MemoryIndexRecord(LanceModel):
    record_id: str
    record_type: str
    task_id: str
    trace_id: str
    decision_id: str
    phase: str
    category: str
    trust_tier: str
    source_type: str
    contract_version: str
    created_at_utc: str
    score_hint: float
    payload_json: str
    embedding: Vector(EMBED_DIM)

def ensure_table(db):
    """建立獲取 LanceDB 表結構 (384-dim)"""
    try:
        return db.open_table(TABLE_NAME)
    except Exception:
        return db.create_table(TABLE_NAME, schema=MemoryIndexRecord)

# --- Ingestors (Read-Only from Truth) ---

def load_jsonl(path: Path) -> List[dict]:
    if not path.exists(): return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line: rows.append(json.loads(line))
    return rows

def iter_local_lessons(repo_root: Path) -> Iterable[Dict[str, Any]]:
    path = repo_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    for row in load_jsonl(path):
        yield {
            "record_id": stable_hash("local_lesson", row.get("lesson_id")),
            "record_type": "local_lesson",
            "task_id": str(row.get("task_id") or ""),
            "trace_id": str(row.get("trace_id") or ""),
            "decision_id": str(row.get("decision_id") or ""),
            "phase": str(row.get("source_phase") or "C"),
            "category": str(row.get("category") or ""),
            "trust_tier": "local",
            "source_type": "local",
            "contract_version": str(row.get("contract_version") or "v22"),
            "created_at_utc": str(row.get("timestamp_utc") or ""),
            "score_hint": float(row.get("confidence") or 0.7),
            "payload": row,
        }

def iter_shared_lessons(repo_root: Path) -> Iterable[Dict[str, Any]]:
    path = repo_root / ".nexus" / "learning" / "shared_lessons.jsonl"
    for env in load_jsonl(path):
        lesson = env.get("lesson", {})
        # 建立融合 Payload：Lesson 內容 + Envelope 元數據 (用於真值追溯)
        fusion_payload = lesson.copy()
        fusion_payload["_envelope"] = {k: v for k, v in env.items() if k != "lesson"}
        
        yield {
            "record_id": stable_hash("shared_lesson", env.get("cache_id")),
            "record_type": "shared_lesson",
            "task_id": str(lesson.get("task_id") or ""),
            "trace_id": str(lesson.get("trace_id") or ""),
            "decision_id": str(lesson.get("decision_id") or ""),
            "phase": str(lesson.get("source_phase") or "C"),
            "category": str(lesson.get("category") or ""),
            "trust_tier": str(env.get("trust_tier") or "peer"),
            "source_type": str(env.get("source_type") or "p2p"),
            "contract_version": str(env.get("source_contract_version") or "v22"),
            "created_at_utc": str(lesson.get("timestamp_utc") or ""),
            "score_hint": float(env.get("local_weight") or 0.85),
            "payload": fusion_payload,
        }

def iter_run_manifests(repo_root: Path) -> Iterable[Dict[str, Any]]:
    runs_dir = repo_root / ".nexus" / "runs"
    if not runs_dir.exists(): return
    
    # P2-B: 實作 90 天時間窗口治理 (配額控制)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    
    # 僅獲取最近 N 個符合時間窗口的 run
    manifests = list(runs_dir.glob("*/manifest.json"))
    manifests.sort(key=lambda p: p.parent.name, reverse=True)
    
    count = 0
    for path in manifests:
        if count >= QUOTA_RUN_MANIFESTS: break
        try:
            data = json.loads(path.read_text())
            # 解析生成時間 (ISO 8601)
            raw_time = data.get("generatedat") or data.get("timestamp_utc", "")
            if not raw_time: continue
            
            gen_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            if gen_time < cutoff: continue
            
            yield {
                "record_id": stable_hash("run_manifest", data.get("taskid"), data.get("traceid")),
                "record_type": "run_manifest",
                "task_id": str(data.get("taskid") or ""),
                "trace_id": str(data.get("traceid") or ""),
                "decision_id": str(data.get("decisionid") or ""),
                "phase": str(data.get("phase") or ""),
                "category": "RUN",
                "trust_tier": "local",
                "source_type": "local",
                "contract_version": str(data.get("contractversion") or "v22"),
                "created_at_utc": raw_time,
                "score_hint": 0.5,
                "payload": data,
            }
            count += 1
        except Exception: continue

def iter_outcome_events(repo_root: Path) -> Iterable[Dict[str, Any]]:
    """載入 .nexus/metrics/skill_outcome_events.jsonl (P2-C)"""
    metrics_path = repo_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
    if not metrics_path.exists(): return
    
    # P2-B/C: 90 天窗口
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    
    for entry in load_jsonl(metrics_path):
        try:
            raw_time = entry.get("timestamp_utc", "")
            if not raw_time: continue
            
            gen_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            if gen_time < cutoff: continue
            
            # 使用穩定的 hash 作為 record_id
            rec_id = stable_hash("outcome", entry.get("task_id"), entry.get("decision_id"), entry.get("skill_id"))
            
            yield {
                "record_id": rec_id,
                "record_type": "outcome_event",
                "task_id": str(entry.get("task_id") or ""),
                "trace_id": str(entry.get("trace_id") or ""),
                "decision_id": str(entry.get("decision_id") or ""),
                "phase": str(entry.get("phase") or ""),
                "category": "OUTCOME",
                "trust_tier": "local",
                "source_type": "local",
                "contract_version": "v22",
                "created_at_utc": raw_time,
                "score_hint": float(entry.get("pattern_reuse") or 0.0) / 100.0, # 轉為 0-1
                "payload": entry,
            }
        except Exception: continue

def build_embedding_text(record: Dict[str, Any]) -> str:
    """提取語義特徵進行向量化 (MiniLM 優化：豐富語義欄位以提高召回精度)"""
    rt = record["record_type"]
    p = record["payload"]
    if rt in {"local_lesson", "shared_lesson"}:
        # shared_lesson 的 fusion_payload 已是 lesson dict，local_lesson 同構
        # 因此對兩種 type 均直接讀取 lesson 欄位
        lesson = p
        reusable = " ".join(lesson.get("reusable_when", []))
        outcome = lesson.get("outcome", "")
        parts = [
            f"category: {lesson.get('category', '')}",
            f"root cause: {lesson.get('root_cause', '')}",
            f"corrective action: {lesson.get('corrective_action', '')}",
            f"outcome: {outcome}" if outcome else "",
            f"reusable when: {reusable}" if reusable else "",
        ]
        return " | ".join(p for p in parts if p)
    elif rt == "run_manifest":
        goal = p.get("goal") or p.get("task", "")
        diag = p.get("diagnosis", {}) if isinstance(p.get("diagnosis"), dict) else {}
        diag_msg = diag.get("status") or p.get("diagnosis", "")
        return f"goal: {goal} | diagnosis: {diag_msg}"
    elif rt == "outcome_event":
        status = p.get("status", "UNKNOWN")
        skill = p.get("skill_id", "UNKNOWN")
        repair = "REPAIR_OK" if p.get("repair_success") else "REPAIR_FAIL"
        return f"outcome: {status} | skill: {skill} | {repair} | phase: {p.get('phase', '')}"
    return json.dumps(p)[:512]

# --- Indexing Core ---

def rebuild_memory_index(repo_root: Path) -> Dict[str, Any]:
    """同步索引：從 Full Rebuild 升級為增量 Upsert (S2 Hardening)"""
    db = connect_memory_db(repo_root)
    table = ensure_table(db)
    
    # 1. 收集所有潛在紀錄
    all_records = []
    all_records.extend(iter_local_lessons(repo_root))
    all_records.extend(iter_shared_lessons(repo_root))
    for rec in iter_run_manifests(repo_root):
        all_records.append(rec)
    for rec in iter_outcome_events(repo_root):
        all_records.append(rec)
        
    if not all_records:
        return {"status": "ok", "message": "No records to index.", "records_processed": 0}
        
    # 2. 增量過濾：僅對不存在於 DB 的 record_id 進行向量化
    try:
        existing_ids = set(table.to_pandas()["record_id"].tolist())
    except Exception:
        existing_ids = set()
    if not existing_ids and hasattr(table, "_rows"):
        try:
            existing_ids = {
                str(row.get("record_id"))
                for row in list(getattr(table, "_rows", []))
                if isinstance(row, dict) and row.get("record_id")
            }
        except Exception:
            existing_ids = set()
        
    new_records = [r for r in all_records if r["record_id"] not in existing_ids]
    
    if not new_records:
        return {"status": "ok", "message": "Index up to date.", "records_processed": 0}
        
    # 3. 向量化新紀錄
    texts = [build_embedding_text(r) for r in new_records]
    embeddings = embed_texts(texts)
    
    # 4. 準備寫入
    rows = []
    for r, emb in zip(new_records, embeddings):
        row = {k: v for k, v in r.items() if k != "payload"}
        row["payload_json"] = json.dumps(r["payload"], ensure_ascii=False)
        row["embedding"] = emb
        rows.append(row)
        
    # 5. 增量 Upsert (fallback to add() for lightweight/stub tables)
    if hasattr(table, "merge_insert"):
        table.merge_insert("record_id") \
             .when_not_matched_insert_all() \
             .when_matched_update_all() \
             .execute(rows)
    else:
        table.add(rows)
    
    return {
        "status": "ok", 
        "records_processed": len(rows),
        "total_records_searched": len(all_records),
        "db_path": str(repo_root / DB_CORE_PATH)
    }
