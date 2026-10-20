"""Self-hosted state per learning phase (#2721, agreed by workspace-33 / workspace-06).

* M and L-B: before every task the state root is restored to the phase-start
  snapshot and the restore is proven by hash.  L-A: restored once, before the
  phase's first task (learning accumulates inside the phase).
* A restore runs only when the instance is quiet: no self-hosted task is still
  in flight, the previous task is terminal and its Target worktree is gone.
* Two state trees are restored under the same policy: ``NEXUS_STATE_ROOT``
  and the self-hosted state dir (``NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR``,
  the driver's ``--state-dir``), each from its own phase-start snapshot,
  unless the self-hosted dir lies inside the state root (one restore then
  covers both).
* ``assisted_provider_jobs/`` is never restored or hashed (PREREG §5): it
  is the Gateway's model-probe cache, not learning state.
* L-A's "restored once" is persisted in the run root
  (``state_phase_<phase>.restored.json`` with the snapshot hashes), so a
  resume after exit 75 does not restore the phase start again and wipe the
  learning accumulated so far; a marker for different snapshots refuses.
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
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

# Relative paths kept as they are by a restore and left out of every hash.
# PREREG §5: the whole probe cache (``assisted_provider_jobs/``: probe jobs, their
# stdout/stderr and ``probe_evidence/``) is never restored, or every row re-probes.
PRESERVED_STATE_PATHS = ("assisted_provider_jobs",)
PHASE_MARKER_SCHEMA = "nexus.measure_2721.state_phase_marker.v1"
PER_ROW_PHASES = frozenset({"M", "LB", "L-B", "COLD", "IRRELEVANT"})
PER_PHASE_PHASES = frozenset({"LA", "L-A"})
READ_ONLY_PHASES = frozenset({"LB", "L-B"})
# Same set as the driver's (nexus_driver imports it from here).
TERMINAL_STATUSES = frozenset({"CANCELLED", "FINAL_BLOCK", "REJECTED", "SUPERSEDED", "INTEGRATED",
                               "INTEGRATION_FAILED", "RETAINED_FOR_REVIEW", "FAILED", "TERMINAL"})
ROUTER_LOG_NAMES = ("router_decisions.jsonl", "scripts/core/router_decisions.jsonl")


def _preserved(relative: Path | str) -> bool:
    rel = Path(relative).as_posix()
    return any(rel == p or rel.startswith(p + "/") for p in PRESERVED_STATE_PATHS)


def _holds_preserved(relative: Path | str) -> bool:
    """``relative`` is a directory above a preserved path (walk into it, never remove it whole)."""
    rel = Path(relative).as_posix()
    return any(p.startswith(rel + "/") for p in PRESERVED_STATE_PATHS)


def _clear(root: Path, relative: Path) -> None:
    for child in list((root / relative).iterdir()):
        rel = relative / child.name
        if child.name.endswith(".lock") or _preserved(rel):
            continue
        if child.is_dir() and not child.is_symlink():
            if _holds_preserved(rel):
                _clear(root, rel)
                continue
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy(snapshot: Path, root: Path, relative: Path) -> None:
    for child in (snapshot / relative).iterdir():
        rel = relative / child.name
        if child.name.endswith(".lock") or _preserved(rel):
            continue
        target = root / rel
        if child.is_dir() and not child.is_symlink():
            if _holds_preserved(rel):
                target.mkdir(parents=True, exist_ok=True)
                _copy(snapshot, root, rel)
            else:
                shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target, follow_symlinks=False)


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
        _clear(state_root, Path())
    state_root.mkdir(parents=True, exist_ok=True)
    _copy(snapshot, state_root, Path())
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


class PhaseMarkerMismatch(RuntimeError):
    """A persisted phase marker names other snapshots than this run's: refuse."""


def phase_marker_path(run_root: Path, phase: Optional[str]) -> Path:
    name = "".join(ch for ch in str(phase or "none").upper() if ch.isalnum()) or "NONE"
    return Path(run_root) / f"state_phase_{name}.restored.json"


def read_phase_marker(run_root: Path, phase: Optional[str], snapshots: Mapping[str, str]) -> bool:
    """True when this phase start was already restored for these snapshot hashes.

    ``snapshots`` maps a label (``state_root``, ``self_hosted``) to the
    snapshot's ``state_sha256``.  A marker for other hashes raises
    ``PhaseMarkerMismatch`` (the run root belongs to another phase start).
    """
    path = phase_marker_path(run_root, phase)
    if not path.is_file():
        return False
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PhaseMarkerMismatch(f"STATE_PHASE_MARKER_UNREADABLE: {path.name}") from exc
    if not isinstance(marker, dict) or marker.get("snapshot_sha256") != dict(snapshots):
        raise PhaseMarkerMismatch(f"STATE_PHASE_MARKER_MISMATCH: {path.name} names other snapshots")
    return True


def write_phase_marker(
    run_root: Path, phase: Optional[str], snapshots: Mapping[str, str], restored: Mapping[str, str]
) -> Path:
    path = phase_marker_path(run_root, phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": PHASE_MARKER_SCHEMA,
        "phase": phase,
        "snapshot_sha256": dict(snapshots),
        "restored_sha256": dict(restored),
        "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def restore_policy(phase: Optional[str]) -> str:
    """``per_row`` (M, L-B and the default) or ``per_phase`` (L-A)."""
    return "per_phase" if str(phase or "").upper() in PER_PHASE_PHASES else "per_row"


def read_only_phase(phase: Optional[str]) -> bool:
    return str(phase or "").upper() in READ_ONLY_PHASES


def summarize(states: Mapping[str, Any]) -> dict[str, Any]:
    return {key: states.get(key) for key in ("expected_sha256", "restored_sha256", "ok")}
