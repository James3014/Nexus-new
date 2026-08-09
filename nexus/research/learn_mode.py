from __future__ import annotations

import json
import re
import hashlib
import os
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
from nexus.learning.learning_closure_effectiveness import (
    normalize_learning_episode,
    append_learning_episode,
    canonical_learning_episode_path,
)
from nexus.services.memory import MemoryService
from .learn.ingest_service import IngestService
from .learn.claim_service import ClaimService
from .learn.converge_service import ConvergeService
from .learn.ask_service import AskService
from .learn.phase_slo_service import PhaseSLOService
from .learn.report_service import ReportService
from .learn.phase_bridge_service import PhaseBridgeService
from .learn.benchmark_service import BenchmarkService
from .learn.source_registry_service import SourceRegistryService
from .learn.phase_slo_summary_service import PhaseSLOSummaryService
from .learn.phase_kpi_service import PhaseKPIService



@dataclass
class LearnClaim:
    claim: str
    source_url: str
    citation_span: list[int]
    topic_tags: list[str]
    created_at: str
    topic_pack: str = "general"
    evidence_strength: str = "medium"
    freshness_days: float = 0.0
    freshness_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "source_url": self.source_url,
            "citation_span": self.citation_span,
            "topic_tags": self.topic_tags,
            "created_at": self.created_at,
            "topic_pack": self.topic_pack,
            "evidence_strength": self.evidence_strength,
            "freshness_days": self.freshness_days,
            "freshness_score": self.freshness_score,
        }


