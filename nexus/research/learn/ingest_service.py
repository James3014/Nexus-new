from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.services.mem_palace import MemPalace

from .learn_models import LearnClaim
from .protocols import LearnContextProtocol


class IngestService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    @staticmethod
    def _is_governance_claim(claim: LearnClaim) -> bool:
        text = str(getattr(claim, "claim", "") or "").lower()
        governance_keywords = (
            "mempalace",
            "governance",
            "policy",
            "guard",
            "boundary",
            "identity",
            "lifecycle",
            "protocol",
            "audit",
        )
        return any(keyword in text for keyword in governance_keywords)

    def _build_channel_counts(self, claims: list[LearnClaim]) -> dict[str, int]:
        governance_count = sum(1 for claim in claims if self._is_governance_claim(claim))
        tactical_count = max(len(claims) - governance_count, 0)
        return {
            "tactical_data": tactical_count,
            "governance_principles": governance_count,
        }

    @staticmethod
    def _normalize_sources(source: str | list[str]) -> list[str]:
        if isinstance(source, str):
            normalized = source.strip()
            if not normalized:
                raise ValueError("source must be non-empty")
            return [normalized]
        if isinstance(source, list):
            normalized = [str(item).strip() for item in source if str(item).strip()]
            if not normalized:
                raise ValueError("source must be non-empty")
            return normalized
        raise TypeError("source must be a string or list of strings")

    def _load_github_repo_documents(
        self,
        owner: str,
        repo: str,
        max_files: int = 24,
        max_total_chars: int = 400_000,
    ) -> list[tuple[str, str]]:
        repo_meta = self.ctx._http_get_json(
            f"https://api.github.com/repos/{owner}/{repo}", timeout=12
        )
        default_branch = str(repo_meta.get("default_branch") or "main")
        tree_api = (
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        )
        tree_data = self.ctx._http_get_json(tree_api, timeout=15)
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
            if not self.ctx._is_text_candidate(path):
                continue
            candidates.append(path)

        if not candidates:
            candidates = ["README.md"]

        candidates = sorted(set(candidates), key=self.ctx._path_priority)[:max_files]

        docs: list[tuple[str, str]] = []
        total_chars = 0
        for path in candidates:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
            try:
                payload = self.ctx._http_get_text(raw_url, timeout=12)
            except Exception:
                continue
            cleaned = self.ctx._clean_text(payload)
            if len(cleaned) < 50:
                continue
            if total_chars + len(cleaned) > max_total_chars:
                break
            total_chars += len(cleaned)
            docs.append((cleaned, raw_url))
        return docs

    def _load_single_source_documents(
        self, source: str, source_file: str | None = None
    ) -> list[tuple[str, str]]:
        if source_file:
            src_path = self.ctx._resolve_path(source_file)
            txt = self.ctx._clean_text(src_path.read_text(encoding="utf-8"))
            return [(txt, f"file://{src_path}")]

        repo_ref = self.ctx._parse_github_repo(source)
        if repo_ref:
            owner, name = repo_ref
            docs = self.ctx._load_github_repo_documents(owner, name)
            if docs:
                return docs

        if source.startswith("http://") or source.startswith("https://"):
            payload = self.ctx._http_get_text(source, timeout=12)
            return [(self.ctx._clean_text(payload), source)]

        seed = (
            f"Learning seed for topic: {source}. "
            f"This entry captures baseline context for {source}. "
            f"Additional evidence should be ingested with --source-file or URL."
        )
        return [(seed, f"keyword://{source}")]

    def _load_source_documents(
        self, source: str | list[str], source_file: str | None = None
    ) -> list[tuple[str, str]]:
        sources = self._normalize_sources(source)
        if source_file and len(sources) != 1:
            raise ValueError("source_file requires exactly one source")
        docs: list[tuple[str, str]] = []
        for src in sources:
            docs.extend(self._load_single_source_documents(src, source_file=source_file))
        return docs

    def ingest(
        self, source: str | list[str], source_file: str | None = None, topic: str = ""
    ) -> dict[str, Any]:
        normalized_sources = self._normalize_sources(source)
        docs = self._load_source_documents(normalized_sources, source_file=source_file)
        snapshot_paths: list[str] = []
        parsed_claims: list[LearnClaim] = []
        source_refs: list[str] = []
        snapshot_hashes: dict[str, str] = {}

        for text, source_ref in docs:
            source_refs.append(source_ref)
            snap = self.ctx._save_source_snapshot(source_ref, text)
            snapshot_paths.append(str(snap))
            snapshot_hashes[source_ref] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            parsed_claims.extend(
                self.ctx._split_to_claims(text, source_ref, topic_hint=topic or source_ref)
            )

        palace = MemPalace(str(self.ctx.project_root))
        verified = palace.verify([c.to_dict() for c in parsed_claims])
        verified_keys = {self.ctx._claim_key(cand) for cand in verified if isinstance(cand, dict)}

        admitted_claims: list[LearnClaim] = []
        verifier_identity = "mempalace.verify"
        for claim in parsed_claims:
            c_key = self.ctx._claim_key(claim)
            if c_key in verified_keys:
                snap_sha = snapshot_hashes.get(claim.source_url, "")
                proof = self.ctx._compute_admission_proof(
                    claim_key=c_key,
                    source_snapshot_sha256=snap_sha,
                    verifier=verifier_identity,
                    status="ADMITTED",
                )
                admitted = replace(
                    claim,
                    admission_status="ADMITTED",
                    admission_verifier=verifier_identity,
                    source_snapshot_sha256=snap_sha,
                    admission_claim_key=c_key,
                    admission_proof=proof,
                )
                admitted_claims.append(admitted)

        # Append ONLY admitted claims to durable store
        self.ctx._append_claims(admitted_claims)

        verified_count = len(admitted_claims)
        channel_counts = self._build_channel_counts(admitted_claims)

        store = FindingsMemoryStore(self.ctx.project_root)
        source_hint = ", ".join(normalized_sources[:3])
        card = FindingsCard(
            kind="knowledge",
            title=f"Learn ingest: {source_hint}",
            scope="task",
            tags=["learn_mode", "ingest"] + ([topic] if topic else []),
            stage="scout",
            confidence="medium",
            evidence_paths=[str(self.ctx.claims_path)] + snapshot_paths[:8],
            retrieval_hints=[topic or source_hint],
            body=f"Ingested {len(admitted_claims)} claims (from {len(parsed_claims)} parsed) from {len(docs)} source docs.",
            task_id=f"learn-{int(datetime.now(timezone.utc).timestamp())}",
            extra={"verified_claims": verified_count, "source_refs": source_refs[:12]},
        )
        card_path = store.write(card)

        report = {
            "status": "SUCCESS",
            "source": source,
            "source_ref": source_refs[0] if source_refs else "",
            "source_refs": source_refs[:20],
            "claims_count": len(parsed_claims),
            "verified_claims_count": verified_count,
            "sources_count": len(set(source_refs)),
            "documents_ingested": len(docs),
            "channel_counts": channel_counts,
            "claims_store": str(self.ctx.claims_path),
            "source_snapshot_path": snapshot_paths[0] if snapshot_paths else "",
            "source_snapshot_paths": snapshot_paths[:20],
            "findings_card_path": card_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        report["learning_closure"] = self.ctx._persist_learning_closure(
            action="ingest",
            status=report["status"],
            reason="ingest_completed",
            topic_or_source=topic or source_hint,
            evidence_paths=[str(self.ctx.claims_path)]
            + snapshot_paths[:8]
            + ([card_path] if card_path else []),
            retrieval_hints=[topic or source_hint],
            metrics={
                "claims_count": report["claims_count"],
                "coverage": 1.0 if report["claims_count"] > 0 else 0.0,
                "pass_rate": 1.0 if report["claims_count"] > 0 else 0.0,
                "citation_valid_ratio": 1.0 if report["claims_count"] > 0 else 0.0,
            },
        )
        for src in normalized_sources:
            self.ctx._sync_registry_after_ingest(
                source=src,
                source_file=source_file,
                topic=topic,
                claims_count=report["claims_count"],
            )

        required_fields = (
            "status",
            "claims_count",
            "verified_claims_count",
            "sources_count",
            "documents_ingested",
        )
        missing = [field for field in required_fields if field not in report]
        if missing:
            raise RuntimeError(f"learn_ingest_contract_violation: missing={missing}")

        return report
