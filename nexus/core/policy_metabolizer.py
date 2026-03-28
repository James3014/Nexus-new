from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_coordinator import MemoryCoordinator


@dataclass(frozen=True)
class MetabolizeResult:
    scanned: int
    archived: int
    active: int
    memory_health_current: float
    negative_transfer_rate: float
    snapshot_path: Optional[Path]
    archive_path: Path


class PolicyMetabolizer:
    """
    Semantic decay processor for policy memory.
    - Snapshot before mutation (lobotomy switch).
    - Zero-decay protection for Sir directives.
    - Archive stale policies by decay score.
    """

    def __init__(
        self,
        project_root: str,
        coordinator: MemoryCoordinator | None = None,
        decay_time_lambda: float = 1.2,
        decay_semantic_lambda: float = 0.8,
        archive_threshold: float = 80.0,
    ):
        self.root = Path(project_root)
        self.coordinator = coordinator or MemoryCoordinator()
        self.policy_file = self.root / ".nexus" / "knowledge" / "policy_memory.jsonl"
        self.archive_file = self.root / ".nexus" / "knowledge" / "archive" / "policy_memory_archive.jsonl"
        self.snapshot_dir = self.root / ".nexus" / "knowledge" / "snapshots"
        self.decay_time_lambda = float(decay_time_lambda)
        self.decay_semantic_lambda = float(decay_semantic_lambda)
        self.archive_threshold = float(archive_threshold)

    def metabolize(self, force: bool = False) -> MetabolizeResult:
        if not self.policy_file.exists():
            return MetabolizeResult(
                scanned=0,
                archived=0,
                active=0,
                memory_health_current=100.0,
                negative_transfer_rate=0.0,
                snapshot_path=None,
                archive_path=self.archive_file,
            )

        with self.coordinator.lock(self.policy_file):
            records = self._read_jsonl(self.policy_file)
            if not force and not records:
                return MetabolizeResult(
                    scanned=0,
                    archived=0,
                    active=0,
                    memory_health_current=100.0,
                    negative_transfer_rate=0.0,
                    snapshot_path=None,
                    archive_path=self.archive_file,
                )

            snapshot_path = self._snapshot_policy_file()
            kept: List[Dict[str, Any]] = []
            archived: List[Dict[str, Any]] = []

            for record in records:
                if self._is_zero_decay(record):
                    kept.append(record)
                    continue
                decay = self._decay_score(record)
                if decay > self.archive_threshold:
                    out = dict(record)
                    out["archived_at"] = datetime.now(timezone.utc).isoformat()
                    out["decay_score"] = round(decay, 2)
                    archived.append(out)
                else:
                    kept.append(record)

            self._write_jsonl(self.policy_file, kept)
            if archived:
                self.archive_file.parent.mkdir(parents=True, exist_ok=True)
                with self.archive_file.open("a", encoding="utf-8") as handle:
                    for row in archived:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")

            scanned = len(records)
            archived_count = len(archived)
            active_count = len(kept)
            memory_health = 100.0 if scanned == 0 else max(0.0, (active_count / scanned) * 100.0)
            ntr = 0.0 if scanned == 0 else (archived_count / scanned) * 100.0
            return MetabolizeResult(
                scanned=scanned,
                archived=archived_count,
                active=active_count,
                memory_health_current=round(memory_health, 2),
                negative_transfer_rate=round(ntr, 2),
                snapshot_path=snapshot_path,
                archive_path=self.archive_file,
            )

    def _snapshot_policy_file(self) -> Path:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = self.snapshot_dir / f"policy_memory.{stamp}.jsonl"
        shutil.copy2(self.policy_file, path)
        return path

    @staticmethod
    def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
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
        return rows

    @staticmethod
    def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _decay_score(self, record: Dict[str, Any]) -> float:
        age_days = self._age_days(record)
        semantic_drift = float(record.get("semantic_drift", 0.0) or 0.0)
        score = (self.decay_time_lambda * age_days) + (self.decay_semantic_lambda * semantic_drift)
        confidence = record.get("confidence")
        try:
            confidence_f = float(confidence)
            score += max(0.0, (0.4 - confidence_f) * 50.0)
        except (TypeError, ValueError):
            pass
        return min(100.0, max(0.0, score))

    @staticmethod
    def _parse_time(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            text = text.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _age_days(self, record: Dict[str, Any]) -> float:
        last_access = self._parse_time(record.get("last_access"))
        last_used = self._parse_time(record.get("last_used_at"))
        created = self._parse_time(record.get("created_at"))
        anchor = last_access or last_used or created
        if not anchor:
            return 0.0
        delta = datetime.now(timezone.utc) - anchor
        return max(0.0, delta.total_seconds() / 86400.0)

    @staticmethod
    def _is_zero_decay(record: Dict[str, Any]) -> bool:
        if bool(record.get("zero_decay")) or bool(record.get("immutable")):
            return True
        source = str(record.get("source", "")).lower()
        governance = str(record.get("governance_level", "")).lower()
        if source in {"sir", "sir_directive", "commander"}:
            return True
        if governance in {"sir", "constitutional"}:
            return True
        tags = record.get("tags") or []
        if isinstance(tags, list):
            normalized = {str(tag).lower() for tag in tags}
            if "sir_directive" in normalized or "zero_decay" in normalized:
                return True
        return False
