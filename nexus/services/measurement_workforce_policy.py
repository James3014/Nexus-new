"""Measurement-only workforce policy for the #2721 Claude worker.

On a measurement Gateway (``NEXUS_MEASUREMENT_CLAUDE_WORKER=1``) every online
route resolves to one worker, ``claude_haiku_measure`` (provider ``claude``,
model ``claude-haiku-5-5``), so P1 dispatches the same model the BARE arm
runs.  The policy is the packaged runtime policy plus that worker; the worker
copies the admission profile (state, autonomy, required controls, forbidden
actions) of the default fast implementation worker, so admission applies the
same rules and only the identity changes.

With the switch off (every live process) ``measurement_workforce_policy_loader``
returns None and callers keep the packaged policy exactly as before.
"""

from __future__ import annotations

import copy
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

from nexus.executors.claude_measurement_worker import (
    CLAUDE_MEASUREMENT_MODEL,
    CLAUDE_MEASUREMENT_PROVIDER,
    CLAUDE_MEASUREMENT_WORKER_ID,
    measurement_claude_enabled,
)

# The worker whose admission profile the measurement worker copies.
TEMPLATE_WORKER_ID = "agy_flash_38"
_IDENTITY_FIELDS = ("provider", "model")


def measurement_policy_document(base: dict[str, Any]) -> dict[str, Any]:
    """The packaged policy with every online route sent to the measurement worker."""
    data = copy.deepcopy(base)
    workers = data.get("workers")
    if not isinstance(workers, dict) or not isinstance(workers.get(TEMPLATE_WORKER_ID), dict):
        raise ValueError(f"measurement policy template worker missing: {TEMPLATE_WORKER_ID}")
    if CLAUDE_MEASUREMENT_WORKER_ID in workers:
        raise ValueError(f"measurement worker id already in the packaged policy: {CLAUDE_MEASUREMENT_WORKER_ID}")
    worker = {
        key: copy.deepcopy(value)
        for key, value in workers[TEMPLATE_WORKER_ID].items()
        if key not in _IDENTITY_FIELDS and not key.endswith("_note") and key != "calibration_evidence"
    }
    online = (data.get("routing") or {}).get("online")
    if not isinstance(online, dict):
        raise ValueError("measurement policy: routing.online missing")
    roles = sorted(role for role, target in online.items() if isinstance(target, str))
    worker.update(
        provider=CLAUDE_MEASUREMENT_PROVIDER,
        model=CLAUDE_MEASUREMENT_MODEL,
        roles=roles,
        default_route=True,
        measurement_only_note=(
            "Nexus-new #2721 measurement worker; exists only when NEXUS_MEASUREMENT_CLAUDE_WORKER=1."
        ),
    )
    # The policy requires exactly one advertised default per defaulted role.
    for other in workers.values():
        if isinstance(other, dict) and other.get("default_route") is True:
            other["default_route"] = False
    workers[CLAUDE_MEASUREMENT_WORKER_ID] = worker
    for role in roles:
        online[role] = CLAUDE_MEASUREMENT_WORKER_ID
    defaults = online.get("route_defaults")
    if isinstance(defaults, dict):
        for role, entry in defaults.items():
            if isinstance(entry, dict) and role in roles:
                entry["current_default"] = CLAUDE_MEASUREMENT_WORKER_ID
                if entry.get("fallback") == CLAUDE_MEASUREMENT_WORKER_ID:
                    raise ValueError(f"measurement policy: {role} fallback equals the measurement worker")
    # Exact campaign / consumer overrides would route around the measurement worker.
    online["campaign_routing"] = {}
    online["consumer_routing"] = {}
    return data


def _materialized_policy_path(base_path: Path) -> Path:
    base_text = base_path.read_text(encoding="utf-8")
    document = measurement_policy_document(yaml.safe_load(base_text))
    text = yaml.safe_dump(document, sort_keys=True, allow_unicode=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    root = Path(tempfile.gettempdir()) / "nexus-measurement-workforce"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"model_workforce.measure-2721.{digest[:16]}.yaml"
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        partial = target.with_suffix(f".{os.getpid()}.tmp")
        partial.write_text(text, encoding="utf-8")
        os.replace(partial, target)
    return target


def measurement_workforce_policy_loader() -> Optional[Any]:
    """A loader for the measurement policy, or None when the switch is off."""
    if not measurement_claude_enabled():
        return None
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    path = _materialized_policy_path(Path(WorkforcePolicyLoader.DEFAULT_POLICY_PATH))
    return WorkforcePolicyLoader(policy_path=path)
