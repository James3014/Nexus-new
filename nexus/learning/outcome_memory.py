from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


OUTCOME_MEMORY_SCHEMA = "nexus_outcome_memory_episode.v1"
DYNAMIC_LEARNING_POLICY_SCHEMA = "nexus_dynamic_learning_policy.v1"


@dataclass(frozen=True)
class EpisodeOutcomeRecord:
    task_id: str
    task_type: str
    task_desc_hash: str
    solved: bool
    wall_duration_sec: float
    total_tokens_used: int
    trust_mismatch: bool
    receipts: list[dict[str, Any]] = field(default_factory=list)
    ab_lift_value: float = 0.0
    created_at: str = ""
    schema_version: str = OUTCOME_MEMORY_SCHEMA

    @classmethod
    def from_task(
        cls,
        *,
        task_id: str,
        task_type: str,
        task_desc: str,
        solved: bool,
        wall_duration_sec: float,
        total_tokens_used: int,
        trust_mismatch: bool,
        receipts: Iterable[Mapping[str, Any]] = (),
        ab_lift_value: float = 0.0,
        created_at: str | None = None,
    ) -> "EpisodeOutcomeRecord":
        return cls(
            task_id=str(task_id or "unknown"),
            task_type=str(task_type or "unknown"),
            task_desc_hash=_stable_hash(task_desc or ""),
            solved=bool(solved),
            wall_duration_sec=max(0.0, float(wall_duration_sec or 0.0)),
            total_tokens_used=max(0, int(total_tokens_used or 0)),
            trust_mismatch=bool(trust_mismatch),
            receipts=[dict(receipt) for receipt in receipts if isinstance(receipt, Mapping)],
            ab_lift_value=float(ab_lift_value or 0.0),
            created_at=created_at or datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_desc_hash": self.task_desc_hash,
            "solved": self.solved,
            "wall_duration_sec": self.wall_duration_sec,
            "total_tokens_used": self.total_tokens_used,
            "trust_mismatch": self.trust_mismatch,
            "receipts": [dict(receipt) for receipt in self.receipts],
            "ab_lift_value": self.ab_lift_value,
            "created_at": self.created_at,
        }


class OutcomeMemoryManager:
    STORAGE_PATH = Path(".nexus") / "memory" / "outcome_history.jsonl"
    POLICY_PATH = Path(".nexus") / "memory" / "dynamic_learning_policy.json"
    RECENT_LIMIT = 20
    MIN_RECENCY_WEIGHT = 0.35

    @classmethod
    async def save_episode_and_tune(
        cls,
        record: EpisodeOutcomeRecord,
        *,
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(cls.save_episode_and_tune_sync, record, project_root=project_root)

    @classmethod
    def save_episode_and_tune_sync(
        cls,
        record: EpisodeOutcomeRecord,
        *,
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        storage_path = _resolve(project_root, cls.STORAGE_PATH)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with storage_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        policy = cls.run_dynamic_autotune_sync(project_root=project_root)
        return {
            "schema_version": "nexus_outcome_memory_write.v1",
            "status": "PASS",
            "storage_path": str(cls.STORAGE_PATH),
            "policy_path": str(cls.POLICY_PATH),
            "policy": policy,
        }

    @classmethod
    def run_dynamic_autotune_sync(cls, *, project_root: Path | None = None) -> dict[str, Any]:
        records = cls.load_recent_records(project_root=project_root, limit=cls.RECENT_LIMIT)
        eligible_records = [record for record in records if not bool(record.get("trust_mismatch", False))]
        promoted_scores: dict[str, float] = {}
        penalized_scores: dict[str, float] = {}
        weights = _recency_weights(len(eligible_records), minimum=cls.MIN_RECENCY_WEIGHT)
        for record, weight in zip(eligible_records, weights, strict=False):
            solved = bool(record.get("solved", False))
            for receipt in record.get("receipts", []) or []:
                if not isinstance(receipt, Mapping):
                    continue
                name = str(receipt.get("name") or "").strip()
                if not name:
                    continue
                if _receipt_promotes(record_solved=solved, receipt=receipt):
                    promoted_scores[name] = promoted_scores.get(name, 0.0) + weight
                if _receipt_penalizes(record_solved=solved, receipt=receipt):
                    penalized_scores[name] = penalized_scores.get(name, 0.0) + weight
        capability_scores = {
            name: round(promoted_scores.get(name, 0.0) - penalized_scores.get(name, 0.0), 4)
            for name in sorted(set(promoted_scores) | set(penalized_scores))
        }
        resolved_promoted = [name for name, score in capability_scores.items() if score > 0]
        resolved_penalized = [name for name, score in capability_scores.items() if score < 0]
        policy = {
            "schema_version": DYNAMIC_LEARNING_POLICY_SCHEMA,
            "status": "PASS",
            "source_experiences_count": len(records),
            "eligible_experiences_count": len(eligible_records),
            "source_experiences": [str(record.get("task_id") or "") for record in records if record.get("task_id")],
            "excluded_experiences": [
                {
                    "task_id": str(record.get("task_id") or ""),
                    "reason": "trust_mismatch",
                }
                for record in records
                if bool(record.get("trust_mismatch", False))
            ],
            "aging_window": {
                "recent_limit": cls.RECENT_LIMIT,
                "minimum_weight": cls.MIN_RECENCY_WEIGHT,
                "records_used": len(eligible_records),
            },
            "capability_scores": capability_scores,
            "promoted_capabilities": resolved_promoted,
            "penalized_capabilities": resolved_penalized,
            "enforce_penalties": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        policy_path = _resolve(project_root, cls.POLICY_PATH)
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(policy, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return policy

    @classmethod
    def append_worker_write(cls, receipt: dict[str, Any], *, project_root: Path | None = None) -> dict[str, Any]:
        if "task_id" not in receipt:
            raise ValueError("Missing required field: task_id")
        if "worker_name" not in receipt:
            raise ValueError("Missing required field: worker_name")
        storage_path = _resolve(project_root, cls.STORAGE_PATH)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with storage_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
        return {
            "status": "PASS",
            "storage_path": str(cls.STORAGE_PATH),
        }

    @classmethod
    def load_recent_records(cls, *, project_root: Path | None = None, limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
        storage_path = _resolve(project_root, cls.STORAGE_PATH)
        if not storage_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in storage_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows[-max(1, int(limit or 1)) :]


def _receipt_promotes(*, record_solved: bool, receipt: Mapping[str, Any]) -> bool:
    return bool(
        record_solved
        and receipt.get("public_claim_safe")
        and receipt.get("selected")
        and receipt.get("invoked")
        and receipt.get("evidence_present")
        and receipt.get("gate_passed")
        and receipt.get("outcome_contributed")
    )


def _receipt_penalizes(*, record_solved: bool, receipt: Mapping[str, Any]) -> bool:
    selected = bool(receipt.get("selected"))
    if not selected:
        return False
    if not receipt.get("invoked"):
        return True
    if receipt.get("evidence_present") and not receipt.get("gate_passed"):
        return True
    return bool(not record_solved and not receipt.get("gate_passed"))


def _recency_weights(count: int, *, minimum: float) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    floor = max(0.0, min(1.0, float(minimum)))
    step = (1.0 - floor) / float(count - 1)
    return [round(floor + (step * index), 4) for index in range(count)]


def _resolve(project_root: Path | None, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (project_root or Path.cwd()) / path


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
