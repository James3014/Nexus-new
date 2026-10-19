"""Persistent root for layer-1 state stores (belief, memory, learning) (#2688).

Stateful capabilities keep their stores under ``<root>/.nexus/...``.  The root used
to be the workspace_root, the cwd or the checkout (``Path(__file__).parents[N]``).
That works for a long-lived checkout but not for the live Gateway, whose cwd and
workspace_root are a per-deploy directory recreated on every deploy, so the stores
always start empty there.

``NEXUS_STATE_ROOT`` names a fixed directory that outlives deploys.  Convention: the
returned root is the directory that *contains* ``.nexus`` -- callers keep appending
``.nexus/...`` exactly as before.  When the variable is unset or empty the caller's
own default comes back unchanged (same object), so behaviour is byte-for-byte the
old one.  A relative value is a misconfiguration (it would silently depend on the
cwd again) and raises ``ValueError``.
"""

from __future__ import annotations

import os
from pathlib import Path

STATE_ROOT_ENV = "NEXUS_STATE_ROOT"


def persistent_state_root(default: Path) -> Path:
    """Return the root that holds ``.nexus`` state: ``$NEXUS_STATE_ROOT`` or ``default``."""
    raw = os.environ.get(STATE_ROOT_ENV, "").strip()
    if not raw:
        return default
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError(f"{STATE_ROOT_ENV} must be an absolute path, got {raw!r}")
    return root.resolve()
