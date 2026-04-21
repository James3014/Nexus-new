from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .protocols import LearnContextProtocol


class BenchmarkService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    def append_benchmark_candidate(
        self,
        *,
        topic: str,
        question: str,
        actual_status: str,
        reason: str,
        token_coverage: float = 0.0,
        topic_pack_selected: str = "",
        conflicts: list[dict[str, Any]] | None = None,
    ) -> None:
        payload = {
            "topic": topic,
            "question": question,
            "actual_status": actual_status,
            "reason": reason,
            "token_coverage": round(float(token_coverage or 0.0), 4),
            "topic_pack_selected": topic_pack_selected,
            "conflicts": conflicts or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.ctx.benchmark_candidates_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ctx.benchmark_candidates_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def load_benchmark_candidates(self) -> list[dict[str, Any]]:
        if not self.ctx.benchmark_candidates_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.ctx.benchmark_candidates_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except json.JSONDecodeError:
                continue
        return rows

    @staticmethod
    def normalize_question(question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    def curate_benchmark_bank(
        self,
        *,
        topic: str = "",
        max_questions: int = 40,
        min_occurrences: int = 1,
    ) -> dict[str, Any]:
        candidates = self.load_benchmark_candidates()
        if topic:
            candidates = [c for c in candidates if str(c.get("topic", "")) == topic]

        buckets: dict[str, dict[str, Any]] = {}
        for row in candidates:
            question = str(row.get("question", "")).strip()
            if not question:
                continue
            key = self.normalize_question(question)
            status = str(row.get("actual_status", "UNKNOWN")).upper()
            token_coverage = float(row.get("token_coverage", 0.0) or 0.0)
            entry = buckets.setdefault(
                key,
                {
                    "question": question,
                    "topics": {},
                    "status_counts": {},
                    "reasons": {},
                    "count": 0,
                    "token_coverage_sum": 0.0,
                    "latest_at": "",
                    "topic_pack_selected": str(row.get("topic_pack_selected", "")),
                },
            )
            t = str(row.get("topic", ""))
            entry["topics"][t] = entry["topics"].get(t, 0) + 1
            entry["status_counts"][status] = entry["status_counts"].get(status, 0) + 1
            reason = str(row.get("reason", ""))
            if reason:
                entry["reasons"][reason] = entry["reasons"].get(reason, 0) + 1
            entry["count"] += 1
            entry["token_coverage_sum"] += token_coverage
            created_at = str(row.get("created_at", ""))
            if created_at and created_at > entry["latest_at"]:
                entry["latest_at"] = created_at
            if not entry["question"] or len(question) < len(entry["question"]):
                entry["question"] = question

        scored: list[dict[str, Any]] = []
        for entry in buckets.values():
            if int(entry["count"]) < max(1, int(min_occurrences)):
                continue
            status_counts = entry["status_counts"]
            expected_status = max(status_counts.items(), key=lambda kv: kv[1])[0] if status_counts else "UNKNOWN"
            avg_cov = entry["token_coverage_sum"] / max(1, int(entry["count"]))
            diversity_bonus = 1.0 if len(status_counts) > 1 else 0.0
            hard_case_bonus = 0.8 if expected_status in {"UNKNOWN", "CONFLICT"} else 0.2
            coverage_band_bonus = 0.6 if 0.2 <= avg_cov <= 0.85 else 0.1
            score = float(entry["count"]) * 1.5 + diversity_bonus + hard_case_bonus + coverage_band_bonus
            scored.append(
                {
                    "question": entry["question"],
                    "expected_status": expected_status,
                    "score": round(score, 4),
                    "count": int(entry["count"]),
                    "avg_token_coverage": round(avg_cov, 4),
                    "status_counts": status_counts,
                    "reasons": entry["reasons"],
                    "topics": entry["topics"],
                    "latest_at": entry["latest_at"],
                    "topic_pack_selected": entry.get("topic_pack_selected", ""),
                }
            )

        scored.sort(key=lambda item: (item["score"], item["count"]), reverse=True)
        selected = scored[: max(1, int(max_questions))]
        manifest_questions = []
        for item in selected:
            manifest_questions.append(
                {
                    "question": item["question"],
                    "expected_status": item["expected_status"],
                    "expected_keywords": [],
                    "difficulty": "unknown"
                    if item["expected_status"] == "UNKNOWN"
                    else ("conflict" if item["expected_status"] == "CONFLICT" else "deep"),
                    "category": "auto_curated",
                    "evidence_score": item["score"],
                }
            )

        bank_payload = {
            "status": "SUCCESS",
            "topic": topic,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "candidate_count": len(candidates),
            "bucket_count": len(buckets),
            "selected_count": len(selected),
            "questions": manifest_questions,
            "ranked_pool": selected,
            "source_file": str(self.ctx.benchmark_candidates_path),
        }
        self.ctx.benchmark_bank_path.parent.mkdir(parents=True, exist_ok=True)
        self.ctx.benchmark_bank_path.write_text(json.dumps(bank_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return bank_payload
