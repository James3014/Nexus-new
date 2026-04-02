from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import json
import hashlib
import gc
import logging
from dataclasses import dataclass
from datetime import datetime
from nexus.core.memory_coordinator import MemoryCoordinator
from nexus.services.memory_repository import MemoryRepository
from nexus.core.errors import NexusError

logger = logging.getLogger(__name__)

try:
    import redis
except ModuleNotFoundError:  # pragma: no cover - optional backend
    redis = None

@dataclass
class FaultLesson:
    """故障教訓的參數封裝。"""
    fault_hash: str
    error_type: str
    diagnosis_kind: str
    lesson: str
    repair_patch: str
    audit_pass_rate: float
    metadata: Optional[Dict[str, Any]] = None

class MemoryService:
    """
    🧠 Nexus Memory Service
    負責聚合與快取跨階段的背景知識與歷史記錄。
    重構版：將 LanceDB 邏輯抽離至 MemoryRepository。
    """
    def __init__(self, project_root: str, run_dir: Optional[str] = None):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else None
        self.db_path = self.project_root / ".nexus" / "knowledge" / "lancedb"
        self.fault_lessons_jsonl = self.project_root / ".nexus" / "knowledge" / "fault_lessons.jsonl"
        self.policy_memory_jsonl = self.project_root / ".nexus" / "knowledge" / "policy_memory.jsonl"
        self.coordinator = MemoryCoordinator()
        self.repo = MemoryRepository(self.db_path)
        
        try:
            if redis is None:
                raise ModuleNotFoundError("redis")
            self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis.ping()
            self.redis_available = True
        except (ConnectionError, TimeoutError, ModuleNotFoundError, Exception) as e:
            logger.warning(f"Redis init failed, falling back to local: {e}")
            self.redis_available = False
        
        self._auto_init_tables()

    def _auto_init_tables(self):
        """🛡️ Auto-Init: Ensure core tables exist."""
        try:
            # Policy Table auto-init from JSONL
            if self.policy_memory_jsonl.exists():
                data = self._load_policy_memory_rows()
                if data:
                    self.repo.ensure_table("policy", initial_data=data, fts_column="condition")
            
            # Fault Lessons Table auto-init from JSONL
            if self.fault_lessons_jsonl.exists():
                fault_data = []
                try:
                    with open(self.fault_lessons_jsonl, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                fault_data.append(json.loads(line.strip()))
                    if fault_data:
                        self.repo.ensure_table("fault_lessons", initial_data=fault_data)
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to load fault lessons during init: {e}")
        except Exception as e:
            logger.error(f"MemoryService auto-init failed: {e}")

    def semantic_search(self, query: str, table_name: str = "policy", limit: int = 3) -> List[Dict]:
        """🧬 語義檢索實作 (M2-Active)"""
        try:
            results = self.repo.search_fts(
                table_name=table_name,
                query=query,
                limit=limit,
                fallback_columns=["condition", "action"]
            )
            
            if results.empty:
                return []

            reminders = []
            for _, row in results.iterrows():
                score = float(getattr(row, "_score", 1.0))
                confidence = min(1.0, score / 1.0) 
                reminders.append({
                    "id": str(row.get("rule_id", "unknown")),
                    "content": str(row.get("action", row.get("condition", "No Content"))),
                    "relevance": round(confidence, 2),
                    "source": "lancedb-fts" if "_score" in row.index else "lancedb-fallback"
                })
            return reminders
        except Exception as e:
            logger.error(f"Semantic search failed on {table_name}: {e}")
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
            success = episode.get("success", False)
            policy_ids = episode.get("policy_hit_ids", [])
            
            if not policy_ids:
                return
                
            df = self.repo.get_all_rows("policy")
            if df.empty:
                return

            # 簡單權重更新：成功 +0.05, 失敗 -0.15 (挫折偏好)
            penalty = 0.05 if success else -0.15
            updated = False
            for pid in policy_ids:
                if pid in df['rule_id'].values:
                    idx = df[df['rule_id'] == pid].index
                    df.loc[idx, 'confidence'] = (df.loc[idx, 'confidence'] + penalty).clip(0.0, 1.0)
                    updated = True
            
            if updated:
                self.repo.update_table("policy", df)
                logger.info(f"M3 Learning applied: {len(policy_ids)} policies updated. (Success: {success})")
        except Exception as e:
            logger.error(f"M3 Ingestion failed: {e}")

    def aggregate_memory(self, query: Optional[str] = None) -> Dict[str, Any]:
        """聚合全域與專案級記憶來源。"""
        if query:
            reminders = self.semantic_search(query)
        else:
            reminders = self.semantic_search("general_nexus_task")[:3]
        
        if not reminders:
            reminders = self._load_local_crystal_lessons(limit=3)

        result = {
            'reminders': reminders, 
            'total_sources': 3,
            'timestamp': datetime.now().isoformat()
        }
        
        dest_path = (self.run_dir if self.run_dir else self.project_root) / 'reminders.json'
        
        try:
            with open(dest_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning(f"Failed to write reminders.json: {e}")
            
        gc.collect()
        return result

    def lookup_fault_lessons(self, fault_hash: str, limit: int = 3) -> List[Dict[str, Any]]:
        if not fault_hash:
            return []
        
        # 1) Prefer LanceDB table when available.
        reminders = self._lookup_fault_lessons_from_db(fault_hash, limit)
        if reminders:
            return reminders

        # 2) Fallback to local JSONL.
        return self._lookup_fault_lessons_from_jsonl(fault_hash, limit)

    def _lookup_fault_lessons_from_db(self, fault_hash: str, limit: int) -> List[Dict[str, Any]]:
        try:
            df = self.repo.get_all_rows("fault_lessons")
            if df.empty or "fault_hash" not in df.columns:
                return []
                
            hits = df[df["fault_hash"] == fault_hash].head(limit)
            return [
                {
                    "id": str(row.get("fault_hash", "unknown")),
                    "content": {
                        "lesson": row.get("lesson", ""),
                        "repair_patch": row.get("repair_patch", ""),
                    },
                    "relevance": float(row.get("audit_pass_rate", 0.0)),
                    "source": "lancedb-fault-lessons",
                }
                for _, row in hits.iterrows()
            ]
        except Exception as e:
            logger.debug(f"LanceDB fault lookup failed: {e}")
            return []

    def _lookup_fault_lessons_from_jsonl(self, fault_hash: str, limit: int) -> List[Dict[str, Any]]:
        if not self.fault_lessons_jsonl.exists():
            return []
            
        reminders: List[Dict[str, Any]] = []
        try:
            with open(self.fault_lessons_jsonl, "r", encoding="utf-8") as handle:
                for idx, line in enumerate(handle):
                    payload = json.loads(line.strip())
                    if payload.get("fault_hash") == fault_hash:
                        reminders.append({
                            "id": f"fault-{idx}",
                            "content": {
                                "lesson": payload.get("lesson", ""),
                                "repair_patch": payload.get("repair_patch", ""),
                            },
                            "relevance": float(payload.get("audit_pass_rate", 0.0)),
                            "source": "jsonl-fault-lessons",
                        })
                    if len(reminders) >= limit:
                        break
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return reminders

    def record_fault_lesson(self, lesson: FaultLesson) -> None:
        """📓 紀錄修復教訓至長效記憶體。"""
        if not lesson.fault_hash:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "fault_hash": lesson.fault_hash,
            "error_type": lesson.error_type,
            "diagnosis_kind": lesson.diagnosis_kind,
            "lesson": lesson.lesson,
            "repair_patch": lesson.repair_patch,
            "audit_pass_rate": float(lesson.audit_pass_rate),
            "metadata": lesson.metadata or {},
        }

        # Always append JSONL as durable fallback.
        try:
            self.fault_lessons_jsonl.parent.mkdir(parents=True, exist_ok=True)
            with open(self.fault_lessons_jsonl, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error(f"Failed to write fault lesson to JSONL: {e}")

        # Best-effort sync into LanceDB.
        try:
            self.repo.add_rows("fault_lessons", [entry])
            if lesson.audit_pass_rate >= 0.8:
                if self.redis_available:
                    self.redis.set(f"nexus:lesson:{lesson.fault_hash}", "ok", ex=3600)
        except Exception as e:
            logger.warning(f"Failed to record fault lesson in LanceDB: {e}")

    def sync_route_phase_weights(
        self,
        weights: Dict[str, float],
        cycle_status: str = "",
        fault_hash: str = "",
    ) -> None:
        if not isinstance(weights, dict) or not weights:
            return

        normalized = self._normalize_phase_weights(weights)
        if not normalized:
            return

        now = datetime.now().isoformat()
        existing = self._load_policy_memory_rows()
        
        # Filter out old route weight rows.
        kept = [
            row for row in existing
            if not str(row.get("rule_id", "")).startswith("ROUTE-WEIGHT-")
        ]

        for phase, weight in normalized.items():
            kept.append(self._build_route_weight_policy(phase, weight, now, cycle_status, fault_hash))

        self._write_policy_memory_rows(kept)

    def _normalize_phase_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        normalized: Dict[str, float] = {}
        for phase, raw in weights.items():
            phase_key = str(phase).upper()
            if phase_key in {"P", "X", "D", "R", "A", "C"}:
                normalized[phase_key] = max(-100.0, min(100.0, float(raw or 0.0)))
        return normalized

    def _build_route_weight_policy(self, phase: str, weight: float, timestamp: str, cycle_status: str, fault_hash: str) -> Dict[str, Any]:
        # Governance Enforcements (Hardened v17.1)
        confidence = round((weight + 100.0) / 200.0, 4)
        drift = round(max(0.0, 50.0 - abs(weight)), 2)
        return {
            "rule_id": f"ROUTE-WEIGHT-{phase}",
            "condition": f"self_heal_route_phase={phase}",
            "action": f"prioritize repair_phase_{phase}",
            "phase": phase,  # Direct field for governance audit
            "confidence": confidence,
            "semantic_drift": drift,
            "source": "self_heal.route_weight",
            "governance_level": "adaptive",
            "tags": ["self_heal_route", "learning_generated"],
            "zero_decay": False,
            "immutable": False,
            "created_at": timestamp,
            "updated_at": timestamp,  # Align with audit metadata requirements
            "last_access": timestamp,
            "last_used_at": timestamp,
            "metadata": {
                "cycle_status": str(cycle_status),
                "fault_hash": str(fault_hash or ""),
                "weight_raw": float(weight)
            }
        }

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
        except OSError as e:
            logger.error(f"Failed to load policy memory rows: {e}")
            return []
        return rows

    def _write_policy_memory_rows(self, rows: List[Dict[str, Any]]) -> None:
        try:
            self.policy_memory_jsonl.parent.mkdir(parents=True, exist_ok=True)
            with self.coordinator.lock(self.policy_memory_jsonl):
                with open(self.policy_memory_jsonl, "w", encoding="utf-8") as handle:
                    for row in rows:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error(f"Failed to write policy memory rows: {e}")

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
