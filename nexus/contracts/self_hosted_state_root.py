"""Shared fail-closed check for legacy self-hosted durable state (#1539).

The default durable-state root moved from ``<repo parent>/<repo>-self-hosted-state``
to ``~/.local/state/<repo>-self-hosted-state``. Adopting the new default while
the legacy tree still holds state would split readback, so every consumer of
the default root refuses instead. Anything uncertain counts as state.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

LEGACY_PRESENT_CODE = "NEXUS_SELF_HOSTED_STATE_ROOT_LEGACY_PRESENT"


def legacy_tree_holds_state(path: Path) -> bool:
    """True when ``path`` may hold durable state; fails closed on every doubt.

    Absent path: no state. Unstattable, symlinked or non-directory path: state.
    Real directory: state when it holds any file or any symlinked directory,
    or when any part of it cannot be read. Empty real directories: no state.
    """
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if not stat.S_ISDIR(mode):
        return True

    def unreadable(exc: OSError) -> None:
        raise exc

    try:
        for dirpath, dirs, files in os.walk(path, onerror=unreadable):
            if files:
                return True
            if any(os.path.islink(os.path.join(dirpath, name)) for name in dirs):
                return True
    except OSError:
        return True
    return False


def raise_if_legacy_state(legacy: Path, new_root: Path) -> None:
    if legacy_tree_holds_state(legacy):
        raise RuntimeError(
            f"{LEGACY_PRESENT_CODE}: {legacy} holds durable state; "
            f"move it to {new_root} or set NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR"
        )
