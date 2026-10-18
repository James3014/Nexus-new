"""Task-bound record keys (#2454, law 2).

A replayable record (an in-process binding, a consumed token, a cached decision) must be
keyed by the task it belongs to, not by a content digest alone. Otherwise a genuine record
made for one task is accepted for another task whose content happens to hash the same --
the #2032 escape, where a planner route_context snapshot was accepted for any task until
#2050 keyed it by ``(task_id, digest)``.

``task_bound_key`` builds that key and fails closed: when the task identity or the digest is
missing, empty or not a string it returns ``None``, and callers must then bind nothing and
treat a lookup as "not bound". Task ids are used exactly as given (never stripped, folded or
normalised), so two distinct ids can never collide into one key. The digest is opaque here:
its format is the caller's contract (e.g. ``planner_snapshot_digest`` yields "sha256:<hex>").
Stdlib-only, importable from any layer.
"""

from __future__ import annotations

__all__ = ["TaskBoundKey", "task_bound_key", "task_identity"]

TaskBoundKey = tuple[str, str]


def task_identity(task_id: object) -> str | None:
    """``task_id`` unchanged when it is a non-blank string, else ``None`` (fail closed)."""
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    return task_id


def task_bound_key(task_id: object, digest: object) -> TaskBoundKey | None:
    """``(task_id, digest)``, or ``None`` when either part is missing, blank or not a string."""
    task = task_identity(task_id)
    if task is None or not isinstance(digest, str) or not digest.strip():
        return None
    return (task, digest)
