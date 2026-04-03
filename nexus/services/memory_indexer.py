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

class IndexerError(RuntimeError):
    pass

def stable_hash(*parts: str) -> str:
    """生成穩定 ID 用於冪等 Upsert"""
    joined = "||".join(str(p or "") for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()

def connect_memory_db(repo_root: Path):
    db_path = repo_root / DB_CORE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(db_path))

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
            "task_id": row.get("task_id", ""),
            "trace_id": row.get("trace_id", ""),
            "decision_id": row.get("decision_id", ""),
            "phase": row.get("source_phase", "C"),
            "category": row.get("category", ""),
            "trust_tier": "local",
            "source_type": "local",
            "contract_version": row.get("contract_version", "v22"),
            "created_at_utc": row.get("timestamp_utc", ""),
            "score_hint": float(row.get("confidence", 0.7)),
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
            "task_id": lesson.get("task_id", ""),
            "trace_id": lesson.get("trace_id", ""),
            "decision_id": lesson.get("decision_id", ""),
            "phase": lesson.get("source_phase", "C"),
            "category": lesson.get("category", ""),
            "trust_tier": env.get("trust_tier", "peer"),
            "source_type": env.get("source_type", "p2p"),
            "contract_version": env.get("source_contract_version", "v22"),
            "created_at_utc": lesson.get("timestamp_utc", ""),
            "score_hint": float(env.get("local_weight", 0.85)),
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
                "task_id": data.get("taskid", ""),
                "trace_id": data.get("traceid", ""),
                "decision_id": data.get("decisionid", ""),
                "phase": data.get("phase", ""),
                "category": "RUN",
                "trust_tier": "local",
                "source_type": "local",
                "contract_version": data.get("contractversion", "v22"),
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
                "task_id": entry.get("task_id", ""),
                "trace_id": entry.get("trace_id", ""),
                "decision_id": entry.get("decision_id", ""),
                "phase": entry.get("phase", ""),
                "category": "OUTCOME",
                "trust_tier": "local",
                "source_type": "local",
                "contract_version": "v22",
                "created_at_utc": raw_time,
                "score_hint": float(entry.get("pattern_reuse", 0.0)) / 100.0, # 轉為 0-1
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
    """一鍵索引重建與同步
    
    v0.1: Full Rebuild 模式（先 drop 再 create）。
    - 優點：Schema 一致性保證、程式碼簡單。
    - 缺點：大型 corpus 每次需重算所有 embedding。
    TODO v0.2: 改用 table.merge_insert 實現增量 Upsert。
    """
    db = connect_memory_db(repo_root)
    # Full Rebuild: 刪除舊表並重建，確保 Schema 乾淨
    db.drop_table(TABLE_NAME, ignore_missing=True)
    table = ensure_table(db)
    
    # 1. 收集
    all_records = []
    all_records.extend(iter_local_lessons(repo_root))
    all_records.extend(iter_shared_lessons(repo_root))
    for rec in iter_run_manifests(repo_root):
        all_records.append(rec)
        
    # 3. Outcome Events (P2-C)
    for rec in iter_outcome_events(repo_root):
        all_records.append(rec)
        
    if not all_records:
        return {"status": "ok", "message": "No records to index.", "records_processed": 0}
        
    # 2. 向量化
    texts = [build_embedding_text(r) for r in all_records]
    embeddings = embed_texts(texts)
    
    # 3. 準備寫入 (JSON 序列化 Payload)
    rows = []
    for r, emb in zip(all_records, embeddings):
        row = {k: v for k, v in r.items() if k != "payload"}
        row["payload_json"] = json.dumps(r["payload"], ensure_ascii=False)
        row["embedding"] = emb
        rows.append(row)
        
    # 4. 冪等 Upsert (第一版先 Full Rebuild 以保證 Schema 一致)
    db.drop_table(TABLE_NAME, ignore_missing=True)
    table = ensure_table(db)
    table.add(rows)
    
    return {
        "status": "ok", 
        "records_processed": len(rows),
        "db_path": str(repo_root / DB_CORE_PATH)
    }
