from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any


class ASIConstraintExtractor:
    """Crystallize repeated ASI failures into cross-task constraints."""

    def __init__(self, *, min_failures: int = 2) -> None:
        self.min_failures = max(2, int(min_failures or 2))

    def extract(self, records: list[Any], *, task_id: str = "") -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw in records or []:
            record = self._mapping(raw)
            if str(record.get("status", "")).lower() != "discard":
                continue
            family = str(record.get("family") or "").strip()
            if not family:
                continue
            grouped[family].append(record)

        constraints: list[dict[str, Any]] = []
        for family, failures in sorted(grouped.items()):
            if len(failures) < self.min_failures:
                continue
            reasons = [str(item.get("rollback_reason") or item.get("evidence") or "").strip() for item in failures]
            reasons = [item for item in reasons if item]
            evidence_refs = [str(item.get("evidence") or "").strip() for item in failures if str(item.get("evidence") or "").strip()]
            confidence = min(0.95, 0.55 + 0.1 * len(failures))
            constraints.append(
                {
                    "schema": "nexus_asi_constraint_v1",
                    "blocked_pattern": family,
                    "preferred_pattern": "change_family_or_architecture_seam",
                    "failure_signature": self._common_reason(reasons),
                    "evidence_refs": evidence_refs,
                    "confidence": round(confidence, 4),
                    "ttl": "30d",
                    "source_task_ids": [task_id] if task_id else [],
                    "source_run_ids": [item.get("run_id") for item in failures if item.get("run_id") is not None],
                }
            )

        return {
            "schema": "nexus_asi_constraints_v1",
            "constraints_count": len(constraints),
            "constraints": constraints,
        }

    def _mapping(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        if is_dataclass(raw):
            return asdict(raw)
        return {}

    def _common_reason(self, reasons: list[str]) -> str:
        if not reasons:
            return "repeated_discard"
        counts: dict[str, int] = {}
        for reason in reasons:
            counts[reason] = counts.get(reason, 0) + 1
        return max(counts, key=lambda item: (counts[item], len(item)))


class ASIConstraintStore:
    """Small JSONL store for cross-task ASI constraints."""

    def __init__(self, repo_root: Path, *, rel_path: str = ".nexus/reports/asi/global_constraints.jsonl") -> None:
        self.repo_root = Path(repo_root)
        self.path = self.repo_root / rel_path

    def append_constraints(self, constraints: list[dict[str, Any]]) -> str:
        rows = [dict(item) for item in constraints or [] if isinstance(item, dict)]
        if not rows:
            return str(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = {(row.get("blocked_pattern"), row.get("failure_signature")) for row in self.load_constraints()}
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                key = (row.get("blocked_pattern"), row.get("failure_signature"))
                if key in existing:
                    continue
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                existing.add(key)
        return str(self.path)

    def load_constraints(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def match(self, task_desc: str, *, limit: int = 5) -> list[dict[str, Any]]:
        text = task_desc.lower()
        matches: list[dict[str, Any]] = []
        for row in self.load_constraints():
            blocked = str(row.get("blocked_pattern") or "").lower()
            signature = str(row.get("failure_signature") or "").lower()
            tokens = [token for token in f"{blocked} {signature}".replace(":", " ").replace("_", " ").split() if len(token) >= 4]
            if any(token in text for token in tokens):
                matches.append(row)
        return matches[: max(1, int(limit or 5))]
