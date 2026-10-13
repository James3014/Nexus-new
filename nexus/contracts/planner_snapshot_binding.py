"""In-process binding of CapabilityPlanner signal snapshots to executor route contexts (#1924).

``build_execution_plan`` (trusted, in-process) registers the pair (task_id, sha256 of the
canonical JSON of the planner snapshot) it passes through as ``executor_controls["route_context"]``.
Consumers such as LocalHealCapabilityAdapter accept a route_context only when the pair
(their request's task_id, the snapshot digest) is registered here, so a hand-built or edited
``route_context`` is rejected, and so is a genuine snapshot replayed for a different task.

Guarantee: in-process origin only. The snapshot went through ``build_execution_plan`` in this
process for this task_id and was not edited afterwards. This is not cryptographic protection
against code that can call ``build_execution_plan`` (or this module) directly.

Entries are not single-use: the digest is deterministic, so a re-plan of the same task yields
the same key, and a task may legitimately run the adapter more than once (dry run, then a
real run). The task binding, not consumption, is what blocks cross-task replay.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

ROUTE_CONTEXT_NOT_PLANNER_BOUND = "ROUTE_CONTEXT_NOT_PLANNER_BOUND"
_MAX_BOUND_SNAPSHOTS = 1024

_lock = threading.Lock()
_bound: OrderedDict[tuple[str, str], None] = OrderedDict()


def planner_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=repr)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _task_key(task_id: object) -> str | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    return task_id


def register_planner_snapshot(snapshot: Mapping[str, Any], *, task_id: str) -> str:
    """Bind ``snapshot`` to ``task_id``; an empty task_id binds nothing (fail closed)."""
    digest = planner_snapshot_digest(snapshot)
    task_key = _task_key(task_id)
    if task_key is None:
        return digest
    key = (task_key, digest)
    with _lock:
        _bound[key] = None
        _bound.move_to_end(key)
        while len(_bound) > _MAX_BOUND_SNAPSHOTS:
            _bound.popitem(last=False)
    return digest


def is_planner_bound(snapshot: object, *, task_id: object) -> bool:
    task_key = _task_key(task_id)
    if task_key is None or not isinstance(snapshot, Mapping) or not snapshot:
        return False
    key = (task_key, planner_snapshot_digest(snapshot))
    with _lock:
        return key in _bound


def clear_planner_bindings() -> None:
    with _lock:
        _bound.clear()
