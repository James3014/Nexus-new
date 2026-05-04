from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re


@dataclass(frozen=True)
class DocScoutHit:
    path: str
    score: float
    source: str
    snippet: str


class DocScoutAdapter:
    """Lightweight local doc scout for research-stage context retrieval."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()

    def search(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        tokens = self._tokens(query)
        if not tokens:
            return self._empty(query)

        hits: list[DocScoutHit] = []
        docs_roots = [
            self.project_root / "docs",
            self.project_root / "nexus_wiki_vault",
        ]
        for root in docs_roots:
            hits.extend(self._scan_markdown(root, tokens))

        # Dependency changelog hints: prefer files likely to encode dependency updates.
        dep_roots = [
            self.project_root / "requirements.txt",
            self.project_root / "pyproject.toml",
            self.project_root / "package.json",
            self.project_root / "poetry.lock",
            self.project_root / "uv.lock",
        ]
        for dep_file in dep_roots:
            if dep_file.exists():
                text = dep_file.read_text(encoding="utf-8", errors="ignore")
                score = self._score_text(text, tokens)
                if score > 0:
                    hits.append(
                        DocScoutHit(
                            path=str(dep_file),
                            score=score + 0.5,
                            source="dependency",
                            snippet=self._best_line(text, tokens),
                        )
                    )

        ranked = sorted(hits, key=lambda item: item.score, reverse=True)[: max(1, int(limit))]
        retrieval_hints = [f"{item.source}:{Path(item.path).name}" for item in ranked]
        confidence = min(1.0, round(sum(item.score for item in ranked) / max(1.0, len(tokens) * 3.0), 4))
        return {
            "query": query,
            "status": "SUCCESS",
            "hits_count": len(ranked),
            "confidence": confidence,
            "retrieval_hints": retrieval_hints,
            "hits": [
                {
                    "path": item.path,
                    "score": round(item.score, 4),
                    "source": item.source,
                    "snippet": item.snippet,
                }
                for item in ranked
            ],
        }

    def _scan_markdown(self, root: Path, tokens: list[str]) -> list[DocScoutHit]:
        if not root.exists():
            return []
        hits: list[DocScoutHit] = []
        for path in root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            score = self._score_text(text, tokens)
            if score <= 0:
                continue
            rel = str(path.resolve())
            source = "issue" if "incident" in rel.lower() else "doc"
            hits.append(
                DocScoutHit(
                    path=rel,
                    score=score,
                    source=source,
                    snippet=self._best_line(text, tokens),
                )
            )
        return hits

    def _score_text(self, text: str, tokens: list[str]) -> float:
        content = text.lower()
        score = 0.0
        for token in tokens:
            if token in content:
                score += 1.0
        return score

    def _best_line(self, text: str, tokens: list[str]) -> str:
        best = ""
        best_score = -1
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            score = 0
            lower = line.lower()
            for token in tokens:
                if token in lower:
                    score += 1
            if score > best_score:
                best = line[:220]
                best_score = score
        return best

    def _tokens(self, query: str) -> list[str]:
        out: list[str] = []
        for token in re.findall(r"[a-zA-Z_]{4,}", (query or "").lower()):
            if token in out:
                continue
            out.append(token)
        return out[:12]

    def _empty(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "status": "EMPTY_QUERY",
            "hits_count": 0,
            "confidence": 0.0,
            "retrieval_hints": [],
            "hits": [],
        }
