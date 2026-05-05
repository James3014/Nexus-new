from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol
import re
import time


@dataclass(frozen=True)
class DocScoutHit:
    path: str
    score: float
    source: str
    snippet: str
    source_url: str = ""


class ExternalScoutProvider(Protocol):
    name: str

    def search(self, query: str, *, tokens: list[str], limit: int) -> list[dict[str, Any]]:
        ...


class StaticExternalScoutProvider:
    """Deterministic opt-in provider for GitHub/spec/arXiv style evidence rows."""

    def __init__(self, *, name: str, source: str, rows: list[dict[str, Any]]) -> None:
        self.name = name
        self.source = source
        self.rows = list(rows or [])

    def search(self, query: str, *, tokens: list[str], limit: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.rows:
            text = f"{row.get('title', '')} {row.get('snippet', '')} {row.get('source_url', '')}".lower()
            score = sum(1 for token in tokens if token in text)
            if score <= 0:
                continue
            out.append({**row, "source": row.get("source") or self.source, "score": float(row.get("score", score) or score)})
        return sorted(out, key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)[: max(1, int(limit))]


class GitHubIssueScoutProvider(StaticExternalScoutProvider):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(name="github_issue", source="github_issue", rows=rows)


class ArxivScoutProvider(StaticExternalScoutProvider):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(name="arxiv", source="arxiv", rows=rows)


class SpecUrlScoutProvider(StaticExternalScoutProvider):
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(name="spec_url", source="spec", rows=rows)


class DocScoutAdapter:
    """Lightweight local doc scout for research-stage context retrieval."""

    def __init__(
        self,
        project_root: Path,
        *,
        external_providers: list[ExternalScoutProvider] | None = None,
        cache_ttl_sec: int = 86400,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.external_providers = list(external_providers or [])
        self.cache_ttl_sec = max(0, int(cache_ttl_sec or 0))

    def search(self, query: str, *, limit: int = 8, include_external: bool = False) -> dict[str, Any]:
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

        external_enabled = bool(include_external and self.external_providers)
        if external_enabled:
            hits.extend(self._scan_external(query, tokens, limit=limit))

        ranked = sorted(hits, key=lambda item: item.score, reverse=True)[: max(1, int(limit))]
        retrieval_hints = [f"{item.source}:{Path(item.path).name}" for item in ranked]
        confidence = min(1.0, round(sum(item.score for item in ranked) / max(1.0, len(tokens) * 3.0), 4))
        return {
            "query": query,
            "status": "SUCCESS",
            "external_enabled": external_enabled,
            "hits_count": len(ranked),
            "confidence": confidence,
            "retrieval_hints": retrieval_hints,
            "hits": [
                {
                    "path": item.path,
                    "score": round(item.score, 4),
                    "source": item.source,
                    "snippet": item.snippet,
                    "source_url": item.source_url,
                }
                for item in ranked
            ],
        }

    def _scan_external(self, query: str, tokens: list[str], *, limit: int) -> list[DocScoutHit]:
        cached = self._read_external_cache(query, tokens=tokens, limit=limit)
        if cached is not None:
            return cached
        hits: list[DocScoutHit] = []
        for provider in self.external_providers:
            try:
                rows = provider.search(query, tokens=tokens, limit=limit)
            except Exception:
                continue
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                source_url = str(row.get("source_url") or row.get("url") or row.get("path") or "").strip()
                if not self._source_url_verified(source_url):
                    continue
                snippet = str(row.get("snippet") or "")[:220]
                if not snippet.strip():
                    continue
                hits.append(
                    DocScoutHit(
                        path=str(row.get("path") or source_url),
                        score=float(row.get("score", 0.0) or 0.0),
                        source=str(row.get("source") or getattr(provider, "name", "external")),
                        snippet=snippet,
                        source_url=source_url,
                    )
                )
        self._write_external_cache(query, tokens=tokens, limit=limit, hits=hits)
        return hits

    def _source_url_verified(self, source_url: str) -> bool:
        return bool(re.match(r"^https?://", source_url))

    def _cache_path(self, query: str, *, tokens: list[str], limit: int) -> Path:
        provider_names = ",".join(str(getattr(provider, "name", "external")) for provider in self.external_providers)
        raw = json.dumps({"query": query, "tokens": tokens, "limit": limit, "providers": provider_names}, sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        return self.project_root / ".nexus" / "cache" / "doc_scout" / f"{digest}.json"

    def _read_external_cache(self, query: str, *, tokens: list[str], limit: int) -> list[DocScoutHit] | None:
        if self.cache_ttl_sec <= 0:
            return None
        path = self._cache_path(query, tokens=tokens, limit=limit)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - float(payload.get("created_at", 0.0) or 0.0) > self.cache_ttl_sec:
            return None
        hits = []
        for row in payload.get("hits", []) or []:
            if isinstance(row, dict) and self._source_url_verified(str(row.get("source_url") or "")):
                hits.append(DocScoutHit(**row))
        return hits

    def _write_external_cache(self, query: str, *, tokens: list[str], limit: int, hits: list[DocScoutHit]) -> None:
        if self.cache_ttl_sec <= 0:
            return
        path = self._cache_path(query, tokens=tokens, limit=limit)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "nexus_doc_scout_external_cache_v1",
            "created_at": time.time(),
            "hits": [hit.__dict__ for hit in hits],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

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
            "external_enabled": False,
            "hits_count": 0,
            "confidence": 0.0,
            "retrieval_hints": [],
            "hits": [],
        }
