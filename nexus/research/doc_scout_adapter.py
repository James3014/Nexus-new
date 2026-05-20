from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol
import re
import time

from nexus.infrastructure.guarded_fetch import GuardedFetcher


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


class FetchedExternalScoutProvider:
    """Opt-in external fetch provider with injectable fetcher for deterministic tests."""

    def __init__(
        self,
        *,
        name: str,
        source: str,
        urls: list[str],
        fetcher: Any | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self.name = name
        self.source = source
        self.urls = [str(url).strip() for url in urls if str(url).strip()]
        self.fetcher = fetcher or self._urlopen_fetcher
        self.timeout_sec = max(0.1, float(timeout_sec or 5.0))

    def search(self, query: str, *, tokens: list[str], limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for url in self.urls[: max(1, int(limit))]:
            if not re.match(r"^https?://", url):
                continue
            try:
                text = str(self.fetcher(url, timeout_sec=self.timeout_sec) or "")
            except Exception:
                continue
            score = float(sum(1 for token in tokens if token in text.lower()))
            if score <= 0:
                continue
            rows.append(
                {
                    "path": url,
                    "source_url": url,
                    "source": self.source,
                    "score": score,
                    "snippet": DocScoutAdapter._best_line(text, tokens),
                }
            )
        return sorted(rows, key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)[: max(1, int(limit))]

    @staticmethod
    def _urlopen_fetcher(url: str, *, timeout_sec: float) -> str:
        return GuardedFetcher().fetch_text(url, timeout_sec=timeout_sec)


def _split_env_urls(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n,]+", value or "") if item.strip()]


def build_external_scout_providers_from_env(env: dict[str, str] | None = None) -> list[ExternalScoutProvider]:
    """Build opt-in external providers without making network access implicit."""
    source_env = env if env is not None else os.environ
    providers: list[ExternalScoutProvider] = []
    provider_specs = (
        ("NEXUS_DOC_SCOUT_GITHUB_ISSUE_URLS", "github_issue_fetch", "github_issue"),
        ("NEXUS_DOC_SCOUT_ARXIV_URLS", "arxiv_fetch", "arxiv"),
        ("NEXUS_DOC_SCOUT_SPEC_URLS", "spec_url_fetch", "spec"),
    )
    for env_key, name, source in provider_specs:
        urls = _split_env_urls(str(source_env.get(env_key, "") or ""))
        if urls:
            providers.append(FetchedExternalScoutProvider(name=name, source=source, urls=urls))

    rows_text = str(source_env.get("NEXUS_DOC_SCOUT_EXTERNAL_ROWS_JSON", "") or "").strip()
    if rows_text:
        try:
            rows_payload = json.loads(rows_text)
        except json.JSONDecodeError:
            rows_payload = []
        if isinstance(rows_payload, list):
            providers.append(StaticExternalScoutProvider(name="external_rows", source="external", rows=rows_payload))
    return providers


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
        external_hits: list[DocScoutHit] = []
        external_meta: dict[str, Any] = {
            "providers_configured": [str(getattr(provider, "name", "external")) for provider in self.external_providers],
            "providers_used": [],
            "provider_errors": [],
            "cache_status": "disabled",
            "verified_source_count": 0,
            "source_count": 0,
            "error_count": 0,
            "latency_ms": 0.0,
            "cache_age_sec": 0.0,
        }
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
            external_hits, external_meta = self._scan_external(query, tokens, limit=limit)
            hits.extend(external_hits)

        ranked = sorted(hits, key=lambda item: item.score, reverse=True)[: max(1, int(limit))]
        retrieval_hints = [f"{item.source}:{Path(item.path).name}" for item in ranked]
        confidence = min(1.0, round(sum(item.score for item in ranked) / max(1.0, len(tokens) * 3.0), 4))
        ranked_external_urls = {
            str(item.source_url).strip()
            for item in ranked
            if str(item.source_url).strip()
        }
        external_meta["verified_source_count"] = len(ranked_external_urls)
        external_meta["source_count"] = len(ranked_external_urls)
        return {
            "query": query,
            "status": "SUCCESS",
            "external_enabled": external_enabled,
            "external_metadata": external_meta,
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

    def _scan_external(self, query: str, tokens: list[str], *, limit: int) -> tuple[list[DocScoutHit], dict[str, Any]]:
        meta: dict[str, Any] = {
            "providers_configured": [str(getattr(provider, "name", "external")) for provider in self.external_providers],
            "providers_used": [],
            "provider_errors": [],
            "cache_status": "disabled" if self.cache_ttl_sec <= 0 else "miss",
            "verified_source_count": 0,
            "source_count": 0,
            "error_count": 0,
            "latency_ms": 0.0,
            "cache_age_sec": 0.0,
        }
        started_at = time.perf_counter()
        cached = self._read_external_cache(query, tokens=tokens, limit=limit)
        if cached is not None:
            cached_hits, cache_age_sec = cached
            meta["cache_status"] = "hit"
            meta["providers_used"] = sorted({hit.source for hit in cached_hits if str(hit.source).strip()})
            source_count = len({hit.source_url for hit in cached_hits if str(hit.source_url).strip()})
            meta["verified_source_count"] = source_count
            meta["source_count"] = source_count
            meta["cache_age_sec"] = round(max(0.0, cache_age_sec), 4)
            meta["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 4)
            return cached_hits, meta
        hits: list[DocScoutHit] = []
        for provider in self.external_providers:
            provider_name = str(getattr(provider, "name", "external"))
            try:
                rows = provider.search(query, tokens=tokens, limit=limit)
            except Exception as exc:
                meta["provider_errors"].append(f"{provider_name}:{type(exc).__name__}")
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
                if provider_name not in meta["providers_used"]:
                    meta["providers_used"].append(provider_name)
        self._write_external_cache(query, tokens=tokens, limit=limit, hits=hits)
        source_count = len({hit.source_url for hit in hits if str(hit.source_url).strip()})
        meta["verified_source_count"] = source_count
        meta["source_count"] = source_count
        meta["error_count"] = len(meta["provider_errors"])
        meta["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 4)
        return hits, meta

    def _source_url_verified(self, source_url: str) -> bool:
        return bool(re.match(r"^https?://", source_url))

    def _cache_path(self, query: str, *, tokens: list[str], limit: int) -> Path:
        provider_names = ",".join(str(getattr(provider, "name", "external")) for provider in self.external_providers)
        raw = json.dumps({"query": query, "tokens": tokens, "limit": limit, "providers": provider_names}, sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        return self.project_root / ".nexus" / "cache" / "doc_scout" / f"{digest}.json"

    def _read_external_cache(self, query: str, *, tokens: list[str], limit: int) -> tuple[list[DocScoutHit], float] | None:
        if self.cache_ttl_sec <= 0:
            return None
        path = self._cache_path(query, tokens=tokens, limit=limit)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        cache_age_sec = time.time() - float(payload.get("created_at", 0.0) or 0.0)
        if cache_age_sec > self.cache_ttl_sec:
            return None
        hits = []
        for row in payload.get("hits", []) or []:
            if isinstance(row, dict) and self._source_url_verified(str(row.get("source_url") or "")):
                hits.append(DocScoutHit(**row))
        return hits, cache_age_sec

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

    @staticmethod
    def _best_line(text: str, tokens: list[str]) -> str:
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
            "external_metadata": {
                "providers_configured": [],
                "providers_used": [],
                "provider_errors": [],
                "cache_status": "disabled",
                "verified_source_count": 0,
                "source_count": 0,
                "error_count": 0,
                "latency_ms": 0.0,
                "cache_age_sec": 0.0,
            },
            "hits_count": 0,
            "confidence": 0.0,
            "retrieval_hints": [],
            "hits": [],
        }
