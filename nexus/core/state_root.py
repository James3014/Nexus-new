"""Persistent root for layer-1 state stores (belief, memory, learning) (#2688).

Stateful capabilities keep their stores under ``<root>/.nexus/...``.  The root used
to be the workspace_root, the cwd or the checkout (``Path(__file__).parents[N]``).
That works for a long-lived checkout but not for the live Gateway, whose code
checkout, cwd and workspace_root are per-deploy directories recreated on every
deploy, so the stores always start empty there.

``NEXUS_STATE_ROOT`` names a fixed directory that outlives deploys.  Convention: the
state root is the directory that *contains* ``.nexus``; callers keep appending
``.nexus/...`` exactly as before.

Only the per-deploy roots move: this checkout (``REPO_ROOT``), the process cwd and
``NEXUS_CANONICAL_SOURCE_ROOT``.  Any other root a caller passes (a canary or test
directory, another project) stays where it is, so isolated runs never write into
the shared state.  The store classes apply the resolver themselves
(``FindingsMemoryStore``, ``resolve_lancedb_root``, ``LearnModeService``,
``BeliefEngine``, ...), so every reader and writer of one store moves together, and
applying it twice is harmless.

When the variable is unset, empty or not absolute, every function returns its
argument unchanged (the same object), so behaviour is byte-for-byte the old one.
A relative value is ignored with a warning instead of raising, because these
lookups run on routing hot paths that must not crash on a bad env value.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

STATE_ROOT_ENV = "NEXUS_STATE_ROOT"
CANONICAL_SOURCE_ROOT_ENV = "NEXUS_CANONICAL_SOURCE_ROOT"
_CODE_ROOT = Path(__file__).resolve().parents[2]
_T = TypeVar("_T")


def configured_state_root() -> Path | None:
    """``$NEXUS_STATE_ROOT`` resolved, or None when unset, empty or not absolute."""
    raw = os.environ.get(STATE_ROOT_ENV, "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    if not root.is_absolute():
        logger.warning("%s=%r is not an absolute path; ignoring it", STATE_ROOT_ENV, raw)
        return None
    return root.resolve()


def _deploy_roots() -> set[Path]:
    roots = {_CODE_ROOT}
    try:
        roots.add(Path.cwd().resolve())
    except OSError:
        pass
    source = os.environ.get(CANONICAL_SOURCE_ROOT_ENV, "").strip()
    if source:
        roots.add(Path(source).expanduser().resolve())
    return roots


def persistent_state_root(default: _T) -> Path | _T:
    """Return the root that holds ``.nexus`` state for ``default``.

    ``$NEXUS_STATE_ROOT`` when it is configured and ``default`` is a per-deploy root
    (or already the state root); otherwise ``default`` itself, unchanged.
    """
    state_root = configured_state_root()
    if state_root is None:
        return default
    try:
        candidate = Path(default).expanduser().resolve()  # type: ignore[arg-type]
    except (TypeError, ValueError, OSError):
        return default
    if candidate == state_root or candidate in _deploy_roots():
        return state_root
    return default


def rebase_state_path(path: _T) -> Path | _T:
    """Move ``<root>/.nexus/<rest>`` to ``<state root>/.nexus/<rest>`` when ``root`` moves.

    Paths without a ``.nexus`` component, or whose root does not move, come back
    unchanged (the same object).
    """
    if configured_state_root() is None:
        return path
    try:
        parts = Path(path).parts  # type: ignore[arg-type]
    except TypeError:
        return path
    if ".nexus" not in parts:
        return path
    index = parts.index(".nexus")
    root = Path(*parts[:index]) if index else Path(".")
    moved = persistent_state_root(root)
    if moved is root:
        return path
    return Path(moved, *parts[index:])
