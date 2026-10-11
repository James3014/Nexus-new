"""Belief + Artifact + Dependency Graph v0.2 data model and JSONL writer.

Implements the core of ``nexus-belief-artifact-v0.2-spec.md`` on top of the
``.nexusknowledge/{beliefs,artifacts,dependency_edges}.jsonl`` files that the
existing readers (``scripts/ops/brain_loop_closure.py``,
``scripts/ops/predictive_healing.py``) consume:

* beliefs / artifacts are keyed by ``id`` and carry ``status``;
* edges use ``from_id`` / ``to_id`` / ``type`` (belief -> artifact).

Writes are idempotent: a record with an existing id (or identical edge key)
is never appended twice. Not wired into routing/planner/budget.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BELIEF_STATUSES = ("active", "retracted", "superseded")
ARTIFACT_STATUSES = ("active", "stale", "needs_review")
EDGE_TYPES = ("depends_on", "derived_from", "supports", "conflicts_with", "supersedes")
# Belief statuses that invalidate dependent artifacts.
_INVALIDATING_BELIEF_STATUSES = ("retracted", "superseded")

BELIEFS_FILE = "beliefs.jsonl"
ARTIFACTS_FILE = "artifacts.jsonl"
EDGES_FILE = "dependency_edges.jsonl"


def _require_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("record id must be a non-empty string")


@dataclass
class BeliefRecord:
    id: str
    content: str = ""
    version: int = 1
    type: str = "belief"
    status: str = "active"
    supported_by_artifacts: List[str] = field(default_factory=list)
    invalidates_artifacts: List[str] = field(default_factory=list)

    def validate(self) -> None:
        _require_id(self.id)
        if self.status not in BELIEF_STATUSES:
            raise ValueError(f"invalid belief status: {self.status!r}")


@dataclass
class ArtifactRecord:
    id: str
    path_ref: str = ""
    version: int = 1
    type: str = "artifact"
    status: str = "active"
    supersedes_id: Optional[str] = None
    linked_beliefs: List[str] = field(default_factory=list)

    def validate(self) -> None:
        _require_id(self.id)
        if self.status not in ARTIFACT_STATUSES:
            raise ValueError(f"invalid artifact status: {self.status!r}")


@dataclass
class EdgeRecord:
    from_id: str
    to_id: str
    type: str = "depends_on"

    def validate(self) -> None:
        _require_id(self.from_id)
        _require_id(self.to_id)
        if self.type not in EDGE_TYPES:
            raise ValueError(f"invalid edge type: {self.type!r}")


def _record_id(record: Dict[str, Any]) -> Optional[str]:
    """Id of a stored record; tolerates legacy ``belief_id`` / ``artifact_id`` keys."""
    for key in ("id", "belief_id", "artifact_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _edge_key(record: Dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        record.get("from_id", record.get("source")),
        record.get("to_id", record.get("target")),
        record.get("type"),
    )


def _merge_unique(old: Iterable[str], new: Iterable[str]) -> List[str]:
    merged = list(old)
    merged.extend(x for x in new if x not in merged)
    return merged


def _belief_from_row(row: Dict[str, Any]) -> BeliefRecord:
    return BeliefRecord(
        id=_record_id(row) or "",
        content=row.get("content", ""),
        version=row.get("version", 1),
        type=row.get("type", "belief"),
        status=row.get("status", "active"),
        supported_by_artifacts=list(row.get("supported_by_artifacts") or []),
        invalidates_artifacts=list(row.get("invalidates_artifacts") or []),
    )


def _artifact_from_row(row: Dict[str, Any]) -> ArtifactRecord:
    return ArtifactRecord(
        id=_record_id(row) or "",
        path_ref=row.get("path_ref", ""),
        version=row.get("version", 1),
        type=row.get("type", "artifact"),
        status=row.get("status", "active"),
        supersedes_id=row.get("supersedes_id"),
        linked_beliefs=list(row.get("linked_beliefs") or []),
    )


class KnowledgeStore:
    """Idempotent writer/reader for the v0.2 ``.nexusknowledge`` JSONL files."""

    def __init__(self, knowledge_dir: Path) -> None:
        self.knowledge_dir = Path(knowledge_dir)
        self.beliefs_path = self.knowledge_dir / BELIEFS_FILE
        self.artifacts_path = self.knowledge_dir / ARTIFACTS_FILE
        self.edges_path = self.knowledge_dir / EDGES_FILE

    # -- low-level io -------------------------------------------------
    @staticmethod
    def load(path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    @staticmethod
    def _append(path: Path, record: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _rewrite(path: Path, rows: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _upsert(self, path: Path, record: Dict[str, Any]) -> bool:
        """Append if id is new; replace in place (collapsing duplicates) if it differs.

        Returns True when the file changed.
        """
        rid = record["id"]
        rows = self.load(path)
        matches = [i for i, r in enumerate(rows) if _record_id(r) == rid]
        if not matches:
            self._append(path, record)
            return True
        if len(matches) == 1 and rows[matches[0]] == record:
            return False
        rows[matches[0]] = record
        drop = set(matches[1:])
        self._rewrite(path, [r for i, r in enumerate(rows) if i not in drop])
        return True

    # -- writers ------------------------------------------------------
    def write_belief(self, belief: BeliefRecord) -> bool:
        """Upsert a belief by id. Re-writing identical data is a no-op."""
        belief.validate()
        return self._upsert(self.beliefs_path, asdict(belief))

    def write_artifact(self, artifact: ArtifactRecord) -> bool:
        """Upsert an artifact by id. Re-writing identical data is a no-op."""
        artifact.validate()
        return self._upsert(self.artifacts_path, asdict(artifact))

    def write_edge(self, edge: EdgeRecord) -> bool:
        """Append an edge unless (from_id, to_id, type) already exists."""
        edge.validate()
        record = asdict(edge)
        key = _edge_key(record)
        if any(_edge_key(r) == key for r in self.load(self.edges_path)):
            return False
        self._append(self.edges_path, record)
        return True

    def link(self, belief_id: str, artifact_id: str, edge_type: str = "depends_on") -> None:
        """Link a belief and artifact consistently in both records and the edge file.

        Edges run belief -> artifact (the direction the existing readers use); the
        belief lists the artifact in ``invalidates_artifacts`` and the artifact lists
        the belief in ``linked_beliefs``.
        """
        EdgeRecord(belief_id, artifact_id, edge_type).validate()
        belief = self.get_belief(belief_id)
        artifact = self.get_artifact(artifact_id)
        if belief is None or artifact is None:
            raise KeyError("both belief and artifact must exist before link()")
        belief.invalidates_artifacts = _merge_unique(belief.invalidates_artifacts, [artifact_id])
        artifact.linked_beliefs = _merge_unique(artifact.linked_beliefs, [belief_id])
        self.write_belief(belief)
        self.write_artifact(artifact)
        self.write_edge(EdgeRecord(belief_id, artifact_id, edge_type))

    # -- readers ------------------------------------------------------
    def get_belief(self, belief_id: str) -> Optional[BeliefRecord]:
        rows = [r for r in self.load(self.beliefs_path) if _record_id(r) == belief_id]
        return _belief_from_row(rows[-1]) if rows else None

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        rows = [r for r in self.load(self.artifacts_path) if _record_id(r) == artifact_id]
        return _artifact_from_row(rows[-1]) if rows else None

    # -- invalidation propagation ------------------------------------
    def set_belief_status(
        self, belief_id: str, status: str, reason: str = "Unspecified"
    ) -> List[str]:
        """Change a belief's status; if retracted/superseded, mark dependent artifacts stale.

        Dependents are the belief's ``invalidates_artifacts`` plus targets of its
        outgoing ``depends_on`` edges (mirrors ``brain_loop_closure`` propagation).
        Only ``active`` artifacts are changed. Returns the ids of artifacts marked stale.
        """
        if status not in BELIEF_STATUSES:
            raise ValueError(f"invalid belief status: {status!r}")
        rows = self.load(self.beliefs_path)
        matches = [i for i, r in enumerate(rows) if _record_id(r) == belief_id]
        if not matches:
            raise KeyError(belief_id)
        row = rows[matches[-1]]
        row["id"] = belief_id
        row["status"] = status
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        drop = set(matches[:-1])
        self._rewrite(self.beliefs_path, [r for i, r in enumerate(rows) if i not in drop])
        if status not in _INVALIDATING_BELIEF_STATUSES:
            return []
        affected = set(row.get("invalidates_artifacts") or [])
        for edge in self.load(self.edges_path):
            f_id, t_id, e_type = _edge_key(edge)
            if f_id == belief_id and e_type == "depends_on" and t_id:
                affected.add(t_id)
        return self.mark_artifacts_stale(
            sorted(affected), f"Origin belief {belief_id} {status}: {reason}"
        )

    def mark_artifacts_stale(self, artifact_ids: Iterable[str], reason: str) -> List[str]:
        wanted = set(artifact_ids)
        rows = self.load(self.artifacts_path)
        changed: List[str] = []
        for row in rows:
            rid = _record_id(row)
            if rid in wanted and row.get("status", "active") == "active":
                row["status"] = "stale"
                row["stale_reason"] = reason
                row["updated_at"] = datetime.now(timezone.utc).isoformat()
                changed.append(rid)
        if changed:
            self._rewrite(self.artifacts_path, rows)
        return changed
