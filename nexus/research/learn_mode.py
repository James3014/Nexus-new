from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import quote_plus

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

    @staticmethod
    def _claim_key(claim: LearnClaim | dict[str, Any]) -> str:
        if isinstance(claim, LearnClaim):
            raw = f"{claim.claim}|{claim.source_url}|{claim.citation_span}"
        else:
            raw = f"{claim.get('claim','')}|{claim.get('source_url','')}|{claim.get('citation_span',[])}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
        existing = {self._claim_key(c) for c in self.load_claims()}
        with self.claims_path.open("a", encoding="utf-8") as f:
            for c in claims:
                key = self._claim_key(c)
                if key in existing:
                    continue
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
                existing.add(key)

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

    def _extract_tokens(self, topic: str) -> set[str]:
        tokens = set(re.findall(r"[A-Za-z0-9_-]+", topic.lower()))
        return {t for t in tokens if len(t) >= 3} or {"general"}

    def _is_valid_citation(self, c: dict[str, Any]) -> bool:
        src = str(c.get("source_url") or "")
        span = c.get("citation_span")
        if not src or not isinstance(span, list) or len(span) != 2:
            return False
        try:
            start, end = int(span[0]), int(span[1])
            return end > start >= 0
        except Exception:
            return False

    def _discover_sources(self, topic: str, max_sources: int = 3) -> list[str]:
        tokens = sorted(self._extract_tokens(topic))
        out: list[str] = []
        claims = self.load_claims()
        for c in claims:
            src = str(c.get("source_url", ""))
            if src.startswith("https://raw.githubusercontent.com/"):
                m = re.search(r"githubusercontent\.com/([^/]+/[^/]+)/", src)
                if m:
                    out.append(f"repo:{m.group(1)}")
        q = quote_plus(" ".join(tokens[:4]))
        out.append(f"https://duckduckgo.com/html/?q={q}")
        # stable unique
        uniq = []
        for s in out:
            if s not in uniq:
                uniq.append(s)
        return uniq[:max_sources]

    def _build_question_set(self, topic: str, question_count: int = 5) -> list[dict[str, Any]]:
        tokens = sorted(self._extract_tokens(topic))
        qs = []
        for token in tokens[: max(3, question_count)]:
            qs.append(
                {
                    "token": token,
                    "question": f"What cited evidence explains '{token}' in topic context?",
                }
            )
        return qs

    def _answer_questions(self, questions: list[dict[str, Any]], claims: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        answered, unresolved = [], []
        for q in questions:
            token = q["token"]
            matched = []
            for c in claims:
                if not self._is_valid_citation(c):
                    continue
                blob = f"{c.get('claim','')} {' '.join(c.get('topic_tags',[]))}".lower()
                if token in blob:
                    matched.append(
                        {
                            "source_url": c.get("source_url"),
                            "citation_span": c.get("citation_span"),
                            "claim": c.get("claim", ""),
                        }
                    )
                if len(matched) >= 2:
                    break
            if matched:
                answered.append({"token": token, "question": q["question"], "evidence": matched})
            else:
                unresolved.append({"token": token, "question": q["question"]})
        return answered, unresolved

    def converge(
        self,
        topic: str,
        max_rounds: int = 3,
        pass_threshold: float = 0.6,
        question_count: int = 5,
        auto_research: bool = True,
        max_sources_per_round: int = 2,
    ) -> dict[str, Any]:
        claims = self.load_claims()
        questions = self._build_question_set(topic, question_count=question_count)
        rounds_used = 0
        discovered_sources: list[str] = []
        answered_q, unresolved_q = [], questions
        while rounds_used < max_rounds:
            rounds_used += 1
            claims = self.load_claims()
            answered_q, unresolved_q = self._answer_questions(questions, claims)
            pass_rate = 0.0 if not questions else len(answered_q) / len(questions)
            converged = pass_rate >= pass_threshold
            if converged or not auto_research or rounds_used >= max_rounds:
                break
            for src in self._discover_sources(topic, max_sources=max_sources_per_round):
                discovered_sources.append(src)
                try:
                    self.ingest(source=src, source_file=None, topic=topic)
                except Exception:
                    continue

        claims = self.load_claims()
        matched = [c for c in claims if self._is_valid_citation(c)]
        pass_rate = 0.0 if not questions else len(answered_q) / len(questions)
        converged = pass_rate >= pass_threshold
        unresolved = [] if converged else [f"Need cited evidence for token: {q['token']}" for q in unresolved_q]
        report = {
            "status": "SUCCESS",
            "topic": topic,
            "rounds_used": rounds_used,
            "sources_count": len({c.get("source_url", "") for c in claims}),
            "claims_total": len(claims),
            "claims_matched": len(matched),
            "self_questions_total": len(questions),
            "self_questions_answered": len(answered_q),
            "self_question_pass_rate": round(pass_rate, 4),
            "coverage": round(0.0 if not claims else len(matched) / max(1, len(claims)), 4),
            "converged": converged,
            "question_set": questions,
            "answered_questions": answered_q,
            "unresolved_questions": unresolved,
            "discovered_sources": discovered_sources,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return report

    def ask(self, topic: str, top_k: int = 5, min_evidence: int = 1) -> dict[str, Any]:
        claims = self.load_claims()
        tokens = self._extract_tokens(topic)
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
            if not self._is_valid_citation(c):
                continue
            blob = f"{c.get('claim', '')} {' '.join(c.get('topic_tags', []))}".lower()
            score = sum(1 for t in tokens if t in blob)
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = [c for _, c in scored[:top_k] if self._is_valid_citation(c)]

        if len(best) < max(1, min_evidence):
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "reason": "insufficient_cited_claims",
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
                    "claim": c.get("claim", ""),
                }
            )
        return {
            "status": "ANSWERED",
            "topic": topic,
            "answer": "\n".join(lines),
            "citations": citations,
            "claims_used": len(best),
            "min_evidence_required": max(1, min_evidence),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def build_report(self, topic: str = "") -> dict[str, Any]:
        claims = self.load_claims()
        sources = {c.get("source_url", "") for c in claims if c.get("source_url")}
        valid_claims = [c for c in claims if self._is_valid_citation(c)]
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
            "claims_with_valid_citation": len(valid_claims),
            "citation_valid_ratio": round(0.0 if not claims else len(valid_claims) / len(claims), 4),
            "top_sources": sorted(sources)[:5],
            "coverage": round(coverage, 4),
            "self_question_pass_rate": round(pass_rate, 4),
            "unresolved_questions": unresolved_questions,
            "converged": pass_rate >= 0.6,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
