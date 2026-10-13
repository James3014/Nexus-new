"""Per-predictor on/off switches and the ``predictor_influence`` receipt entry.

``NEXUS_LATENT_PREDICTOR`` gates ``latent_predictor_v20`` and defaults to on. A value
of ``0``, ``false``, ``no`` or ``off`` turns the predictor off, and the call site then
takes the path it would take if the predictor module were absent.

The ``lewm_predictor`` module was archived on 2026-10-12 (see ``ARCHIVED_2026-10-12.md``):
nothing consults it any more. ``LEWM_PREDICTOR`` and its env name remain only so the
frozen predictor-ablation harness (``scripts/eval/run_predictor_ablation.py``) still
imports; ``NEXUS_LEWM_PREDICTOR`` has no effect on any call site.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from typing import Any

LATENT_PREDICTOR = "latent_predictor_v20"
LEWM_PREDICTOR = "lewm_predictor"  # archived 2026-10-12; inert, see module docstring

_ENV_BY_PREDICTOR = {
    LATENT_PREDICTOR: "NEXUS_LATENT_PREDICTOR",
    LEWM_PREDICTOR: "NEXUS_LEWM_PREDICTOR",
}
_OFF_VALUES = {"0", "false", "no", "off"}

_LEDGER: deque[dict[str, Any]] = deque(maxlen=10000)
_LEDGER_LOCK = threading.Lock()


def env_name(name: str) -> str:
    return _ENV_BY_PREDICTOR[name]


def predictor_enabled(name: str) -> bool:
    """True unless the predictor's env switch is set to an off value."""
    return os.environ.get(_ENV_BY_PREDICTOR[name], "").strip().lower() not in _OFF_VALUES


def influence_entry(
    name: str,
    *,
    enabled: bool,
    consulted: bool,
    before: Any = None,
    after: Any = None,
    site: str = "",
) -> dict[str, Any]:
    """Build the ``predictor_influence`` entry.

    ``before`` is the decision the site takes without the predictor and ``after`` is
    the decision it actually took. ``changed_decision`` is only true when the
    predictor was consulted and the two differ.
    """
    entry: dict[str, Any] = {
        "name": name,
        "enabled": bool(enabled),
        "consulted": bool(consulted),
        "changed_decision": bool(consulted and before != after),
        "before": before,
        "after": after,
    }
    if site:
        entry["site"] = site
    return entry


def record_influence(
    entry: dict[str, Any], *, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Append the entry to ``metadata['predictor_influence']`` and the process ledger."""
    if metadata is not None:
        bucket = metadata.setdefault("predictor_influence", [])
        if isinstance(bucket, list):
            bucket.append(entry)
    with _LEDGER_LOCK:
        _LEDGER.append(dict(entry))
    return entry


def drain_ledger() -> list[dict[str, Any]]:
    """Return and clear the process-level ledger (used by the ablation script)."""
    with _LEDGER_LOCK:
        items = list(_LEDGER)
        _LEDGER.clear()
    return items
