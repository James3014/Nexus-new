"""Measurement-only directory scope for ``allowed_files`` (Issue #2721).

A benchmark task often names a package (``sympy/``, ``src/werkzeug/``) rather
than single files.  The scope checks of the worker path already treat a
boundary ending in ``/`` as a prefix (the directory and everything below it),
but the lifecycle action envelope and the pre-action guard refuse such an
entry.  On a frozen measurement Gateway started with
``NEXUS_MEASURE_DIR_SCOPE=1`` they accept it; the live Gateway never sets the
variable (the deployer's launch wrappers refuse to start with it), so for live
nothing here changes.

The variable is read ONCE, at import (= Gateway start), like
``nexus.orchestrator.measure_external_target``: setting it later has no
effect.  This module sits in ``nexus.contracts`` and imports only the standard
library, so both the contracts and the orchestrator layers can import it.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

MEASURE_DIR_SCOPE_ENV = "NEXUS_MEASURE_DIR_SCOPE"
# Snapshot taken once at import; only the exact value "1" enables it.
MEASURE_DIR_SCOPE_AT_START = str(os.environ.get(MEASURE_DIR_SCOPE_ENV, "") or "").strip() == "1"


def dir_scope_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """The start-time snapshot; ``env`` is an explicit override for unit tests only."""
    if env is None:
        return MEASURE_DIR_SCOPE_AT_START
    return str(env.get(MEASURE_DIR_SCOPE_ENV, "") or "").strip() == "1"


def split_dir_scope(value: str) -> Optional[str]:
    """``"src/pkg/"`` -> ``"src/pkg"`` for a candidate directory scope, else ``None``.

    A candidate ends in exactly one ``/`` and has a non-empty remainder that
    itself does not end in ``/``.  The remainder still has to pass the caller's
    own normalized-path check (no ``..``, no ``.git``, no ``.`` segment, not
    absolute).
    """
    if not isinstance(value, str) or not value.endswith("/"):
        return None
    stripped = value[:-1]
    if not stripped or stripped.endswith("/"):
        return None
    return stripped
