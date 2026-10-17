"""Failed-outcome-pattern producer for MemPalace belief constraints.

Fed by real skill outcomes (CrystallizationService.persist_outcome). When the same
(skill_id, domain) fails N times in a row (at most one failure per task_id; retries of one
task are not independent evidence), a ``forbid`` belief is upserted into the
LanceDB table ``nexus_soul_palace`` (the table MemPalace reads constraints from). A later
success for that pair marks the belief ``inactive`` so the constraint is lifted.

Never raises into the caller; write failures are logged and exposed via ``last_write_status``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from nexus.infrastructure.storage_implementations import LanceBeliefStore
from nexus.services.memory_repository import EmbeddingProvider, default_embedding_provider

logger = logging.getLogger(__name__)

STREAK_ENV = "NEXUS_BELIEF_FORBID_STREAK"
DEFAULT_STREAK = 3
STATE_REL = Path(".nexus") / "state" / "outcome_failure_streaks.json"
_DOMAIN_KEYS = ("task_type", "domain", "active_domain")
# Bound on remembered task ids per streak (retries of one task count once; see #2375).
MAX_TRACKED_TASKS = 50


def forbid_belief_id(skill_id: str, domain: str) -> str:
    return hashlib.sha256(
        json.dumps(["forbid", skill_id, domain], ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def outcome_domain(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata")
    for source in (payload, metadata if isinstance(metadata, dict) else {}):
        for key in _DOMAIN_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "general"


def _streak_threshold() -> int:
    try:
        return max(1, int(os.environ.get(STREAK_ENV, DEFAULT_STREAK)))
    except ValueError:
        return DEFAULT_STREAK


class BeliefConstraintProducer:
    def __init__(
        self,
        project_root: Path,
        *,
        threshold: Optional[int] = None,
        belief_store: Optional[LanceBeliefStore] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.threshold = threshold if threshold is not None else _streak_threshold()
        self.belief_store = belief_store or LanceBeliefStore(self.project_root)
        self.embedding_provider = embedding_provider
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.state_path = self.project_root / STATE_REL
        self.last_write_status: str = ""
        self.last_write_error: str = ""

    # -- streak state --------------------------------------------------
    def _load_state(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self.state_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -- main entry ----------------------------------------------------
    def record_outcome(self, payload: Dict[str, Any]) -> None:
        """Update the streak for the outcome's (skill, domain). Never raises."""
        self.last_write_status = ""
        self.last_write_error = ""
        try:
            skill_id = str(payload.get("skill_id") or "").strip()
            if not skill_id or "passed" not in payload:
                return
            domain = outcome_domain(payload)
            key = f"{skill_id}\x1f{domain}"
            state = self._load_state()
            raw_entry = state.get(key)
            entry: Dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}
            streak = int(entry.get("streak", 0))
            active = bool(entry.get("active", False))
            stamp = self._now().isoformat()
            if payload.get("passed"):
                if active:
                    ok = self.belief_store.set_belief_status(
                        forbid_belief_id(skill_id, domain), "inactive", stamp
                    )
                    self._note(ok)
                    if not ok and self.belief_store.last_write_status == "unavailable":
                        return  # keep ``active`` so the lift is retried on the next success
                state.pop(key, None)
            else:
                task_id = str(payload.get("task_id") or "").strip()
                seen = [str(t) for t in entry.get("tasks", []) if isinstance(t, str)]
                if task_id and task_id in seen:
                    return  # retry of an already counted task: not independent evidence
                if task_id:
                    seen = (seen + [task_id])[-MAX_TRACKED_TASKS:]
                streak += 1
                active = active or streak >= self.threshold
                if streak >= self.threshold:
                    self._note(self._write_forbid(skill_id, domain, streak, stamp))
                state[key] = {"streak": streak, "active": active}
                if seen:
                    state[key]["tasks"] = seen
            self._save_state(state)
        except Exception as exc:
            self.last_write_status = "unavailable"
            self.last_write_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "BeliefConstraintProducer: outcome recording failed: %s", self.last_write_error
            )

    def _note(self, ok: bool) -> None:
        status = self.belief_store.last_write_status
        if status == "unavailable":
            self.last_write_status = "unavailable"
            self.last_write_error = self.belief_store.last_write_error
        elif self.last_write_status != "unavailable":
            self.last_write_status = "ok"

    def _write_forbid(self, skill_id: str, domain: str, streak: int, stamp: str) -> bool:
        content = (
            f"禁止 {skill_id} (forbid) in domain {domain}: {streak} consecutive failed outcomes"
        )
        vector = None
        provider = self.embedding_provider or default_embedding_provider()
        try:
            vector = provider.embed(content)
        except Exception as exc:  # embedding is optional; the row is still written
            logger.warning(
                "BeliefConstraintProducer: embedding failed (%s): %s", provider.name, exc
            )
        row = {
            "id": forbid_belief_id(skill_id, domain),
            "type": "belief",
            "status": "active",
            "content": content,
            "skill_id": skill_id,
            "domain": domain,
            "trust_level": "TRUSTED",
            "created_at": stamp,
            "updated_at": stamp,
            "vector": [float(x) for x in vector] if vector else None,
        }
        return self.belief_store.upsert_belief(row)
