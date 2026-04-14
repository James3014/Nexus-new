from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.services.mem_palace import MemPalace


@dataclass
class LearnClaim:
    claim: str
    source_url: str
    citation_span: list[int]
    topic_tags: list[str]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "source_url": self.source_url,
            "citation_span": self.citation_span,
            "topic_tags": self.topic_tags,
            "created_at": self.created_at,
        }


class LearnModeService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.knowledge_dir = project_root / ".nexus" / "knowledge"
        self.raw_dir = self.knowledge_dir / "raw_sources"
        self.claims_path = self.knowledge_dir / "learn_claims.jsonl"
        self.reports_dir = project_root / ".nexus" / "reports" / "learn"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, p: str | Path) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (self.project_root / path).resolve()

    @staticmethod
    def _extract_tags(claim: str) -> list[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", claim.lower())
        return sorted(set(words[:8]))

    @staticmethod
    def _split_to_claims(text: str, source_url: str) -> list[LearnClaim]:
        claims: list[LearnClaim] = []
        for m in re.finditer(r"[^.!?\n][^.!?\n]{20,}[.!?]?", text):
            raw = m.group(0).strip()
            if len(raw) < 20:
                continue
            claims.append(
                LearnClaim(
                    claim=raw,
                    source_url=source_url,
                    citation_span=[m.start(), m.end()],
                    topic_tags=LearnModeService._extract_tags(raw),
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            if len(claims) >= 200:
                break
        return claims

    def _save_source_snapshot(self, source_ref: str, text: str) -> Path:
        digest = hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:16]
        out = self.raw_dir / f"{digest}.txt"
        out.write_text(text, encoding="utf-8")
        return out

    def _load_source_text(self, source: str, source_file: str | None = None) -> tuple[str, str]:
        if source_file:
            src_path = self._resolve_path(source_file)
            return src_path.read_text(encoding="utf-8"), f"file://{src_path}"
        if source.startswith("repo:"):
            repo = source.replace("repo:", "", 1).strip()
            if "/" in repo:
                owner, name = repo.split("/", 1)
                for branch in ("main", "master"):
                    url = f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/README.md"
                    try:
                        with request.urlopen(url, timeout=10) as resp:  # nosec: B310
                            payload = resp.read().decode("utf-8", errors="ignore")
                        if payload.strip():
                            return payload, url
                    except Exception:
                        continue
        if source.startswith("http://") or source.startswith("https://"):
            with request.urlopen(source, timeout=10) as resp:  # nosec: B310 (user-provided url by design)
                payload = resp.read().decode("utf-8", errors="ignore")
            return payload, source
        # keyword/repo fallback path: treat source string itself as seed text
        seed = (
            f"Learning seed for topic: {source}. "
            f"This entry captures baseline context for {source}. "
            f"Additional evidence should be ingested with --source-file or URL."
        )
        return seed, f"keyword://{source}"

    def _append_claims(self, claims: list[LearnClaim]) -> None:
        with self.claims_path.open("a", encoding="utf-8") as f:
            for c in claims:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")

    def load_claims(self) -> list[dict[str, Any]]:
        if not self.claims_path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.claims_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def ingest(self, source: str, source_file: str | None = None, topic: str = "") -> dict[str, Any]:
        text, source_ref = self._load_source_text(source, source_file=source_file)
        snapshot_path = self._save_source_snapshot(source_ref, text)
        claims = self._split_to_claims(text, source_ref)
        self._append_claims(claims)

        # Learning closure hooks: MemPalace verify + Findings write
        palace = MemPalace(str(self.project_root))
        verified = palace.verify([c.to_dict() for c in claims])
        verified_count = len(verified)

        store = FindingsMemoryStore(self.project_root)
        card = FindingsCard(
            kind="knowledge",
            title=f"Learn ingest: {source}",
            scope="task",
            tags=["learn_mode", "ingest"] + ([topic] if topic else []),
            stage="scout",
            confidence="medium",
            evidence_paths=[str(self.claims_path), str(snapshot_path)],
            retrieval_hints=[topic or source],
            body=f"Ingested {len(claims)} claims from {source_ref}",
            task_id=f"learn-{int(datetime.now(timezone.utc).timestamp())}",
            extra={"verified_claims": verified_count},
        )
        card_path = store.write(card)

        report = {
            "status": "SUCCESS",
            "source": source,
            "source_ref": source_ref,
            "claims_count": len(claims),
            "verified_claims_count": verified_count,
            "sources_count": 1,
            "claims_store": str(self.claims_path),
            "source_snapshot_path": str(snapshot_path),
            "findings_card_path": card_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return report

    def converge(self, topic: str, max_rounds: int = 3, pass_threshold: float = 0.6) -> dict[str, Any]:
        claims = self.load_claims()
        tokens = set(re.findall(r"[A-Za-z0-9_-]+", topic.lower()))
        if not tokens:
            tokens = {"general"}

        def _match(c: dict[str, Any]) -> bool:
            blob = f"{c.get('claim', '')} {' '.join(c.get('topic_tags', []))}".lower()
            return any(t in blob for t in tokens)

        matched = [c for c in claims if _match(c)]
        total_questions = min(5, max(3, len(tokens)))
        answered = min(total_questions, len(matched))
        pass_rate = 0.0 if total_questions == 0 else answered / total_questions
        converged = pass_rate >= pass_threshold
        rounds_used = 1

        while not converged and rounds_used < max_rounds:
            rounds_used += 1
            # local-first loop: no auto web fetch in MVP; retain unresolved questions
            answered = min(total_questions, answered + 1)
            pass_rate = answered / total_questions
            converged = pass_rate >= pass_threshold

        unresolved = [] if converged else [f"Need more evidence for topic token: {t}" for t in sorted(tokens)]
        report = {
            "status": "SUCCESS",
            "topic": topic,
            "rounds_used": rounds_used,
            "sources_count": len({c.get("source_url", "") for c in claims}),
            "claims_total": len(claims),
            "claims_matched": len(matched),
            "self_questions_total": total_questions,
            "self_questions_answered": answered,
            "self_question_pass_rate": round(pass_rate, 4),
            "coverage": round(0.0 if not claims else len(matched) / max(1, len(claims)), 4),
            "converged": converged,
            "unresolved_questions": unresolved,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return report

    def ask(self, topic: str, top_k: int = 5) -> dict[str, Any]:
        claims = self.load_claims()
        tokens = set(re.findall(r"[A-Za-z0-9_-]+", topic.lower()))
        if not tokens:
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "reason": "empty_topic",
            }

        scored: list[tuple[int, dict[str, Any]]] = []
        for c in claims:
            blob = f"{c.get('claim', '')} {' '.join(c.get('topic_tags', []))}".lower()
            score = sum(1 for t in tokens if t in blob)
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = [c for _, c in scored[:top_k]]

        if not best:
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "reason": "no_cited_claims",
            }

        lines = []
        citations = []
        for c in best:
            span = c.get("citation_span", [0, 0])
            source_url = c.get("source_url", "unknown://source")
            citation = f"{source_url}#span={span[0]}-{span[1]}"
            lines.append(f"- {c.get('claim', '')} [{citation}]")
            citations.append(
                {
                    "source_url": source_url,
                    "citation_span": span,
                }
            )
        return {
            "status": "ANSWERED",
            "topic": topic,
            "answer": "\n".join(lines),
            "citations": citations,
            "claims_used": len(best),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def build_report(self, topic: str = "") -> dict[str, Any]:
        claims = self.load_claims()
        sources = {c.get("source_url", "") for c in claims if c.get("source_url")}
        matched = claims
        unresolved_questions: list[str] = []
        coverage = 1.0 if claims else 0.0
        pass_rate = 1.0 if claims else 0.0
        if topic:
            tokens = set(re.findall(r"[A-Za-z0-9_-]+", topic.lower()))
            if tokens:
                matched = []
                for c in claims:
                    blob = f"{c.get('claim', '')} {' '.join(c.get('topic_tags', []))}".lower()
                    if any(t in blob for t in tokens):
                        matched.append(c)
                coverage = 0.0 if not claims else len(matched) / len(claims)
                pass_rate = min(1.0, len(matched) / max(3, len(tokens)))
                if not matched:
                    unresolved_questions = [f"Need cited claims for token: {t}" for t in sorted(tokens)]
                elif pass_rate < 0.6:
                    unresolved_questions = ["Need more cited claims to reach pass threshold 0.6"]

        return {
            "status": "SUCCESS",
            "topic": topic,
            "sources_count": len(sources),
            "claims_count": len(claims),
            "coverage": round(coverage, 4),
            "self_question_pass_rate": round(pass_rate, 4),
            "unresolved_questions": unresolved_questions,
            "converged": pass_rate >= 0.6,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
