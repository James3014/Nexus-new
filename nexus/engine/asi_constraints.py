from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
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