class LearnModeService:
    def __init__(self, project_root: Path, run_root: Path | None = None):
        self.project_root = Path(project_root)
        self._run_root = Path(run_root) if run_root is not None else self.project_root
        self.knowledge_dir = self._run_root / ".nexus" / "knowledge"
        self.raw_dir = self.knowledge_dir / "raw_sources"
        self.claims_path = self.knowledge_dir / "learn_claims.jsonl"
        self.sources_path = self.knowledge_dir / "learn_sources.jsonl"
        self.benchmark_candidates_path = self.knowledge_dir / "learn_benchmark_candidates.jsonl"
        self.benchmark_bank_path = self.knowledge_dir / "learn_benchmark_bank.json"
        self.reports_dir = self._run_root / ".nexus" / "reports" / "learn"
        self.phase_writeback_path = self.reports_dir / "phase_writeback.jsonl"
        self.phase_slo_summary_path = self.reports_dir / "phase_slo_summary.json"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.closure_log = self.reports_dir / "learning_closure.jsonl"

        self._ingest_svc = IngestService(self)
        self._claim_svc = ClaimService(self)
        self._converge_svc = ConvergeService(self)
        self._ask_svc = AskService(self)
        self._slo_svc = PhaseSLOService(self)
        self._report_svc = ReportService(self)
        self._phase_bridge_svc = PhaseBridgeService(self)
        self._benchmark_svc = BenchmarkService(self)
        self._source_registry_svc = SourceRegistryService(self)
        self._phase_slo_summary_svc = PhaseSLOSummaryService(self)
        self._phase_kpi_svc = PhaseKPIService(self)


    PHASES: tuple[str, ...] = ("P", "X", "D", "R", "A", "C")
    INGEST_REQUIRED_FIELDS: tuple[str, ...] = (
        "status",
        "claims_count",
        "verified_claims_count",
        "sources_count",
        "documents_ingested",
    )

    def _resolve_path(self, p: str | Path) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (self.project_root / path).resolve()

    @staticmethod
    def _extract_tags(claim: str) -> list[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", claim.lower())
        return sorted(set(words[:8]))

    @staticmethod
    def _days_since(ts: str) -> float:
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400.0)
        except Exception:
            return 365.0

    @classmethod
    def _freshness_score_for(cls, ts: str) -> tuple[float, float]:
        days = cls._days_since(ts)
        if days <= 7:
            score = 1.0
        elif days <= 30:
            score = 0.85
        elif days <= 90:
            score = 0.6
        else:
            score = 0.35
        return round(days, 3), score

    @staticmethod
    def _infer_topic_pack(source_url: str, claim: str, topic_hint: str = "") -> str:
        src = source_url.lower()
        hint = (topic_hint or "").strip().lower()
        if hint:
            return re.sub(r"[^a-z0-9_-]+", "-", hint)[:48].strip("-") or "general"
        if "raw.githubusercontent.com" in src:
            m = re.search(r"githubusercontent\.com/([^/]+/[^/]+)/", src)
            if m:
                return m.group(1).replace("/", "__")
        if src.startswith("file://"):
            name = Path(src.replace("file://", "")).stem.lower()
            return re.sub(r"[^a-z0-9_-]+", "-", name)[:48].strip("-") or "local"
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", claim.lower())
        return (words[0] if words else "general")[:48]

    @staticmethod
    def _estimate_evidence_strength(source_url: str, claim: str) -> str:
        src = source_url.lower()
        text = claim.lower()
        if any(k in src for k in ["/readme", "/docs/", "/skill.md", "claude.md"]):
            return "high"
        if src.endswith((".md", ".rst", ".txt")):
            return "high"
        if src.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java")):
            return "medium"
        if any(k in text for k in ["must", "required", "supports", "uses", "provides"]):
            return "medium"
        return "low"

    @classmethod
    def _split_to_claims(cls, text: str, source_url: str, topic_hint: str = "") -> list[LearnClaim]:
        claims: list[LearnClaim] = []
        created_at = datetime.now(timezone.utc).isoformat()
        freshness_days, freshness_score = cls._freshness_score_for(created_at)
        for m in re.finditer(r"[^.!?\n][^.!?\n]{20,}[.!?]?", text):
            raw = m.group(0).strip()
            if len(raw) < 20:
                continue
            claims.append(
                LearnClaim(
                    claim=raw,
                    source_url=source_url,
                    citation_span=[m.start(), m.end()],
                    topic_tags=cls._extract_tags(raw),
                    created_at=created_at,
                    topic_pack=cls._infer_topic_pack(source_url, raw, topic_hint=topic_hint),
                    evidence_strength=cls._estimate_evidence_strength(source_url, raw),
                    freshness_days=freshness_days,
                    freshness_score=freshness_score,
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

    def _http_get_text(self, url: str, timeout: int = 10) -> str:
        with request.urlopen(url, timeout=timeout) as resp:  # nosec: B310
            return resp.read().decode("utf-8", errors="ignore")

    def _http_get_json(self, url: str, timeout: int = 10) -> dict[str, Any]:
        data = self._http_get_text(url, timeout=timeout)
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}

    @staticmethod
    def _parse_github_repo(source: str) -> tuple[str, str] | None:
        if source.startswith("repo:"):
            repo = source.replace("repo:", "", 1).strip()
            if "/" in repo:
                owner, name = repo.split("/", 1)
                return owner.strip(), name.strip().removesuffix(".git")

        m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", source)
        if m:
            return m.group(1).strip(), m.group(2).strip().removesuffix(".git")
        return None

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        header = text[:2048].lower()
        return "<html" in header or "<!doctype html" in header

    @staticmethod
    def _clean_text(text: str) -> str:
        if LearnModeService._looks_like_html(text):
            t = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
            t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.IGNORECASE)
            t = re.sub(r"<[^>]+>", " ", t)
            t = html.unescape(t)
            t = re.sub(r"\s+", " ", t)
            return t.strip()
        # markdown/text cleanup: keep structure but remove pathological whitespace.
        lines = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if ln and len(ln) >= 8]
        return "\n".join(lines)

    @staticmethod
    def _is_text_candidate(path: str) -> bool:
        p = path.lower()
        if p.endswith((".md", ".markdown", ".rst", ".txt", ".adoc")):
            return True
        if p.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")):
            return True
        return False

    @staticmethod
    def _path_priority(path: str) -> tuple[int, int]:
        p = path.lower()
        rank = 99
        if p.startswith("readme"):
            rank = 0
        elif p.startswith("docs/"):
            rank = 1
        elif "/readme" in p:
            rank = 2
        elif p.endswith(".md"):
            rank = 3
        elif p.startswith("src/") or p.startswith("lib/"):
            rank = 4
        elif p.startswith("examples/"):
            rank = 5
        return (rank, len(path))

    def _load_github_repo_documents(self, owner: str, repo: str, max_files: int = 24, max_total_chars: int = 400_000) -> list[tuple[str, str]]:
        repo_meta = self._http_get_json(f"https://api.github.com/repos/{owner}/{repo}", timeout=12)
        default_branch = str(repo_meta.get("default_branch") or "main")
        tree_api = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        tree_data = self._http_get_json(tree_api, timeout=15)
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
            if not self._is_text_candidate(path):
                continue
            candidates.append(path)

        if not candidates:
            # fallback to README only
            candidates = ["README.md"]

        candidates = sorted(set(candidates), key=self._path_priority)[:max_files]

        docs: list[tuple[str, str]] = []
        total_chars = 0
        for path in candidates:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
            try:
                payload = self._http_get_text(raw_url, timeout=12)
            except Exception:
                continue
            cleaned = self._clean_text(payload)
            if len(cleaned) < 50:
                continue
            if total_chars + len(cleaned) > max_total_chars:
                break
            total_chars += len(cleaned)
            docs.append((cleaned, raw_url))
        return docs

    def _load_source_documents(self, source: str, source_file: str | None = None) -> list[tuple[str, str]]:
        if source_file:
            src_path = self._resolve_path(source_file)
            txt = self._clean_text(src_path.read_text(encoding="utf-8"))
            return [(txt, f"file://{src_path}")]

        repo_ref = self._parse_github_repo(source)
        if repo_ref:
            owner, name = repo_ref
            docs = self._load_github_repo_documents(owner, name)
            if docs:
                return docs

        if source.startswith("http://") or source.startswith("https://"):
            payload = self._http_get_text(source, timeout=12)
            return [(self._clean_text(payload), source)]

        # keyword/repo fallback path: treat source string itself as seed text
        seed = (
            f"Learning seed for topic: {source}. "
            f"This entry captures baseline context for {source}. "
            f"Additional evidence should be ingested with --source-file or URL."
        )
        return [(seed, f"keyword://{source}")]

    def _append_claims(self, claims: list[LearnClaim]) -> None:
        existing = {self._claim_key(c) for c in self.load_claims()}
        with self.claims_path.open("a", encoding="utf-8") as f:
            for c in claims:
                key = self._claim_key(c)
                if key in existing:
                    continue
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
                existing.add(key)

    def _persist_learning_closure(
        self,
        *,
        action: str,
        status: str,
        reason: str,
        topic_or_source: str,
        evidence_paths: list[str],
        retrieval_hints: list[str],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Unified learn closure:
        1) MemPalace verify
        2) FindingsMemory write (LanceDB sync via repository)
        3) MemPalace sync + arweave tx
        4) skill_outcome_events writeback
        5) policy_memory route-phase weight sync
        """
        closure: dict[str, Any] = {
            "action": action,
            "status": status,
            "reason": reason,
            "mempalace_verified": False,
            "memory_written": False,
            "lancedb_synced": False,
            "mempalace_sync_status": "SKIPPED",
            "skill_outcome_written": False,
            "policy_memory_synced": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if os.environ.get("NEXUS_LEARN_CLOSURE_WRITEBACK", "").strip().lower() in {"0", "false", "no", "off"}:
            closure["writeback_disabled"] = True
            closure["reason"] = f"{reason} | writeback_disabled"
            return closure
        task_id = f"learn-{action}-{int(time.time())}"
        try:
            card = FindingsCard(
                kind="episodes",
                title=f"Learn {action}: {status}",
                task_id=task_id,
                tags=["learn_mode", action, status.lower()],
                stage="analysis" if action == "converge" else "scout",
                confidence="high" if status == "SUCCESS" else "medium",
                evidence_paths=evidence_paths[:12],
                retrieval_hints=list(dict.fromkeys([topic_or_source] + retrieval_hints))[:8],
                body=(
                    f"Action: {action}\n"
                    f"Status: {status}\n"
                    f"Reason: {reason}\n"
                    f"Topic/Source: {topic_or_source}\n"
                    f"Metrics: {json.dumps(metrics, ensure_ascii=False)}\n"
                ),
                extra={"closure_kind": "learn_mode", "action": action, "metrics": metrics},
            )
            palace = MemPalace(str(self.project_root))
            clean = palace.verify([card.to_dict()])
            if not clean:
                closure["reason"] = f"{reason} | mempalace_rejected"
                self._append_closure_log(closure)
                return closure
            closure["mempalace_verified"] = True

            store = FindingsMemoryStore(self.project_root)
            write_path = store.write(FindingsCard.from_dict(clean[0]))
            closure["memory_written"] = True
            closure["memory_path"] = write_path
            closure["lancedb_synced"] = True

            sync_info = palace.sync()
            closure["mempalace_sync_status"] = str(sync_info.get("status", "UNKNOWN"))
            closure["mempalace_sync"] = sync_info
            closure["arweave_tx_id"] = palace.trigger_arweave_distillation(clean[0])

            pass_rate = float(metrics.get("self_question_pass_rate", metrics.get("pass_rate", 0.0)) or 0.0)
            claims_count = int(metrics.get("claims_count", 0) or 0)
            outcome = build_outcome_event(
                OutcomePayload(
                    task_id=task_id,
                    phase="LEARN",
                    decision_id=f"{action}-{int(time.time())}",
                    skill_id=f"learn:{action}",
                    passed=status == "SUCCESS",
                    repair_success=status == "SUCCESS",
                    proof_present=claims_count > 0,
                    regression_pass_rate=pass_rate,
                    pattern_reuse=float(metrics.get("coverage", 0.0) or 0.0),
                    next_run_hit=1.0 if status == "SUCCESS" else 0.0,
                    metadata={"status": status, "source": "learn.mode", "reason": reason},
                )
            )
            outcome_path = append_skill_outcome_event(self.project_root, outcome)
            closure["skill_outcome_written"] = True
            closure["skill_outcome_path"] = str(outcome_path)

            memory = MemoryService(str(self.project_root))
            # Keep route-weight updates conservative and bounded.
            pr = max(0.0, min(1.0, pass_rate))
            cv = max(0.0, min(1.0, float(metrics.get("coverage", 0.0) or 0.0)))
            weights = {
                "P": max(0.2, cv),
                "X": max(0.2, pr),
                "D": max(0.2, (pr + cv) / 2.0),
                "R": max(0.2, 1.0 if status == "SUCCESS" else 0.3),
                "A": max(0.2, float(metrics.get("citation_valid_ratio", 0.0) or cv)),
                "C": max(0.2, 1.0 if status == "SUCCESS" else 0.3),
            }
            memory.sync_route_phase_weights(
                weights=weights,
                cycle_status=status,
                fault_hash=topic_or_source[:120],
            )
            closure["policy_memory_synced"] = True
            closure["route_phase_weights"] = weights

        except Exception as exc:
            closure["mempalace_sync_status"] = "ERROR"
            closure["error"] = str(exc)

        self._append_closure_log(closure)
        return closure

    def _append_closure_log(self, closure: dict[str, Any]) -> None:
        # Keep the historical LearnMode projection, but make the canonical
        # episode envelope the only effectiveness authority.
        task_id = str(closure.get("task_id") or f"learn-{closure.get('action', 'unknown')}-{closure.get('topic_or_source', 'unknown')}")
        evidence = {
            "status": str(closure.get("status", "")),
            "verifier_status": "pass" if closure.get("mempalace_verified") else "missing",
            "receipt": closure.get("skill_outcome_path", ""),
        }
        write_ok = bool(
            closure.get("mempalace_verified")
            and closure.get("memory_written")
            and closure.get("skill_outcome_written")
        )
        qualification = dict(closure.get("qualification") or {})
        episode = normalize_learning_episode(
            task_id=task_id,
            attempt_id=str(closure.get("attempt_id") or closure.get("timestamp", "")),
            action_id=str(closure.get("action", "unknown")),
            source="learn_mode",
            terminal_outcome="SUCCEEDED" if str(closure.get("status", "")).upper() == "SUCCESS" else "FAILED",
            terminal_evidence=evidence,
            retrieved_lesson_ids=tuple(closure.get("retrieved_lesson_ids") or ()),
            applied_lesson_ids=tuple(closure.get("applied_lesson_ids") or ()),
            qualification=qualification,
            lesson_disposition=str(closure.get("lesson_disposition") or "shadow"),
            learning_write_succeeded=write_ok,
        )
        closure.update({
            "task_id": task_id,
            "source_schema": episode["schema"],
            "episode_id": episode["episode_id"],
            "idempotency_key": episode["idempotency_key"],
            "stages": episode["stages"],
            "learning_write_succeeded": write_ok,
        })
        if not append_learning_episode(canonical_learning_episode_path(self.project_root), episode):
            closure["learning_episode_write_failed"] = True
        self.closure_log.parent.mkdir(parents=True, exist_ok=True)
        with self.closure_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(closure, ensure_ascii=False) + "\n")

    def _decide_learn_phase_route(self, *, phase: str, topic: str, metrics: dict[str, Any]) -> dict[str, Any]:
        return self._phase_bridge_svc._decide_learn_phase_route(
            phase=phase,
            topic=topic,
            metrics=metrics,
        )

    def _phase_writeback_policy(self, *, phase: str, route: dict[str, Any]) -> dict[str, Any]:
        return self._phase_bridge_svc._phase_writeback_policy(phase=phase, route=route)

    def _append_phase_writeback(self, payload: dict[str, Any]) -> None:
        self._phase_bridge_svc._append_phase_writeback(payload)

    def sync_phase_learning_closure(
        self,
        *,
        topic: str,
        metrics: dict[str, Any],
        phase_status: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._phase_bridge_svc.sync_phase_learning_closure(
            topic=topic,
            metrics=metrics,
            phase_status=phase_status,
        )

    def build_phase_slo_report(self, *, window: int = 300) -> dict[str, Any]:
        return self._slo_svc.build_phase_slo_report(window=window)

    def read_phase_slo_summary(self) -> dict[str, Any]:
        return self._phase_slo_summary_svc.read_phase_slo_summary()

    def build_phase_kpi_report(self, *, window: int = 300) -> dict[str, Any]:
        return self._phase_kpi_svc.build_phase_kpi_report(window=window)

    def _load_source_registry(self) -> list[dict[str, Any]]:
        return self._source_registry_svc.load_source_registry()

    def _write_source_registry(self, rows: list[dict[str, Any]]) -> None:
        self._source_registry_svc.write_source_registry(rows)

    def _append_benchmark_candidate(
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
        self._benchmark_svc.append_benchmark_candidate(
            topic=topic,
            question=question,
            actual_status=actual_status,
            reason=reason,
            token_coverage=token_coverage,
            topic_pack_selected=topic_pack_selected,
            conflicts=conflicts,
        )

    def _load_benchmark_candidates(self) -> list[dict[str, Any]]:
        return self._benchmark_svc.load_benchmark_candidates()

    @staticmethod
    def _normalize_question(question: str) -> str:
        return BenchmarkService.normalize_question(question)

    def curate_benchmark_bank(
        self,
        *,
        topic: str = "",
        max_questions: int = 40,
        min_occurrences: int = 1,
    ) -> dict[str, Any]:
        return self._benchmark_svc.curate_benchmark_bank(
            topic=topic,
            max_questions=max_questions,
            min_occurrences=min_occurrences,
        )

    def _sync_registry_after_ingest(self, *, source: str, source_file: str | None, topic: str, claims_count: int) -> None:
        self._source_registry_svc.sync_registry_after_ingest(
            source=source,
            source_file=source_file,
            topic=topic,
            claims_count=claims_count,
        )

    def register_source(
        self,
        *,
        topic: str,
        source: str,
        refresh_after_days: int = 14,
        priority: str = "medium",
        source_file: str | None = None,
    ) -> dict[str, Any]:
        return self._source_registry_svc.register_source(
            topic=topic,
            source=source,
            refresh_after_days=refresh_after_days,
            priority=priority,
            source_file=source_file,
        )

    def _source_due(self, row: dict[str, Any]) -> bool:
        return self._source_registry_svc.source_due(row)

    def refresh_sources(
        self,
        *,
        topic: str = "",
        due_only: bool = True,
        pass_threshold: float = 0.6,
        question_count: int = 5,
    ) -> dict[str, Any]:
        return self._source_registry_svc.refresh_sources(
            topic=topic,
            due_only=due_only,
            pass_threshold=pass_threshold,
            question_count=question_count,
        )

    def build_refresh_plan(
        self,
        *,
        topic: str = "",
        due_within_days: int = 0,
    ) -> dict[str, Any]:
        return self._source_registry_svc.build_refresh_plan(
            topic=topic,
            due_within_days=due_within_days,
        )

    def _enrich_claim(self, claim: dict[str, Any]) -> dict[str, Any]:
        out = dict(claim)
        created_at = str(out.get("created_at") or datetime.now(timezone.utc).isoformat())
        freshness_days, freshness_score = self._freshness_score_for(created_at)
        out["created_at"] = created_at
        out["topic_pack"] = out.get("topic_pack") or self._infer_topic_pack(
            str(out.get("source_url", "")),
            str(out.get("claim", "")),
        )
        out["evidence_strength"] = out.get("evidence_strength") or self._estimate_evidence_strength(
            str(out.get("source_url", "")),
            str(out.get("claim", "")),
        )
        out["freshness_days"] = float(out.get("freshness_days", freshness_days) or freshness_days)
        out["freshness_score"] = float(out.get("freshness_score", freshness_score) or freshness_score)
        return out

    def _claim_strength_weight(self, claim: dict[str, Any]) -> float:
        strength = str(claim.get("evidence_strength", "medium")).lower()
        return {"high": 1.0, "medium": 0.75, "low": 0.45}.get(strength, 0.6)

    def _claim_pack_score(self, claim: dict[str, Any], topic: str, question: str) -> float:
        hay = " ".join(
            [
                str(claim.get("topic_pack", "")),
                " ".join(claim.get("topic_tags", []) or []),
                str(claim.get("source_url", "")),
            ]
        ).lower()
        score = 0.0
        for tok in self._extract_tokens(f"{topic} {question}"):
            if tok in hay:
                score += 1.0
        return score

    def _route_topic_pack(self, claims: list[dict[str, Any]], topic: str, question: str) -> tuple[str, list[dict[str, Any]]]:
        if not claims:
            return "general", []
        pack_scores: dict[str, float] = {}
        for claim in claims:
            pack = str(claim.get("topic_pack", "general"))
            pack_scores[pack] = pack_scores.get(pack, 0.0) + self._claim_pack_score(claim, topic, question)
        selected_pack = max(pack_scores.items(), key=lambda item: item[1])[0] if pack_scores else "general"
        routed = [c for c in claims if str(c.get("topic_pack", "general")) == selected_pack]
        return selected_pack, (routed or claims)

    @staticmethod
    def _topic_pack_candidates(claims: list[dict[str, Any]]) -> list[str]:
        return sorted({str(c.get("topic_pack", "general")) for c in claims})

    @staticmethod
    def _topic_pack_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    @classmethod
    def _topic_scoped_claims(cls, claims: list[dict[str, Any]], topic: str) -> list[dict[str, Any]]:
        topic_key = cls._topic_pack_key(topic)
        return [
            c
            for c in claims
            if str(c.get("topic_pack", "general")) == topic
            or cls._topic_pack_key(str(c.get("topic_pack", "general"))) == topic_key
        ]

    def _route_claims_for_topic(
        self,
        claims: list[dict[str, Any]],
        topic: str,
        question: str,
        *,
        allow_cross_pack: bool,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        candidates = self._topic_pack_candidates(claims)
        scoped_claims = self._topic_scoped_claims(claims, topic)
        if scoped_claims:
            return (
                topic,
                scoped_claims,
                {
                    "routing_mode": "strict_topic",
                    "topic_pack_selected": topic,
                    "topic_pack_candidates": candidates,
                    "cross_pack_fallback_used": False,
                },
            )
        if allow_cross_pack:
            selected_pack, routed_claims = self._route_topic_pack(claims, topic, question)
            return (
                selected_pack,
                routed_claims,
                {
                    "routing_mode": "cross_pack",
                    "topic_pack_selected": selected_pack,
                    "topic_pack_candidates": candidates,
                    "cross_pack_fallback_used": True,
                },
            )
        return (
            topic,
            [],
            {
                "routing_mode": "strict_topic",
                "topic_pack_selected": topic,
                "topic_pack_candidates": candidates,
                "cross_pack_fallback_used": False,
            },
        )

    def _claim_polarity(self, text: str) -> str:
        lowered = text.lower()
        negative_patterns = [" does not ", " do not ", " cannot ", " can't ", " never ", " no "]
        return "negative" if any(p in f" {lowered} " for p in negative_patterns) else "positive"

    def _find_conflicts(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for i, left in enumerate(claims):
            ltoks = self._extract_tokens(str(left.get("claim", "")))
            if not ltoks:
                continue
            for right in claims[i + 1 :]:
                rtoks = self._extract_tokens(str(right.get("claim", "")))
                if not rtoks:
                    continue
                overlap = ltoks & rtoks
                union = ltoks | rtoks
                overlap_ratio = 0.0 if not union else len(overlap) / len(union)
                if overlap_ratio < 0.55:
                    continue
                if self._claim_polarity(str(left.get("claim", ""))) == self._claim_polarity(str(right.get("claim", ""))):
                    continue
                conflicts.append(
                    {
                        "left": {
                            "claim": left.get("claim", ""),
                            "source_url": left.get("source_url", ""),
                            "citation_span": left.get("citation_span", []),
                        },
                        "right": {
                            "claim": right.get("claim", ""),
                            "source_url": right.get("source_url", ""),
                            "citation_span": right.get("citation_span", []),
                        },
                        "conflict_score": round(overlap_ratio, 4),
                    }
                )
        return conflicts

    _claims_cache = None
    _claims_mtime = 0

    def load_claims(self) -> list[dict[str, Any]]:
        if not self.claims_path.exists():
            return []
            
        current_mtime = self.claims_path.stat().st_mtime
        if self.__class__._claims_cache is None or current_mtime > self.__class__._claims_mtime:
            out: list[dict[str, Any]] = []
            for line in self.claims_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(self._enrich_claim(json.loads(line)))
                except json.JSONDecodeError:
                    continue
            self.__class__._claims_cache = out
            self.__class__._claims_mtime = current_mtime
            
        return self.__class__._claims_cache

    def _validate_ingest_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        missing = [field for field in self.INGEST_REQUIRED_FIELDS if field not in payload]
        if missing:
            raise RuntimeError(f"learn_ingest_contract_violation: missing={missing}")
        return payload

    def ingest(self, source: str, source_file: str | None = None, topic: str = "") -> dict[str, Any]:
        payload = self._ingest_svc.ingest(source, source_file, topic)
        if not isinstance(payload, dict):
            raise RuntimeError("learn_ingest_contract_violation: payload_must_be_dict")
        return self._validate_ingest_payload(payload)

    def _extract_tokens(self, topic: str) -> set[str]:
        raw = set(re.findall(r"[A-Za-z0-9_-]+", topic.lower()))
        stop = {
            "what",
            "how",
            "why",
            "when",
            "where",
            "which",
            "explain",
            "describe",
            "about",
            "with",
            "and",
            "the",
            "for",
            "that",
            "this",
            "are",
            "is",
            "does",
            "did",
            "do",
            "repo",
            "repository",
            "project",
            "plan",
            "implement",
            "implements",
            "implementation",
            "workflow",
        }
        tokens = {self._normalize_token(t) for t in raw if len(t) >= 3 and t not in stop}
        return {t for t in tokens if t} or {"general"}

    @staticmethod
    def _normalize_token(tok: str) -> str:
        t = tok.lower().strip("-_ ")
        synonyms = {
            "installation": "install",
            "installed": "install",
            "installing": "install",
            "organization": "organize",
            "organised": "organize",
            "organized": "organize",
            "rules": "rule",
            "guidelines": "guideline",
            "structures": "structure",
            "methods": "method",
        }
        if t in synonyms:
            t = synonyms[t]
        for suf in ("ing", "tion", "ions", "ed", "es", "s"):
            if len(t) > 5 and t.endswith(suf):
                t = t[: -len(suf)]
                break
        return t

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
        swarm_mode: bool = True,
        swarm_max_parallel: int = 3,
        per_source_timeout_sec: int = 25,
    ) -> dict[str, Any]:
        claims = self.load_claims()
        questions = self._build_question_set(topic, question_count=question_count)
        rounds_used = 0
        discovered_sources: list[str] = []
        round_activity: list[dict[str, Any]] = []
        answered_q, unresolved_q = [], questions

        def _ingest_one(src: str) -> dict[str, Any]:
            started = time.time()
            try:
                rep = self.ingest(source=src, source_file=None, topic=topic)
                return {
                    "source": src,
                    "ok": True,
                    "claims_count": int(rep.get("claims_count", 0)),
                    "documents_ingested": int(rep.get("documents_ingested", 0)),
                    "elapsed_sec": round(time.time() - started, 4),
                }
            except Exception as exc:
                return {
                    "source": src,
                    "ok": False,
                    "error": str(exc),
                    "elapsed_sec": round(time.time() - started, 4),
                }

        while rounds_used < max_rounds:
            rounds_used += 1
            claims = self.load_claims()
            answered_q, unresolved_q = self._answer_questions(questions, claims)
            pass_rate = 0.0 if not questions else len(answered_q) / len(questions)
            converged = pass_rate >= pass_threshold
            if converged or not auto_research or rounds_used >= max_rounds:
                break

            sources = self._discover_sources(topic, max_sources=max_sources_per_round)
            discovered_sources.extend(sources)
            round_rec = {
                "round": rounds_used,
                "sources_discovered": sources,
                "swarm_mode": bool(swarm_mode),
                "ingest_results": [],
            }
            if swarm_mode and sources:
                max_workers = max(1, min(swarm_max_parallel, len(sources)))
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                    fut_map = {pool.submit(_ingest_one, src): src for src in sources}
                    for fut in concurrent.futures.as_completed(fut_map, timeout=max(1, per_source_timeout_sec) * len(sources)):
                        src = fut_map[fut]
                        try:
                            rec = fut.result(timeout=max(1, per_source_timeout_sec))
                        except Exception as exc:
                            rec = {"source": src, "ok": False, "error": f"swarm_timeout_or_error:{exc}"}
                        round_rec["ingest_results"].append(rec)
            else:
                for src in sources:
                    round_rec["ingest_results"].append(_ingest_one(src))
            round_activity.append(round_rec)

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
            "round_activity": round_activity,
            "swarm": {
                "enabled": bool(swarm_mode),
                "max_parallel": int(max(1, swarm_max_parallel)),
                "per_source_timeout_sec": int(max(1, per_source_timeout_sec)),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        report["learning_closure"] = self._persist_learning_closure(
            action="converge",
            status="SUCCESS" if converged else "PARTIAL",
            reason="converged" if converged else "insufficient_evidence",
            topic_or_source=topic,
            evidence_paths=[str(self.claims_path), str(self.reports_dir / "converge_report.json")],
            retrieval_hints=sorted(self._extract_tokens(topic)),
            metrics={
                "claims_count": report["claims_total"],
                "coverage": report["coverage"],
                "self_question_pass_rate": report["self_question_pass_rate"],
                "citation_valid_ratio": round(0.0 if report["claims_total"] == 0 else report["claims_matched"] / max(1, report["claims_total"]), 4),
            },
        )
        phase_status = {
            "P": "SUCCESS",
            "X": "SUCCESS" if report["discovered_sources"] else "PARTIAL",
            "D": "SUCCESS" if report["claims_total"] > 0 else "PARTIAL",
            "R": "SUCCESS" if report["converged"] else "PARTIAL",
            "A": "SUCCESS" if report["claims_matched"] > 0 else "PARTIAL",
            "C": "SUCCESS" if bool((report.get("learning_closure") or {}).get("mempalace_verified")) else "PARTIAL",
        }
        report["phase_learning_bridge"] = self.sync_phase_learning_closure(
            topic=topic,
            metrics={
                "coverage": report["coverage"],
                "self_question_pass_rate": report["self_question_pass_rate"],
                "citation_valid_ratio": round(0.0 if report["claims_total"] == 0 else report["claims_matched"] / max(1, report["claims_total"]), 4),
                "stale_claims_count": 0,
                "conflict_count": 0,
            },
            phase_status=phase_status,
        )
        return report

    def ask(
        self,
        topic: str,
        question: str,
        top_k: int = 5,
        min_evidence: int = 1,
        min_token_coverage: float | None = None,
        max_staleness_days: int | None = 180,
        allow_cross_pack: bool = False,
    ) -> dict[str, Any]:
        claims = self.load_claims()
        selected_pack, routed_claims, routing_meta = self._route_claims_for_topic(
            claims,
            topic,
            question,
            allow_cross_pack=allow_cross_pack,
        )
        tokens = self._extract_tokens(question)
        if not tokens:
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason="empty_question",
                topic_or_source=topic,
                evidence_paths=[str(self.claims_path)],
                retrieval_hints=[],
                metrics={"claims_count": 0, "coverage": 0.0, "pass_rate": 0.0, "citation_valid_ratio": 0.0},
            )
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": "empty_question",
                "learning_closure": closure,
                **routing_meta,
            }

        if not routed_claims:
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason="topic_no_claims",
                topic_or_source=topic,
                evidence_paths=[str(self.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": 0,
                    "coverage": 0.0,
                    "pass_rate": 0.0,
                    "citation_valid_ratio": 0.0,
                    **routing_meta,
                },
            )
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": "topic_no_claims",
                "token_coverage": 0.0,
                "learning_closure": closure,
                **routing_meta,
            }

        filtered_claims = [
            c for c in routed_claims if max_staleness_days is None or float(c.get("freshness_days", 0.0)) <= float(max_staleness_days)
        ]
        scored: list[tuple[float, dict[str, Any], set[str]]] = []
        for c in filtered_claims:
            if not self._is_valid_citation(c):
                continue
            blob = f"{c.get('claim', '')} {' '.join(c.get('topic_tags', []))}".lower()
            words = {self._normalize_token(w) for w in re.findall(r"[a-z0-9_-]+", blob)}
            score = 0.0
            token_hits: set[str] = set()
            for t in tokens:
                if t in words:
                    score += 2.0
                    token_hits.add(t)
                elif any(w.startswith(t) or t.startswith(w) for w in words if len(w) >= 4):
                    score += 1.0
                    token_hits.add(t)
            if score > 0:
                score = (
                    score
                    + self._claim_strength_weight(c)
                    + float(c.get("freshness_score", 0.0))
                )
                scored.append((score, c, token_hits))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Greedy coverage-first selector: prioritize claims that add new token coverage,
        # then break ties by base score.
        best_pairs: list[tuple[dict[str, Any], set[str]]] = []
        covered_tokens: set[str] = set()
        pool = [(score, c, hits) for score, c, hits in scored if self._is_valid_citation(c)]
        while pool and len(best_pairs) < top_k:
            best_idx = 0
            best_gain = -1
            best_score = -1
            for i, (score, _, hits) in enumerate(pool):
                gain = len(hits - covered_tokens)
                if gain > best_gain or (gain == best_gain and score > best_score):
                    best_idx = i
                    best_gain = gain
                    best_score = score
            score, c, hits = pool.pop(best_idx)
            if not best_pairs and best_gain <= 0 and score <= 0:
                break
            best_pairs.append((c, hits))
            covered_tokens.update(hits)

        best = [c for c, _ in best_pairs]
        token_coverage = 0.0 if not tokens else len(covered_tokens) / len(tokens)
        if min_token_coverage is None:
            if len(tokens) >= 5:
                min_token_coverage = 0.6
            elif len(tokens) >= 3:
                min_token_coverage = 0.5
            else:
                min_token_coverage = 0.5

        conflicts = self._find_conflicts(best)
        if conflicts:
            self._append_benchmark_candidate(
                topic=topic,
                question=question,
                actual_status="CONFLICT",
                reason="conflicting_cited_claims",
                token_coverage=token_coverage,
                topic_pack_selected=selected_pack,
                conflicts=conflicts,
            )
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason="conflicting_cited_claims",
                topic_or_source=topic,
                evidence_paths=[str(self.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": len(best),
                    "coverage": min(1.0, len(best) / max(1, top_k)),
                    "pass_rate": 0.0,
                    "citation_valid_ratio": 1.0 if best else 0.0,
                    "token_coverage": round(token_coverage, 4),
                    "conflict_count": len(conflicts),
                },
            )
            return {
                "status": "CONFLICT",
                "answer": "CONFLICT",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": "conflicting_cited_claims",
                "token_coverage": round(token_coverage, 4),
                "conflicts": conflicts,
                "learning_closure": closure,
                **routing_meta,
            }

        if len(best) < max(1, min_evidence) or token_coverage < float(min_token_coverage):
            unknown_reason = "insufficient_cited_claims" if len(best) < max(1, min_evidence) else "insufficient_token_coverage"
            self._append_benchmark_candidate(
                topic=topic,
                question=question,
                actual_status="UNKNOWN",
                reason=unknown_reason,
                token_coverage=token_coverage,
                topic_pack_selected=selected_pack,
            )
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason=unknown_reason,
                topic_or_source=topic,
                evidence_paths=[str(self.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": len(best),
                    "coverage": min(1.0, len(best) / max(1, top_k)),
                    "pass_rate": 0.0,
                    "citation_valid_ratio": 1.0 if best else 0.0,
                    "token_coverage": round(token_coverage, 4),
                    "topic_pack_selected": selected_pack,
                },
            )
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": unknown_reason,
                "token_coverage": round(token_coverage, 4),
                "learning_closure": closure,
                **routing_meta,
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
            "question": question,
            "answer": "\n".join(lines),
            "citations": citations,
            "claims_used": len(best),
            "min_evidence_required": max(1, min_evidence),
            "token_coverage": round(token_coverage, 4),
            **routing_meta,
            "learning_closure": self._persist_learning_closure(
                action="ask",
                status="SUCCESS",
                reason="answered_with_citations",
                topic_or_source=topic,
                evidence_paths=[str(self.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": len(best),
                    "coverage": min(1.0, len(best) / max(1, top_k)),
                    "pass_rate": 1.0,
                    "citation_valid_ratio": 1.0,
                    "topic_pack_selected": selected_pack,
                },
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def build_report(
        self,
        topic: str = "",
        question_count: int = 5,
        pass_threshold: float = 0.6,
    ) -> dict[str, Any]:
        return self._report_svc.build_report(
            topic=topic,
            question_count=question_count,
            pass_threshold=pass_threshold,
        )
