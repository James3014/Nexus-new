import pandas as pd
import json
import hashlib
import gc
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from nexus.core.memory_coordinator import MemoryCoordinator

try:
    import lancedb
except ModuleNotFoundError:  # pragma: no cover - optional backend
    lancedb = None

try:
    import redis
except ModuleNotFoundError:  # pragma: no cover - optional backend
    redis = None

class MemoryService:
    """
    🧠 Nexus Memory Service
    負責聚合與快取跨階段的背景知識與歷史記錄。
    已從 legacy scripts/logmemory.py 重構為原生物件。
    """
    def __init__(self, project_root: str, run_dir: Optional[str] = None):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else None
        self.db_path = self.project_root / ".nexus" / "knowledge" / "lancedb"
        self.fault_lessons_jsonl = self.project_root / ".nexus" / "knowledge" / "fault_lessons.jsonl"
        self.policy_memory_jsonl = self.project_root / ".nexus" / "knowledge" / "policy_memory.jsonl"
        self.coordinator = MemoryCoordinator()
        self._db = None
        try:
            if redis is None:
                raise ModuleNotFoundError("redis")
            self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis.ping()
            self.redis_available = True
        except (ConnectionError, TimeoutError, ModuleNotFoundError) as e:
            print(f"⚠️ [MemoryService] Redis init failed: {e}")
            self.redis_available = False

    def _get_db(self):
        if self._db is None:
            if lancedb is None:
                return None
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.db_path)
            
            # 🛡️ Auto-Init: 如果 policy 表不存在，從 JSONL 匯入
            table_names = self._db.table_names() if self._db else []
            if "policy" not in table_names:
                policy_jsonl = self.project_root / ".nexus" / "knowledge" / "policy_memory.jsonl"
                if policy_jsonl.exists():
                    try:
                        data = []
                        with open(policy_jsonl, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    data.append(json.loads(line.strip()))
                        if data:
                            tbl = self._db.create_table("policy", data=data)
                            # 🧪 v9 M2: 建立 FTS 索引 (限制: 單一欄位)
                            tbl.create_fts_index("condition", replace=True)
                            print(f"✅ [MemoryService] Initialized 'policy' table with FTS index on 'condition'")
                    except (OSError, ValueError, RuntimeError) as e:
                        print(f"⚠️ [MemoryService] Auto-init failed: {e}")
        return self._db

    def semantic_search(self, query: str, table_name: str = "policy", limit: int = 3) -> List[Dict]:
        """🧬 語義檢索實作 (M2-Active)"""
        try:
            db = self._get_db()
            if not db:
                return []
            if table_name not in db.table_names():
                return []
            
            table = db.open_table(table_name)
            try:
                # 💡 v9: 優先使用 FTS (Full Text Search)
                results = table.search(query, query_type="fts").limit(limit).to_pandas()
            except (ValueError, RuntimeError, KeyError) as e:
                # 🛡️ Fallback: 如果 FTS 索引尚未就緒或失敗，使用 Pandas 關鍵字過濾
                print(f"⚠️ [MemorySearch] FTS failed, using pandas fallback: {e}")
                df = table.to_pandas()
                # 簡單關鍵字過濾
                q = str(query).lower()
                results = df[
                    df['condition'].str.contains(q, case=False, na=False) | 
                    df['action'].str.contains(q, case=False, na=False)
                ].head(limit)

            # 轉換為 Nexus 格式
            reminders = []
            for _, row in results.iterrows():
                # FTS 下使用得分 (_score) 作為相關性參考
                score = float(getattr(row, "_score", 1.0))
                confidence = min(1.0, score / 1.0) # Fallback 情況下設較高 confidence 
                reminders.append({
                    "id": str(row.get("rule_id", "unknown")),
                    "content": str(row.get("action", row.get("condition", "No Content"))),
                    "relevance": round(confidence, 2),
                    "source": "lancedb-fts" if "_score" in row.index else "lancedb-fallback"
                })
            return reminders
        except (OSError, RuntimeError) as e:
            print(f"⚠️ [MemorySearch] Critical failure: {e}")
            return []

    def _load_local_crystal_lessons(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Fallback lessons from local JSONL when vector DB is unavailable."""
        candidates = [
            self.project_root / "obsidian" / "crystal_lessons.jsonl",
            self.project_root / ".nexus" / "knowledge" / "crystal_lessons.jsonl",
        ]
        reminders: List[Dict[str, Any]] = []
        for path in candidates:
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    for idx, line in enumerate(handle):
                        line = line.strip()
                        if not line:
                            continue
                        payload = json.loads(line)
                        reminders.append(
                            {
                                "id": f"local-{path.stem}-{idx}",
                                "content": payload,
                                "relevance": 0.8,
                                "source": "local-crystal-jsonl",
                            }
                        )
                        if len(reminders) >= limit:
                            return reminders
            except (ValueError, KeyError, OSError, json.JSONDecodeError):
                continue
        return reminders

    def ingest_episode(self, episode: Dict[str, Any]):
        """🧪 Phase M3: 學習閉環入口。根據任務結果更新 Policy 權重。"""
        try:
            db = self._get_db()
            if not db:
                return
            
            success = episode.get("success", False)
            policy_ids = episode.get("policy_hit_ids", [])
            
            if not policy_ids:
                return
                
            # 更新 Policy Confidence
            if "policy" in db.table_names():
                table = db.open_table("policy")
                df = table.to_pandas()
                
                # 簡單權重更新：成功 +0.05, 失敗 -0.15 (挫折偏好)
                penalty = 0.05 if success else -0.15
                
                updated = False
                for pid in policy_ids:
                    if pid in df['rule_id'].values:
                        idx = df[df['rule_id'] == pid].index
                        df.loc[idx, 'confidence'] = (df.loc[idx, 'confidence'] + penalty).clip(0.0, 1.0)
                        updated = True
                
                if updated:
                    # 覆寫表格 (M3 規模較小，全量覆寫可接受)
                    db.create_table("policy", data=df, mode="overwrite")
                    print(f"🧠 [MemoryService] M3 Learning applied: {len(policy_ids)} policies updated. (Success: {success})")
                    
                    # 🛡️ 汰弱留強: 如果信心度低於 0.3，標註為 deprecated
                    deprecated_count = len(df[df['confidence'] < 0.3])
                    if deprecated_count > 0:
                        print(f"⚠️ [MemoryService] {deprecated_count} policies are now deprecated due to poor performance.")
        except (ValueError, OSError, RuntimeError) as e:
            print(f"⚠️ [MemoryService] M3 Ingestion failed: {e}")

    def aggregate_memory(self, query: Optional[str] = None) -> Dict[str, Any]:
        """聚合全域與專案級記憶來源。"""
        # 🧪 v9 M2: 優先使用語義檢索
        if query:
            reminders = self.semantic_search(query)
        else:
            # Fallback to random/recent if no query provided
            reminders = self.semantic_search("general_nexus_task")[:3]
        if not reminders:
            reminders = self._load_local_crystal_lessons(limit=3)

        result = {
            'reminders': reminders, 
            'total_sources': 3, # LanceDB + Global
            'timestamp': datetime.now().isoformat()
        }
        
        # 持久化 reminders.json 以供其他工具/Shell 讀取 (後向相容)
        if self.run_dir:
            dest_path = self.run_dir / 'reminders.json'
        else:
            dest_path = self.project_root / 'reminders.json'
        
        with open(dest_path, 'w', encoding='utf-8') as f:
            import json
            json.dump(result, f, ensure_ascii=False, indent=2)
            
        import gc
        gc.collect()
        return result

    def lookup_fault_lessons(self, fault_hash: str, limit: int = 3) -> List[Dict[str, Any]]:
        if not fault_hash:
            return []
        # 1) Prefer LanceDB table when available.
        db = self._get_db()
        if db and "fault_lessons" in db.table_names():
            try:
                table = db.open_table("fault_lessons")
                df = table.to_pandas()
                if "fault_hash" in df.columns:
                    hits = df[df["fault_hash"] == fault_hash].head(limit)
                    reminders: List[Dict[str, Any]] = []
                    for _, row in hits.iterrows():
                        reminders.append(
                            {
                                "id": str(row.get("fault_hash", "unknown")),
                                "content": {
                                    "lesson": row.get("lesson", ""),
                                    "repair_patch": row.get("repair_patch", ""),
                                },
                                "relevance": float(row.get("audit_pass_rate", 0.0)),
                                "source": "lancedb-fault-lessons",
                            }
                        )
                    if reminders:
                        return reminders
            except (RuntimeError, ValueError, KeyError):
                pass

        # 2) Fallback to local JSONL.
        if not self.fault_lessons_jsonl.exists():
            return []
        reminders: List[Dict[str, Any]] = []
        try:
            with open(self.fault_lessons_jsonl, "r", encoding="utf-8") as handle:
                for idx, line in enumerate(handle):
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    if payload.get("fault_hash") != fault_hash:
                        continue
                    reminders.append(
                        {
                            "id": f"fault-{idx}",
                            "content": {
                                "lesson": payload.get("lesson", ""),
                                "repair_patch": payload.get("repair_patch", ""),
                            },
                            "relevance": float(payload.get("audit_pass_rate", 0.0)),
                            "source": "jsonl-fault-lessons",
                        }
                    )
                    if len(reminders) >= limit:
                        break
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        return reminders

    def record_fault_lesson(
        self,
        fault_hash: str,
        error_type: str,
        diagnosis_kind: str,
        lesson: str,
        repair_patch: str,
        audit_pass_rate: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not fault_hash:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "fault_hash": fault_hash,
            "error_type": error_type,
            "diagnosis_kind": diagnosis_kind,
            "lesson": lesson,
            "repair_patch": repair_patch,
            "audit_pass_rate": float(audit_pass_rate),
            "metadata": metadata or {},
        }

        # Always append JSONL as durable fallback.
        self.fault_lessons_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(self.fault_lessons_jsonl, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Best-effort sync into LanceDB.
        db = self._get_db()
        if not db:
            return
        try:
            if "fault_lessons" not in db.table_names():
                db.create_table("fault_lessons", data=[entry])
                return
            table = db.open_table("fault_lessons")
            table.add([entry])
        except (RuntimeError, ValueError):
            pass

    def sync_route_phase_weights(
        self,
        weights: Dict[str, float],
        cycle_status: str = "",
        fault_hash: str = "",
    ) -> None:
        if not isinstance(weights, dict) or not weights:
            return

        normalized: Dict[str, float] = {}
        for phase, raw in weights.items():
            phase_key = str(phase).upper()
            if phase_key not in {"P", "X", "D", "R", "A", "C"}:
                continue
            normalized[phase_key] = max(-100.0, min(100.0, float(raw or 0.0)))
        if not normalized:
            return

        now = datetime.now().isoformat()
        existing = self._load_policy_memory_rows()
        kept = [
            row
            for row in existing
            if str(row.get("rule_id", "")).upper() not in {
                f"ROUTE-WEIGHT-{phase}" for phase in normalized.keys()
            }
        ]

        for phase, weight in normalized.items():
            confidence = round((weight + 100.0) / 200.0, 4)
            drift = round(max(0.0, 50.0 - abs(weight)), 2)
            kept.append(
                {
                    "rule_id": f"ROUTE-WEIGHT-{phase}",
                    "condition": f"self_heal_route_phase={phase}",
                    "action": f"prioritize repair_phase_{phase}",
                    "confidence": confidence,
                    "semantic_drift": drift,
                    "source": "self_heal_route_weight",
                    "governance_level": "adaptive",
                    "tags": ["self_heal_route", "learning_generated"],
                    "zero_decay": False,
                    "immutable": False,
                    "created_at": now,
                    "last_access": now,
                    "last_used_at": now,
                    "metadata": {
                        "phase": phase,
                        "route_weight": round(weight, 2),
                        "cycle_status": str(cycle_status),
                        "fault_hash": str(fault_hash or ""),
                    },
                }
            )

        self._write_policy_memory_rows(kept)

    def _load_policy_memory_rows(self) -> List[Dict[str, Any]]:
        if not self.policy_memory_jsonl.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            with open(self.policy_memory_jsonl, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        rows.append(payload)
        except Exception:
            return []
        return rows

    def _write_policy_memory_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.policy_memory_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with self.coordinator.lock(self.policy_memory_jsonl):
            with open(self.policy_memory_jsonl, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def cached_search(self, key: str, ttl: int = 1800) -> Dict[str, Any]:
        """雙層快取搜尋。"""
        if self.redis_available:
            hot_key = f"hot:{hashlib.md5(key.encode()).hexdigest()}"
            try:
                cached = self.redis.get(hot_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
        
        result = self.aggregate_memory()
        
        if self.redis_available:
            try:
                self.redis.setex(f"hot:{hashlib.md5(key.encode()).hexdigest()}", ttl, json.dumps(result))
            except Exception:
                pass
        return result
