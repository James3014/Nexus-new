"""Runtime retrieval over the committed Wiki agent index and link graph.

This service is intentionally local and evidence-bound.  It never invents a
page when the artifacts are missing, stale, or when only historical sources
match the query.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from nexus.contracts.retrieval_query import build_retrieval_query


AGENT_INDEX_SCHEMA = "nexus.wiki.agent-index.v1"
GRAPH_SCHEMA = "nexus.wiki.wikilink-graph.v1"
FRESHNESS_SCHEMA = "nexus.wiki.content-freshness.v1"
RECEIPT_SCHEMA = "nexus.wiki.knowledge-agent-receipt.v1"
DERIVED_AUTHORITY = "derived_non_authoritative"
CURRENT_CLASSES = {"current_verified", "current_needs_review", "current", "active", "hardened", "sealed"}
LEGACY_CLASSES = {"historical", "superseded", "draft", "archive", "mixed_needs_review"}
TOKEN_RE = re.compile(r"[A-Za-z0-9_:-]+|[\u3400-\u9fff]+")


class WikiKnowledgeAgent:
    """Retrieve current, source-backed Wiki context for a Nexus task."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.vault_root = self.project_root / "nexus_wiki_vault"
        self.generated_root = self.vault_root / "99_Schema" / "generated"
        self.index_path = self.generated_root / "agent-index.json"
        self.graph_path = self.generated_root / "wikilink-graph.json"
        self.freshness_path = self.generated_root / "content-freshness-audit.json"
        self.manifest_path = self.vault_root / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"

    def retrieve(self, query: str, *, max_results: int = 3) -> dict[str, Any]:
        retrieval_query = build_retrieval_query(
            query,
            source_scope="wiki_authority",
            max_chars=500,
        )
        query_receipt = retrieval_query.receipt()
        if query_receipt["status"] != "PASS":
            return self._return_response(
                query_receipt=query_receipt,
                blockers=list(query_receipt.get("unsafe_flags", [])) or ["query_not_allowed"],
            )

        try:
            artifacts = self._load_artifacts()
        except _WikiArtifactError as exc:
            return self._return_response(
                query_receipt=query_receipt,
                blockers=[str(exc)],
            )

        normalized = retrieval_query.normalized_text
        query_tokens = set(TOKEN_RE.findall(str(normalized).lower()))
        if not query_tokens:
            return self._return_response(
                query_receipt=query_receipt,
                blockers=["empty_normalized_query"],
            )

        freshness_by_path = {
            row.get("path"): row
            for row in artifacts["freshness"].get("pages", [])
            if isinstance(row, dict) and row.get("path")
        }
        pages_by_id = {
            page.get("id"): page
            for page in artifacts["index"].get("pages", [])
            if isinstance(page, dict) and page.get("id")
        }
        candidates: list[dict[str, Any]] = []
        legacy_candidates: list[dict[str, Any]] = []
        for page in pages_by_id.values():
            candidate = self._score_page(
                page,
                query_tokens=query_tokens,
                freshness_row=freshness_by_path.get(page.get("path")),
            )
            if candidate is None:
                continue
            if candidate["eligible"]:
                candidates.append(candidate)
            elif candidate["classification"] in LEGACY_CLASSES:
                legacy_candidates.append(candidate)

        candidates.sort(key=self._candidate_sort_key)
        if not candidates:
            if legacy_candidates:
                legacy_candidates.sort(key=self._candidate_sort_key)
                results = [self._receipt_result(item, selected=False, reason="legacy_only_downgraded") for item in legacy_candidates[:max_results]]
                return self._response(
                    status="RETURN",
                    query_receipt=query_receipt,
                    source_fingerprint=artifacts["source_fingerprint"],
                    results=results,
                    blockers=["legacy_only_result"],
                )
            return self._return_response(
                query_receipt=query_receipt,
                source_fingerprint=artifacts["source_fingerprint"],
                blockers=["no_current_authority_match"],
            )

        result_limit = max(1, int(max_results))
        direct_limit = result_limit if len(candidates) == 1 else max(1, result_limit - 1)
        direct = candidates[:direct_limit]
        selected = [self._receipt_result(item, selected=True, reason="direct_authority_match") for item in direct]
        selected_ids = {item["page_id"] for item in direct}
        graph_expansion: list[dict[str, Any]] = []
        for parent in direct:
            for edge in artifacts["graph"].get("edges", []):
                if not isinstance(edge, dict) or edge.get("source") != parent["page_id"]:
                    continue
                target = pages_by_id.get(edge.get("target"))
                if not target or target.get("id") in selected_ids:
                    continue
                target_candidate = self._score_page(
                    target,
                    query_tokens=set(),
                    freshness_row=freshness_by_path.get(target.get("path")),
                )
                if not target_candidate or not target_candidate["eligible"]:
                    continue
                target_candidate["retrieval_score"] = round(parent["retrieval_score"] * 0.75, 6)
                target_candidate["score_components"]["graph_expansion"] = 0.75
                selected_ids.add(target_candidate["page_id"])
                selected.append(self._receipt_result(target_candidate, selected=True, reason="graph_expansion"))
                graph_expansion.append(
                    {
                        "from": parent["source_path"],
                        "to": target_candidate["source_path"],
                        "score": target_candidate["retrieval_score"],
                    }
                )
                if len(selected) >= result_limit:
                    break
            if len(selected) >= result_limit:
                break

        context = self._build_context(selected, source_fingerprint=artifacts["source_fingerprint"])
        return self._response(
            status="PASS",
            query_receipt=query_receipt,
            source_fingerprint=artifacts["source_fingerprint"],
            results=selected,
            graph_expansion=graph_expansion,
            context=context,
            blockers=[],
        )

    def _load_artifacts(self) -> dict[str, Any]:
        paths = {
            "agent-index.json": self.index_path,
            "wikilink-graph.json": self.graph_path,
            "content-freshness-audit.json": self.freshness_path,
        }
        for name, path in paths.items():
            if not path.is_file():
                raise _WikiArtifactError(f"missing_wiki_artifact:{name}")
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
            graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
            freshness = json.loads(self.freshness_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _WikiArtifactError("invalid_wiki_artifact_json") from exc
        if index.get("schema") != AGENT_INDEX_SCHEMA or graph.get("schema") != GRAPH_SCHEMA:
            raise _WikiArtifactError("invalid_wiki_artifact_schema")
        if freshness.get("schema") != FRESHNESS_SCHEMA or freshness.get("status") != "PASS":
            raise _WikiArtifactError("freshness_evidence_not_pass")
        source_fingerprint = str(index.get("source_fingerprint") or "")
        if not source_fingerprint or graph.get("source_fingerprint") != source_fingerprint:
            raise _WikiArtifactError("wiki_artifact_source_fingerprint_mismatch")
        if index.get("authority") != DERIVED_AUTHORITY or graph.get("authority") != DERIVED_AUTHORITY:
            raise _WikiArtifactError("wiki_artifact_authority_invalid")

        # Recompile in memory so the runtime cannot consume an artifact from a
        # different committed Wiki tree.
        try:
            from scripts.ops.build_wiki_agent_index import WikiIndexCompiler

            compiler = WikiIndexCompiler(self.vault_root, self.manifest_path, self.generated_root)
            expected_index, expected_graph, _ = compiler.build()
        except (Exception, SystemExit) as exc:
            raise _WikiArtifactError("wiki_artifact_source_recompile_failed") from exc
        if expected_index.get("source_fingerprint") != source_fingerprint:
            raise _WikiArtifactError("stale_wiki_artifact")
        if expected_graph.get("source_fingerprint") != source_fingerprint:
            raise _WikiArtifactError("stale_wiki_graph")
        self._validate_freshness_identity(freshness)
        return {"index": index, "graph": graph, "freshness": freshness, "source_fingerprint": source_fingerprint}

    def _validate_freshness_identity(self, freshness: dict[str, Any]) -> None:
        source_commits: set[str] = set()
        for page in freshness.get("pages", []):
            if not isinstance(page, dict):
                raise _WikiArtifactError("invalid_freshness_page")
            path = self.vault_root / str(page.get("path") or "")
            if not path.is_file():
                raise _WikiArtifactError("freshness_page_missing")
            content_hash = _sha256(path.read_bytes())
            if content_hash != page.get("content_sha256"):
                raise _WikiArtifactError("stale_freshness_page")
            for source in page.get("source_paths", []):
                if not isinstance(source, dict) or not source.get("exists"):
                    raise _WikiArtifactError("freshness_source_path_missing")
                commit = str(source.get("source_commit") or "")
                if commit and commit != "unknown":
                    source_commits.add(commit)
        commits = sorted(source_commits)
        expected = _sha256("\n".join(commits).encode("utf-8"))
        if expected != freshness.get("source_commit"):
            raise _WikiArtifactError("stale_freshness_source_commit")

    def _score_page(
        self,
        page: dict[str, Any],
        *,
        query_tokens: set[str],
        freshness_row: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        source_path = str(page.get("path") or "")
        if not source_path or source_path.startswith("99_Schema/generated/"):
            return None
        page_path = self.vault_root / source_path
        if not page_path.is_file():
            return None
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        classification = str(
            (freshness_row or {}).get("classification")
            or page.get("classification")
            or "unclassified"
        ).strip().lower()
        searchable = " ".join(
            str(page.get(key) or "")
            for key in ("path", "title", "one_sentence_summary", "authority", "owner", "source_of_truth")
        ) + " " + content[:8000]
        tokens = set(TOKEN_RE.findall(searchable.lower()))
        overlap = len(query_tokens & tokens)
        if query_tokens and overlap == 0:
            return None
        lexical = overlap / max(1, len(query_tokens))
        authority_score = {
            "current_verified": 1.0,
            "current": 0.95,
            "active": 0.9,
            "hardened": 0.85,
            "sealed": 0.8,
            "current_needs_review": 0.65,
            "mixed_needs_review": 0.3,
            "historical": 0.1,
            "superseded": 0.05,
        }.get(classification, 0.0)
        source_kind = self._source_kind(page, content)
        source_score = {"code_backed": 1.0, "spec_backed": 0.85, "wiki_backed": 0.4, "unknown": 0.1}[source_kind]
        canonical_bonus = 0.05 if page.get("is_canonical") else 0.0
        retrieval_score = round(lexical * 0.6 + authority_score * 0.25 + source_score * 0.1 + canonical_bonus, 6)
        return {
            "page_id": page.get("id"),
            "source_path": source_path,
            "title": str(page.get("title") or Path(source_path).stem),
            "summary": str(page.get("one_sentence_summary") or "").strip(),
            "content": content,
            "classification": classification,
            "source_kind": source_kind,
            "authority_score": authority_score,
            "retrieval_score": retrieval_score,
            "score_components": {
                "lexical_overlap": round(lexical, 6),
                "authority": authority_score,
                "source_kind": source_score,
                "canonical_bonus": canonical_bonus,
            },
            "content_sha256": str(page.get("content_sha256") or _sha256(content.encode("utf-8"))),
            "eligible": classification in CURRENT_CLASSES,
        }

    @staticmethod
    def _candidate_sort_key(item: dict[str, Any]) -> tuple[float, float, str]:
        return (-float(item.get("retrieval_score", 0.0)), -float(item.get("authority_score", 0.0)), str(item.get("source_path", "")))

    @staticmethod
    def _source_kind(page: dict[str, Any], content: str) -> str:
        source = str(page.get("source_of_truth") or "").lower()
        if re.search(r"\[(?:code):", content, re.IGNORECASE) or any(
            token in source for token in (".py", ".rs", ".sh", "nexus/", "scripts/")
        ):
            return "code_backed"
        if re.search(r"\[(?:source):", content, re.IGNORECASE) or "spec" in source:
            return "spec_backed"
        if source or page.get("is_canonical"):
            return "wiki_backed"
        return "unknown"

    @staticmethod
    def _receipt_result(item: dict[str, Any], *, selected: bool, reason: str) -> dict[str, Any]:
        return {
            "source_id": item["page_id"],
            "source_page": item["source_path"],
            "source_path": item["source_path"],
            "title": item["title"],
            "authority_classification": item["classification"],
            "source_kind": item["source_kind"],
            "authority_score": item["authority_score"],
            "retrieval_score": item["retrieval_score"],
            "score_components": item["score_components"],
            "content_sha256": item["content_sha256"],
            "selected": selected,
            "selected_reason": reason,
        }

    def _build_context(self, results: list[dict[str, Any]], *, source_fingerprint: str) -> str:
        blocks: list[str] = []
        for index, result in enumerate(results, start=1):
            page_path = self.vault_root / result["source_path"]
            content = page_path.read_text(encoding="utf-8")
            excerpt = _strip_frontmatter(content).strip()[:2200]
            blocks.append(
                f"[Wiki Source {index}]\n"
                f"source_page: {result['source_page']}\n"
                f"authority_classification: {result['authority_classification']}\n"
                f"source_fingerprint: {source_fingerprint}\n"
                f"retrieval_score: {result['retrieval_score']:.6f}\n"
                f"source_kind: {result['source_kind']}\n"
                f"{excerpt}"
            )
        return "\n\n".join(blocks)

    def _response(
        self,
        *,
        status: str,
        query_receipt: dict[str, Any],
        source_fingerprint: str = "",
        results: list[dict[str, Any]] | None = None,
        graph_expansion: list[dict[str, Any]] | None = None,
        context: str = "",
        blockers: list[str],
    ) -> dict[str, Any]:
        results = results or []
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": status,
            "artifact_authority": DERIVED_AUTHORITY,
            "query": query_receipt,
            "index_snapshot_id": source_fingerprint,
            "source_fingerprint": source_fingerprint,
            "graph_source_fingerprint": source_fingerprint,
            "result_count": len(results),
            "selected_count": sum(1 for result in results if result.get("selected")),
            "results": [
                {**result, "source_fingerprint": source_fingerprint}
                for result in results
            ],
            "graph_expansion": graph_expansion or [],
            "blockers": sorted(set(blockers)),
            "claim_boundary": [
                "Wiki context is source-bound retrieval evidence, not an answer or runtime policy.",
                "Historical and superseded pages are never promoted to selected current authority.",
            ],
        }
        return {
            "schema": RECEIPT_SCHEMA,
            "status": status,
            "context": context if status == "PASS" else "",
            "selected_sources": [result["source_page"] for result in results if result.get("selected")],
            "source_fingerprint": source_fingerprint,
            "retrieval_receipt": receipt,
            "blockers": sorted(set(blockers)),
        }

    def _return_response(
        self,
        *,
        query_receipt: dict[str, Any],
        blockers: list[str],
        source_fingerprint: str = "",
    ) -> dict[str, Any]:
        return self._response(
            status="RETURN",
            query_receipt=query_receipt,
            source_fingerprint=source_fingerprint,
            blockers=blockers,
        )


class _WikiArtifactError(RuntimeError):
    pass


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end >= 0:
            return content[end + len("\n---") :]
    return content


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_runtime_integration(project_root: str | Path) -> tuple[bool, list[str]]:
    """Run the Phase 7 runtime gate against the real committed Wiki artifacts."""
    result = WikiKnowledgeAgent(project_root).retrieve("CLI gate", max_results=3)
    blockers = list(result.get("blockers", []))
    receipt = result.get("retrieval_receipt", {})
    results = receipt.get("results", [])
    if result.get("status") != "PASS":
        blockers.append("runtime_retrieval_not_pass")
    if not results or results[0].get("authority_classification") != "current_verified":
        blockers.append("current_authority_not_first")
    if not result.get("source_fingerprint") or not receipt.get("graph_source_fingerprint"):
        blockers.append("source_identity_missing")
    if any(not item.get("source_page") or not item.get("source_fingerprint") for item in results):
        blockers.append("result_source_identity_missing")
    if not result.get("context") or "authority_classification:" not in result["context"]:
        blockers.append("context_source_identity_missing")
    return not blockers, sorted(set(blockers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run the Phase 7 runtime integration gate")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required")
    passed, blockers = verify_runtime_integration(args.repo_root)
    if passed:
        print("KNOWLEDGE_AGENT_RUNTIME_INTEGRATION_PASS")
        return 0
    print("KNOWLEDGE_AGENT_RUNTIME_INTEGRATION_RETURN")
    print("blockers=" + ",".join(blockers))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
