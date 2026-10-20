"""Portable arm interface for other harnesses (Cairnwork, #2721).

Kept deliberately small.  An arm adapter takes an ``ArmInput`` and returns a
candidate (a commit or a diff) or an explicit failure code plus a log path;
the scorer stays independent and only ever sees the candidate.  Every row is
also written in the versioned ``PORTABLE_ROW_SCHEMA`` shape.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

PORTABLE_ROW_SCHEMA = "nexus.measure_2721.portable_row.v1"


@dataclass(frozen=True)
class ArmInput:
    repo_path: str
    base: str  # 40-hex
    allowed_files: tuple[str, ...]
    verifier_argv: tuple[tuple[str, ...], ...]
    task_id: str
    attempt_id: str
    model: str
    seed: Optional[int] = None


@dataclass(frozen=True)
class ArmOutput:
    candidate_commit: Optional[str]
    candidate_diff_path: Optional[str]
    failure_code: Optional[str]
    log_path: Optional[str]


def to_portable_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """The harness row in the portable shape (optional ``verdict`` stays None
    until an independent scorer fills it)."""
    tokens = {key: row.get(key) for key in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    return {
        "schema": PORTABLE_ROW_SCHEMA,
        "task_id": row.get("task_id"),
        "arm": row.get("arm"),
        "attempt_id": row.get("run_id"),
        "candidate_commit": row.get("candidate_commit_sha"),
        "candidate_diff_path": row.get("diff_path"),
        "outcome": row.get("outcome"),
        "failure_code": None if row.get("outcome") == "OK" else (row.get("void_reason") or row.get("outcome")),
        "cost_tokens": tokens if any(v is not None for v in tokens.values()) else row.get("total_tokens"),
        "cost_usd": row.get("total_cost_usd"),
        "wall_seconds": row.get("wall_seconds"),
        "verdict": None,
        "log_path": row.get("claude_trace_path") or (row.get("provider") or {}).get("extra", {}).get("trace_path"),
    }


def as_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
