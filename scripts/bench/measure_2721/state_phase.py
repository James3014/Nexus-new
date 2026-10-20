"""Self-hosted state per learning phase (#2721, agreed by workspace-33 / workspace-06).

* M and L-B: before every task the state root is restored to the phase-start
  snapshot and the restore is proven by hash.  L-A: restored once, before the
  phase's first task (learning accumulates inside the phase).
* A restore runs only when the instance is quiet: no self-hosted task is still
  in flight, the previous task is terminal and its Target worktree is gone.
* ``assisted_provider_jobs/`` (probe evidence and assist jobs) is never
  restored or hashed: it is the Gateway's probe cache, not learning state.
* ``state_valid: false`` in any task state refuses the run before it starts.
* L-B is read-only (Q2): after the row the state hash must equal the
  restored hash.
* Extra state files the Gateway writes outside the state root (the router's
  ``router_decisions.jsonl`` under its project root) are put back to their
  phase-start content before every row, so no row sees another row's routing
  log.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

PRESERVED_STATE_DIRS = ("assisted_provider_jobs",)
PER_ROW_PHASES = frozenset({"M", "LB", "L-B", "COLD", "IRRELEVANT"})
PER_PHASE_PHASES = frozenset({"LA", "L-A"})
READ_ONLY_PHASES = frozenset({"LB", "L-B"})
# Same set as the driver's (nexus_driver imports it from here).
TERMINAL_STATUSES = frozenset({"CANCELLED", "FINAL_BLOCK", "REJECTED", "SUPERSEDED", "INTEGRATED",
                               "INTEGRATION_FAILED", "RETAINED_FOR_REVIEW", "FAILED", "TERMINAL"})
ROUTER_LOG_NAMES = ("router_decisions.jsonl", "scripts/core/router_decisions.jsonl")


def _preserved(relative: Path) -> bool:
    return bool(relative.parts) and relative.parts[0] in PRESERVED_STATE_DIRS


def state_sha256(root: Path, *, exclude: Sequence[str] = ()) -> str:
    """sha256 over the state files (relative path + content); locks, the probe cache
    and ``exclude`` (relative prefixes) are left out."""
    digest = hashlib.sha256()
    root = Path(root)
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.name.endswith(".lock")):
        relative = path.relative_to(root)
        rel = relative.as_posix()
        if _preserved(relative) or any(rel == e or rel.startswith(e.rstrip("/") + "/") for e in exclude):
            continue
        digest.update(rel.encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def restore_state(state_root: Path, snapshot: Path) -> dict[str, Any]:
    """Make ``state_root`` equal ``snapshot`` (the probe cache is kept) and prove it by hash."""
    state_root, snapshot = Path(state_root), Path(snapshot)
    expected = state_sha256(snapshot)
    if state_root.exists():
        for child in list(state_root.iterdir()):
            if child.name.endswith(".lock") or child.name in PRESERVED_STATE_DIRS:
                continue
            shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    state_root.mkdir(parents=True, exist_ok=True)
    for child in snapshot.iterdir():
        if child.name in PRESERVED_STATE_DIRS or child.name.endswith(".lock"):
            continue
        target = state_root / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target, follow_symlinks=False)
    actual = state_sha256(state_root)
    return {"expected_sha256": expected, "restored_sha256": actual, "ok": expected == actual}


def _task_states(state_dir: Optional[Path]) -> list[dict[str, Any]]:
    if state_dir is None or not Path(state_dir).is_dir():
        return []
    states = []
    for path in sorted(Path(state_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            states.append({"_path": path.name, "state_valid": False, "_unreadable": True})
            continue
        if isinstance(data, dict):
            states.append({**data, "_path": path.name})
    return states


def invalid_states(state_dir: Optional[Path]) -> list[str]:
    """Task states marked ``state_valid: false`` (the run must not start)."""
    return [s["_path"] for s in _task_states(state_dir) if s.get("state_valid") is False]


def quiescence_problem(state_dir: Optional[Path]) -> Optional[str]:
    """Why the state must not be restored now (a task in flight or a Target left), else None."""
    for state in _task_states(state_dir):
        status = str(state.get("status") or "")
        if status and status not in TERMINAL_STATUSES:
            return f"TASK_IN_FLIGHT:{state['_path']}:{status}"
        target = (state.get("lease") or {}).get("target_worktree") if isinstance(state.get("lease"), dict) else None
        if target and Path(str(target)).exists():
            return f"TARGET_NOT_CLEANED:{state['_path']}"
    return None


class ExtraStateFiles:
    """Files outside the state root that carry state between rows (router log).

    Their content at the phase start is kept in memory and put back (or the
    file removed when it did not exist) before every row.
    """

    def __init__(self, paths: Iterable[Path]):
        self.paths = [Path(p) for p in paths]
        self.initial = {str(p): (p.read_bytes() if p.is_file() else None) for p in self.paths}

    @classmethod
    def router_logs(cls, roots: Iterable[Optional[Path]]) -> "ExtraStateFiles":
        return cls(Path(root) / name for root in roots if root is not None for name in ROUTER_LOG_NAMES)

    def restore(self) -> dict[str, Any]:
        changed = []
        for path in self.paths:
            initial = self.initial[str(path)]
            current = path.read_bytes() if path.is_file() else None
            if current == initial:
                continue
            changed.append(str(path))
            if initial is None:
                path.unlink()
            else:
                path.write_bytes(initial)
        ok = all((p.read_bytes() if p.is_file() else None) == self.initial[str(p)] for p in self.paths)
        return {"ok": ok, "restored": changed}


def restore_policy(phase: Optional[str]) -> str:
    """``per_row`` (M, L-B and the default) or ``per_phase`` (L-A)."""
    return "per_phase" if str(phase or "").upper() in PER_PHASE_PHASES else "per_row"


def read_only_phase(phase: Optional[str]) -> bool:
    return str(phase or "").upper() in READ_ONLY_PHASES


def summarize(states: Mapping[str, Any]) -> dict[str, Any]:
    return {key: states.get(key) for key in ("expected_sha256", "restored_sha256", "ok")}
