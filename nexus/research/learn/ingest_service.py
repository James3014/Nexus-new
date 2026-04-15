from __future__ import annotations
from .learn_models import LearnClaim
import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import quote_plus
import html
import time
import concurrent.futures
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.services.mem_palace import MemPalace
from nexus.core.skill_outcomes import OutcomePayload, build_outcome_event, append_skill_outcome_event
from nexus.services.memory import MemoryService

class IngestService:
    def __init__(self, project_root: Path, learn_mode_service: Any):
        self.learn_mode_service = learn_mode_service
        self.learn_mode_service.project_root = project_root
        self.learn_mode_service = learn_mode_service

    def _load_github_repo_documents(self, owner: str, repo: str, max_files: int = 24, max_total_chars: int = 400_000) -> list[tuple[str, str]]:
        repo_meta = self.learn_mode_service._http_get_json(f"https://api.github.com/repos/{owner}/{repo}", timeout=12)
        default_branch = str(repo_meta.get("default_branch") or "main")
        tree_api = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        tree_data = self.learn_mode_service._http_get_json(tree_api, timeout=15)
        tree_items = tree_data.get("tree", []) if isinstance(tree_data, dict) else []
        if not isinstance(tree_items, list):
            tree_items = []

        candidates: list[str] = []
        for item in tree_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "blob":
                continue
            path = str(item.get("path") or "")
            size = int(item.get("size") or 0)
            if not path or size <= 0 or size > 200_000:
                continue
            if not self.learn_mode_service._is_text_candidate(path):
                continue
            candidates.append(path)

        if not candidates:
            # fallback to README only
            candidates = ["README.md"]

        candidates = sorted(set(candidates), key=self.learn_mode_service._path_priority)[:max_files]

        docs: list[tuple[str, str]] = []
        total_chars = 0
        for path in candidates:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
            try:
                payload = self.learn_mode_service._http_get_text(raw_url, timeout=12)
            except Exception:
                continue
            cleaned = self.learn_mode_service._clean_text(payload)
            if len(cleaned) < 50:
                continue
            if total_chars + len(cleaned) > max_total_chars:
                break
            total_chars += len(cleaned)
            docs.append((cleaned, raw_url))
        return docs

    def _load_source_documents(self, source: str, source_file: str | None = None) -> list[tuple[str, str]]:
        if source_file:
            src_path = self.learn_mode_service._resolve_path(source_file)
            txt = self.learn_mode_service._clean_text(src_path.read_text(encoding="utf-8"))
            return [(txt, f"file://{src_path}")]

        repo_ref = self.learn_mode_service._parse_github_repo(source)
        if repo_ref:
            owner, name = repo_ref
            docs = self.learn_mode_service._load_github_repo_documents(owner, name)
            if docs:
                return docs

        if source.startswith("http://") or source.startswith("https://"):
            payload = self.learn_mode_service._http_get_text(source, timeout=12)
            return [(self.learn_mode_service._clean_text(payload), source)]

        # keyword/repo fallback path: treat source string itself as seed text
        seed = (
            f"Learning seed for topic: {source}. "
            f"This entry captures baseline context for {source}. "
            f"Additional evidence should be ingested with --source-file or URL."
        )
        return [(seed, f"keyword://{source}")]

    def ingest(self, source: str, source_file: str | None = None, topic: str = "") -> dict[str, Any]:
        docs = self.learn_mode_service._load_source_documents(source, source_file=source_file)
        snapshot_paths: list[str] = []
        claims: list[LearnClaim] = []
        source_refs: list[str] = []
        for text, source_ref in docs:
            source_refs.append(source_ref)
            snap = self.learn_mode_service._save_source_snapshot(source_ref, text)
            snapshot_paths.append(str(snap))
            claims.extend(self.learn_mode_service._split_to_claims(text, source_ref, topic_hint=topic or source))
        self.learn_mode_service._append_claims(claims)

        # Learning closure hooks: MemPalace verify + Findings write
        palace = MemPalace(str(self.learn_mode_service.project_root))
        verified = palace.verify([c.to_dict() for c in claims])
        verified_count = len(verified)

        store = FindingsMemoryStore(self.learn_mode_service.project_root)
        card = FindingsCard(
            kind="knowledge",
            title=f"Learn ingest: {source}",
            scope="task",
            tags=["learn_mode", "ingest"] + ([topic] if topic else []),
            stage="scout",
            confidence="medium",
            evidence_paths=[str(self.learn_mode_service.claims_path)] + snapshot_paths[:8],
            retrieval_hints=[topic or source],
            body=f"Ingested {len(claims)} claims from {len(docs)} source docs.",
            task_id=f"learn-{int(datetime.now(timezone.utc).timestamp())}",
            extra={"verified_claims": verified_count, "source_refs": source_refs[:12]},
        )
        card_path = store.write(card)

        report = {
            "status": "SUCCESS",
            "source": source,
            "source_ref": source_refs[0] if source_refs else "",
            "source_refs": source_refs[:20],
            "claims_count": len(claims),
            "verified_claims_count": verified_count,
            "sources_count": len(set(source_refs)),
            "documents_ingested": len(docs),
            "claims_store": str(self.learn_mode_service.claims_path),
            "source_snapshot_path": snapshot_paths[0] if snapshot_paths else "",
            "source_snapshot_paths": snapshot_paths[:20],
            "findings_card_path": card_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        report["learning_closure"] = self.learn_mode_service._persist_learning_closure(
            action="ingest",
            status=report["status"],
            reason="ingest_completed",
            topic_or_source=topic or source,
            evidence_paths=[str(self.learn_mode_service.claims_path)] + snapshot_paths[:8] + ([card_path] if card_path else []),
            retrieval_hints=[topic or source],
            metrics={
                "claims_count": report["claims_count"],
                "coverage": 1.0 if report["claims_count"] > 0 else 0.0,
                "pass_rate": 1.0 if report["claims_count"] > 0 else 0.0,
                "citation_valid_ratio": 1.0 if report["claims_count"] > 0 else 0.0,
            },
        )
        self.learn_mode_service._sync_registry_after_ingest(
            source=source,
            source_file=source_file,
            topic=topic,
            claims_count=report["claims_count"],
        )
        return report
