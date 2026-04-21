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
import html
import time
import concurrent.futures

from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.services.mem_palace import MemPalace
from nexus.core.skill_outcomes import OutcomePayload, build_outcome_event, append_skill_outcome_event
from nexus.services.memory import MemoryService
from .learn.ingest_service import IngestService
from .learn.claim_service import ClaimService
from .learn.converge_service import ConvergeService
from .learn.ask_service import AskService
from .learn.phase_slo_service import PhaseSLOService



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
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.knowledge_dir = self.project_root / ".nexus" / "knowledge"
        self.raw_dir = self.knowledge_dir / "raw_sources"
        self.claims_path = self.knowledge_dir / "learn_claims.jsonl"
        self.sources_path = self.knowledge_dir / "learn_sources.jsonl"
        self.benchmark_candidates_path = self.knowledge_dir / "learn_benchmark_candidates.jsonl"
        self.benchmark_bank_path = self.knowledge_dir / "learn_benchmark_bank.json"
        self.reports_dir = self.project_root / ".nexus" / "reports" / "learn"
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


    PHASES: tuple[str, ...] = ("P", "X", "D", "R", "A", "C")

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
        self.closure_log.parent.mkdir(parents=True, exist_ok=True)
        with self.closure_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(closure, ensure_ascii=False) + "\n")

    def _decide_learn_phase_route(self, *, phase: str, topic: str, metrics: dict[str, Any]) -> dict[str, Any]:
        phase = str(phase or "").upper()
        coverage = float(metrics.get("coverage", 0.0) or 0.0)
        pass_rate = float(metrics.get("self_question_pass_rate", metrics.get("pass_rate", 0.0)) or 0.0)
        citation_valid_ratio = float(metrics.get("citation_valid_ratio", 0.0) or 0.0)
        stale_claims_count = int(metrics.get("stale_claims_count", 0) or 0)
        conflict_count = int(metrics.get("conflict_count", 0) or 0)

        risk_score = 0.0
        if coverage < 0.6:
            risk_score += 0.35
        if pass_rate < 0.6:
            risk_score += 0.35
        if citation_valid_ratio < 0.95:
            risk_score += 0.2
        if stale_claims_count > 0:
            risk_score += 0.05
        if conflict_count > 0:
            risk_score += 0.15
        risk_score = round(min(1.0, risk_score), 4)

        if phase in {"P", "D"}:
            mode = "light"
            reason = "plan_diagnose_context_sync"
        elif phase == "X":
            mode = "research" if risk_score >= 0.5 else "light"
            reason = "research_needed" if mode == "research" else "research_optional"
        elif phase == "R":
            mode = "research" if risk_score >= 0.45 else "light"
            reason = "repair_needs_evidence" if mode == "research" else "repair_low_risk"
        elif phase == "A":
            mode = "strict"
            reason = "audit_requires_citation_integrity"
        elif phase == "C":
            mode = "strict"
            reason = "crystallize_requires_writeback"
        else:
            mode = "off"
            reason = "unknown_phase"

        return {
            "phase": phase,
            "topic": topic,
            "mode": mode,
            "risk_score": risk_score,
            "reason": reason,
            "metrics_snapshot": {
                "coverage": coverage,
                "self_question_pass_rate": pass_rate,
                "citation_valid_ratio": citation_valid_ratio,
                "stale_claims_count": stale_claims_count,
                "conflict_count": conflict_count,
            },
        }

    def _phase_writeback_policy(self, *, phase: str, route: dict[str, Any]) -> dict[str, Any]:
        phase = str(phase or "").upper()
        mode = str(route.get("mode", "off"))
        required = phase in {"R", "A", "C"} or mode in {"research", "strict"}
        return {
            "required": required,
            "policy": "required" if required else "optional",
            "reason": f"phase={phase},mode={mode}",
        }

    def _append_phase_writeback(self, payload: dict[str, Any]) -> None:
        self.phase_writeback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.phase_writeback_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def sync_phase_learning_closure(
        self,
        *,
        topic: str,
        metrics: dict[str, Any],
        phase_status: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Bridge Learn lane into six-phase routing + phase-end writeback policy."""
        now = datetime.now(timezone.utc).isoformat()
        written = 0
        routes: dict[str, Any] = {}
        statuses = {k.upper(): str(v).upper() for k, v in (phase_status or {}).items()}

        for phase in self.PHASES:
            route = self._decide_learn_phase_route(phase=phase, topic=topic, metrics=metrics)
            policy = self._phase_writeback_policy(phase=phase, route=route)
            status = statuses.get(phase, "SUCCESS")
            payload = {
                "timestamp": now,
                "topic": topic,
                "phase": phase,
                "phase_status": status,
                "route": route,
                "writeback_policy": policy,
                "writeback_done": True,
            }
            self._append_phase_writeback(payload)
            routes[phase] = route
            written += 1

        summary = self.build_phase_slo_report(window=300)
        return {
            "status": "SUCCESS",
            "topic": topic,
            "entries_written": written,
            "phase_routes": routes,
            "phase_slo_summary": summary,
        }

    def build_phase_slo_report(self, *, window: int = 300) -> dict[str, Any]:
        return self._slo_svc.build_phase_slo_report(window=window)

    def read_phase_slo_summary(self) -> dict[str, Any]:
        if not self.phase_slo_summary_path.exists():
            return {
                "status": "UNAVAILABLE",
                "phase_slo_pass": False,
                "global": {
                    "required_done_ratio": 0.0,
                    "success_ratio": 0.0,
                },
                "phases": {},
                "reason": "phase_slo_summary_missing",
            }
        try:
            data = json.loads(self.phase_slo_summary_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "status": "UNAVAILABLE",
                "phase_slo_pass": False,
                "global": {
                    "required_done_ratio": 0.0,
                    "success_ratio": 0.0,
                },
                "phases": {},
                "reason": "phase_slo_summary_parse_error",
            }
        if not isinstance(data, dict):
            return {
                "status": "UNAVAILABLE",
                "phase_slo_pass": False,
                "global": {
                    "required_done_ratio": 0.0,
                    "success_ratio": 0.0,
                },
                "phases": {},
                "reason": "phase_slo_summary_invalid_type",
            }
        return data

    def _load_source_registry(self) -> list[dict[str, Any]]:
        if not self.sources_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.sources_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _write_source_registry(self, rows: list[dict[str, Any]]) -> None:
        self.sources_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        self.sources_path.write_text((content + "\n") if content else "", encoding="utf-8")

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
        self.benchmark_candidates_path.parent.mkdir(parents=True, exist_ok=True)
        with self.benchmark_candidates_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _load_benchmark_candidates(self) -> list[dict[str, Any]]:
        if not self.benchmark_candidates_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.benchmark_candidates_path.read_text(encoding="utf-8").splitlines():
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
    def _normalize_question(question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    def curate_benchmark_bank(
        self,
        *,
        topic: str = "",
        max_questions: int = 40,
        min_occurrences: int = 1,
    ) -> dict[str, Any]:
        candidates = self._load_benchmark_candidates()
        if topic:
            candidates = [c for c in candidates if str(c.get("topic", "")) == topic]

        buckets: dict[str, dict[str, Any]] = {}
        for row in candidates:
            question = str(row.get("question", "")).strip()
            if not question:
                continue
            key = self._normalize_question(question)
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
                    "difficulty": "unknown" if item["expected_status"] == "UNKNOWN" else ("conflict" if item["expected_status"] == "CONFLICT" else "deep"),
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
            "source_file": str(self.benchmark_candidates_path),
        }
        self.benchmark_bank_path.parent.mkdir(parents=True, exist_ok=True)
        self.benchmark_bank_path.write_text(json.dumps(bank_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return bank_payload

    def _sync_registry_after_ingest(self, *, source: str, source_file: str | None, topic: str, claims_count: int) -> None:
        rows = self._load_source_registry()
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for row in rows:
            if (
                str(row.get("topic", "")) == str(topic or row.get("topic", ""))
                and str(row.get("source", "")) == str(source)
                and str(row.get("source_file", "")) == str(source_file or "")
            ):
                row["last_ingested_at"] = now
                row["last_claim_count"] = int(claims_count)
                row["updated_at"] = now
                changed = True
        if changed:
            self._write_source_registry(rows)

    def register_source(
        self,
        *,
        topic: str,
        source: str,
        refresh_after_days: int = 14,
        priority: str = "medium",
        source_file: str | None = None,
    ) -> dict[str, Any]:
        rows = self._load_source_registry()
        key = f"{topic}|{source}|{source_file or ''}"
        now = datetime.now(timezone.utc).isoformat()
        refresh_after_days = max(1, int(refresh_after_days))
        priority = str(priority or "medium").lower()
        updated = False
        for row in rows:
            row_key = f"{row.get('topic','')}|{row.get('source','')}|{row.get('source_file','')}"
            if row_key == key:
                row.update(
                    {
                        "topic": topic,
                        "source": source,
                        "source_file": source_file or "",
                        "refresh_after_days": refresh_after_days,
                        "priority": priority,
                        "updated_at": now,
                    }
                )
                updated = True
                break
        if not updated:
            rows.append(
                {
                    "topic": topic,
                    "source": source,
                    "source_file": source_file or "",
                    "refresh_after_days": refresh_after_days,
                    "priority": priority,
                    "last_ingested_at": "",
                    "last_refreshed_at": "",
                    "last_claim_count": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        self._write_source_registry(rows)
        return {"status": "SUCCESS", "topic": topic, "source": source, "priority": priority, "refresh_after_days": refresh_after_days}

    def _source_due(self, row: dict[str, Any]) -> bool:
        last = str(row.get("last_refreshed_at") or row.get("last_ingested_at") or "")
        if not last:
            return True
        return self._days_since(last) >= float(row.get("refresh_after_days", 14) or 14)

    def refresh_sources(
        self,
        *,
        topic: str = "",
        due_only: bool = True,
        pass_threshold: float = 0.6,
        question_count: int = 5,
    ) -> dict[str, Any]:
        rows = self._load_source_registry()
        selected = [r for r in rows if (not topic or str(r.get("topic", "")) == topic)]
        if due_only:
            selected = [r for r in selected if self._source_due(r)]
        refreshed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if row not in selected:
                skipped.append(
                    {
                        "topic": row.get("topic", ""),
                        "source": row.get("source", ""),
                        "reason": "not_selected" if topic and str(row.get("topic", "")) != topic else ("not_due" if due_only else "not_requested"),
                    }
                )
                continue
            ingest_report = self.ingest(
                source=str(row.get("source", "")),
                source_file=(str(row.get("source_file", "")) or None),
                topic=str(row.get("topic", "")),
            )
            converge_report = self.converge(
                topic=str(row.get("topic", "")),
                max_rounds=2,
                pass_threshold=pass_threshold,
                question_count=question_count,
                auto_research=False,
            )
            row["last_ingested_at"] = now
            row["last_refreshed_at"] = now
            row["last_claim_count"] = int(ingest_report.get("claims_count", 0))
            row["updated_at"] = now
            refreshed.append(
                {
                    "topic": row.get("topic", ""),
                    "source": row.get("source", ""),
                    "claims_count": ingest_report.get("claims_count", 0),
                    "converged": converge_report.get("converged", False),
                    "self_question_pass_rate": converge_report.get("self_question_pass_rate", 0.0),
                }
            )
        self._write_source_registry(rows)
        return {
            "status": "SUCCESS",
            "due_only": due_only,
            "topic": topic,
            "refreshed_count": len(refreshed),
            "skipped_count": len(skipped),
            "refreshed": refreshed,
            "skipped": skipped[:20],
            "registry_path": str(self.sources_path),
            "timestamp": now,
        }

    def build_refresh_plan(
        self,
        *,
        topic: str = "",
        due_within_days: int = 0,
    ) -> dict[str, Any]:
        rows = self._load_source_registry()
        if topic:
            rows = [row for row in rows if str(row.get("topic", "")) == topic]

        due_items: list[dict[str, Any]] = []
        not_due_items: list[dict[str, Any]] = []
        threshold = max(0, int(due_within_days))
        for row in rows:
            last = str(row.get("last_refreshed_at") or row.get("last_ingested_at") or "")
            refresh_after_days = int(row.get("refresh_after_days", 14) or 14)
            days_since = self._days_since(last) if last else float(refresh_after_days)
            days_until_due = max(0.0, float(refresh_after_days) - float(days_since))
            item = {
                "topic": row.get("topic", ""),
                "source": row.get("source", ""),
                "source_file": row.get("source_file", ""),
                "priority": row.get("priority", "medium"),
                "refresh_after_days": refresh_after_days,
                "last_ingested_at": row.get("last_ingested_at", ""),
                "last_refreshed_at": row.get("last_refreshed_at", ""),
                "last_claim_count": int(row.get("last_claim_count", 0) or 0),
                "days_since_last_refresh": round(float(days_since), 3),
                "days_until_due": round(float(days_until_due), 3),
                "due": bool(days_until_due <= threshold),
            }
            if item["due"]:
                due_items.append(item)
            else:
                not_due_items.append(item)

        return {
            "status": "SUCCESS",
            "topic": topic,
            "due_within_days": threshold,
            "sources_total": len(rows),
            "due_count": len(due_items),
            "not_due_count": len(not_due_items),
            "due": due_items,
            "not_due": not_due_items,
            "registry_path": str(self.sources_path),
            "benchmark_candidates_path": str(self.benchmark_candidates_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

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

    def ingest(self, source: str, source_file: str | None = None, topic: str = "") -> dict[str, Any]:
        return self._ingest_svc.ingest(source, source_file, topic)

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
    ) -> dict[str, Any]:
        claims = self.load_claims()
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
            }

        selected_pack, routed_claims = self._route_topic_pack(claims, topic, question)
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
                "topic_pack_selected": selected_pack,
                "conflicts": conflicts,
                "learning_closure": closure,
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
                "topic_pack_selected": selected_pack,
                "learning_closure": closure,
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
            "topic_pack_selected": selected_pack,
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
        claims = self.load_claims()
        sources = {c.get("source_url", "") for c in claims if c.get("source_url")}
        valid_claims = [c for c in claims if self._is_valid_citation(c)]
        unresolved_questions: list[str] = []
        answered_questions: list[dict[str, Any]] = []
        question_set: list[dict[str, Any]] = []
        coverage = 0.0 if not claims else len(valid_claims) / len(claims)
        pass_rate = 1.0 if claims else 0.0
        topic_pack_counts: dict[str, int] = {}
        high_strength_claims = 0
        stale_claims_count = 0
        for claim in valid_claims:
            pack = str(claim.get("topic_pack", "general"))
            topic_pack_counts[pack] = topic_pack_counts.get(pack, 0) + 1
            if str(claim.get("evidence_strength", "")).lower() == "high":
                high_strength_claims += 1
            if float(claim.get("freshness_days", 0.0)) > 90:
                stale_claims_count += 1
        conflict_candidates = self._find_conflicts(valid_claims[:50])
        if topic:
            question_set = self._build_question_set(topic, question_count=question_count)
            answered_questions, unresolved_questions = self._answer_questions(question_set, valid_claims)
            pass_rate = (
                0.0 if not question_set else len(answered_questions) / len(question_set)
            )
            if pass_rate < pass_threshold and not unresolved_questions:
                unresolved_questions = [
                    f"Need more cited claims to reach pass threshold {pass_threshold}"
                ]

        report = {
            "status": "SUCCESS",
            "topic": topic,
            "sources_count": len(sources),
            "claims_count": len(claims),
            "claims_with_valid_citation": len(valid_claims),
            "citation_valid_ratio": round(0.0 if not claims else len(valid_claims) / len(claims), 4),
            "high_strength_claims": high_strength_claims,
            "stale_claims_count": stale_claims_count,
            "conflict_candidate_count": len(conflict_candidates),
            "topic_packs": topic_pack_counts,
            "top_sources": sorted(sources)[:5],
            "coverage": round(coverage, 4),
            "self_question_pass_rate": round(pass_rate, 4),
            "question_set": question_set,
            "answered_questions": answered_questions,
            "unresolved_questions": unresolved_questions,
            "converged": pass_rate >= pass_threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        report["phase_slo_summary"] = self.build_phase_slo_report(window=300)
        return report
