from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .protocols import LearnContextProtocol


class SourceRegistryService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    def load_source_registry(self) -> list[dict[str, Any]]:
        if not self.ctx.sources_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.ctx.sources_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def write_source_registry(self, rows: list[dict[str, Any]]) -> None:
        self.ctx.sources_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        self.ctx.sources_path.write_text((content + "\n") if content else "", encoding="utf-8")

    def sync_registry_after_ingest(
        self,
        *,
        source: str,
        source_file: str | None,
        topic: str,
        claims_count: int,
    ) -> None:
        rows = self.load_source_registry()
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for row in rows:
            if (
                str(row.get("topic", "")) == str(topic or row.get("topic", ""))
                and str(row.get("source", "")) == str(source)
                and str(row.get("source_file", "")) == str(source_file or "")
            ):
                row["last_ingested_at"] = now
                row["last_claim_count"] = int(claims_count)
                row["updated_at"] = now
                changed = True
        if changed:
            self.write_source_registry(rows)

    def register_source(
        self,
        *,
        topic: str,
        source: str,
        refresh_after_days: int = 14,
        priority: str = "medium",
        source_file: str | None = None,
    ) -> dict[str, Any]:
        rows = self.load_source_registry()
        key = f"{topic}|{source}|{source_file or ''}"
        now = datetime.now(timezone.utc).isoformat()
        refresh_after_days = max(1, int(refresh_after_days))
        priority = str(priority or "medium").lower()
        updated = False
        for row in rows:
            row_key = f"{row.get('topic','')}|{row.get('source','')}|{row.get('source_file','')}"
            if row_key == key:
                row.update(
                    {
                        "topic": topic,
                        "source": source,
                        "source_file": source_file or "",
                        "refresh_after_days": refresh_after_days,
                        "priority": priority,
                        "updated_at": now,
                    }
                )
                updated = True
                break
        if not updated:
            rows.append(
                {
                    "topic": topic,
                    "source": source,
                    "source_file": source_file or "",
                    "refresh_after_days": refresh_after_days,
                    "priority": priority,
                    "last_ingested_at": "",
                    "last_refreshed_at": "",
                    "last_claim_count": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        self.write_source_registry(rows)
        return {
            "status": "SUCCESS",
            "topic": topic,
            "source": source,
            "priority": priority,
            "refresh_after_days": refresh_after_days,
        }

    def source_due(self, row: dict[str, Any]) -> bool:
        last = str(row.get("last_refreshed_at") or row.get("last_ingested_at") or "")
        if not last:
            return True
        return self.ctx._days_since(last) >= float(row.get("refresh_after_days", 14) or 14)

    def refresh_sources(
        self,
        *,
        topic: str = "",
        due_only: bool = True,
        pass_threshold: float = 0.6,
        question_count: int = 5,
    ) -> dict[str, Any]:
        rows = self.load_source_registry()
        selected = [r for r in rows if (not topic or str(r.get("topic", "")) == topic)]
        if due_only:
            selected = [r for r in selected if self.source_due(r)]
        refreshed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if row not in selected:
                skipped.append(
                    {
                        "topic": row.get("topic", ""),
                        "source": row.get("source", ""),
                        "reason": "not_selected"
                        if topic and str(row.get("topic", "")) != topic
                        else ("not_due" if due_only else "not_requested"),
                    }
                )
                continue
            ingest_report = self.ctx.ingest(
                source=str(row.get("source", "")),
                source_file=(str(row.get("source_file", "")) or None),
                topic=str(row.get("topic", "")),
            )
            converge_report = self.ctx.converge(
                topic=str(row.get("topic", "")),
                max_rounds=2,
                pass_threshold=pass_threshold,
                question_count=question_count,
                auto_research=False,
            )
            row["last_ingested_at"] = now
            row["last_refreshed_at"] = now
            row["last_claim_count"] = int(ingest_report.get("claims_count", 0))
            row["updated_at"] = now
            refreshed.append(
                {
                    "topic": row.get("topic", ""),
                    "source": row.get("source", ""),
                    "claims_count": ingest_report.get("claims_count", 0),
                    "converged": converge_report.get("converged", False),
                    "self_question_pass_rate": converge_report.get("self_question_pass_rate", 0.0),
                }
            )
        self.write_source_registry(rows)
        return {
            "status": "SUCCESS",
            "due_only": due_only,
            "topic": topic,
            "refreshed_count": len(refreshed),
            "skipped_count": len(skipped),
            "refreshed": refreshed,
            "skipped": skipped[:20],
            "registry_path": str(self.ctx.sources_path),
            "timestamp": now,
        }

    def build_refresh_plan(
        self,
        *,
        topic: str = "",
        due_within_days: int = 0,
    ) -> dict[str, Any]:
        rows = self.load_source_registry()
        if topic:
            rows = [row for row in rows if str(row.get("topic", "")) == topic]

        due_items: list[dict[str, Any]] = []
        not_due_items: list[dict[str, Any]] = []
        threshold = max(0, int(due_within_days))
        for row in rows:
            last = str(row.get("last_refreshed_at") or row.get("last_ingested_at") or "")
            refresh_after_days = int(row.get("refresh_after_days", 14) or 14)
            days_since = self.ctx._days_since(last) if last else float(refresh_after_days)
            days_until_due = max(0.0, float(refresh_after_days) - float(days_since))
            item = {
                "topic": row.get("topic", ""),
                "source": row.get("source", ""),
                "source_file": row.get("source_file", ""),
                "priority": row.get("priority", "medium"),
                "refresh_after_days": refresh_after_days,
                "last_ingested_at": row.get("last_ingested_at", ""),
                "last_refreshed_at": row.get("last_refreshed_at", ""),
                "last_claim_count": int(row.get("last_claim_count", 0) or 0),
                "days_since_last_refresh": round(float(days_since), 3),
                "days_until_due": round(float(days_until_due), 3),
                "due": bool(days_until_due <= threshold),
            }
            if item["due"]:
                due_items.append(item)
            else:
                not_due_items.append(item)

        return {
            "status": "SUCCESS",
            "topic": topic,
            "due_within_days": threshold,
            "sources_total": len(rows),
            "due_count": len(due_items),
            "not_due_count": len(not_due_items),
            "due": due_items,
            "not_due": not_due_items,
            "registry_path": str(self.ctx.sources_path),
            "benchmark_candidates_path": str(self.ctx.benchmark_candidates_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
