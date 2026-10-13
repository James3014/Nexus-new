"""In-process binding of CapabilityPlanner signal snapshots to executor route contexts (#1924).

``build_execution_plan`` (trusted, in-process) registers the sha256 of the canonical JSON of
the planner snapshot it passes through as ``executor_controls["route_context"]``. Consumers such
as LocalHealCapabilityAdapter accept a route_context only when its snapshot digest is
registered here, so a hand-built or edited ``route_context`` is rejected.

Guarantee: in-process origin only. The snapshot went through ``build_execution_plan`` in this
process and was not edited afterwards. This is not cryptographic protection against code that
can call ``build_execution_plan`` (or this module) directly.
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
_bound: OrderedDict[str, None] = OrderedDict()


def planner_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=repr)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def register_planner_snapshot(snapshot: Mapping[str, Any]) -> str:
    digest = planner_snapshot_digest(snapshot)
    with _lock:
        _bound[digest] = None
        _bound.move_to_end(digest)
        while len(_bound) > _MAX_BOUND_SNAPSHOTS:
            _bound.popitem(last=False)
    return digest


def is_planner_bound(snapshot: object) -> bool:
    if not isinstance(snapshot, Mapping) or not snapshot:
        return False
    digest = planner_snapshot_digest(snapshot)
    with _lock:
        return digest in _bound


def clear_planner_bindings() -> None:
    with _lock:
        _bound.clear()
