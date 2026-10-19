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
    """The packaged policy with the template worker's routes sent to the measurement worker.

    Only routes (direct, campaign, consumer, route defaults) that point at
    ``TEMPLATE_WORKER_ID`` move; every other route, worker and authority
    (review, main engineering, ...) is left exactly as packaged (Codex r1 #7).
    A dispatch that still resolves elsewhere is refused by
    ``assert_measurement_dispatch`` instead of silently using another model.
    """
    data = copy.deepcopy(base)
    workers = data.get("workers")
    if not isinstance(workers, dict) or not isinstance(workers.get(TEMPLATE_WORKER_ID), dict):
        raise ValueError(f"measurement policy template worker missing: {TEMPLATE_WORKER_ID}")
    if CLAUDE_MEASUREMENT_WORKER_ID in workers:
        raise ValueError(
            f"measurement worker id already in the packaged policy: {CLAUDE_MEASUREMENT_WORKER_ID}"
        )
    template = workers[TEMPLATE_WORKER_ID]
    worker = {
        key: copy.deepcopy(value)
        for key, value in template.items()
        if key not in _IDENTITY_FIELDS
        and not key.endswith("_note")
        and key != "calibration_evidence"
    }
    worker.update(
        provider=CLAUDE_MEASUREMENT_PROVIDER,
        model=CLAUDE_MEASUREMENT_MODEL,
        measurement_only_note=(
            "Nexus-new #2721 measurement worker; exists only when NEXUS_MEASUREMENT_CLAUDE_WORKER=1."
        ),
    )
    # The template's default-route role passes to the measurement worker.
    template["default_route"] = False
    workers[CLAUDE_MEASUREMENT_WORKER_ID] = worker
    online = (data.get("routing") or {}).get("online")
    if not isinstance(online, dict):
        raise ValueError("measurement policy: routing.online missing")
    for role, target in list(online.items()):
        if target == TEMPLATE_WORKER_ID:
            online[role] = CLAUDE_MEASUREMENT_WORKER_ID
    for scope_key in ("campaign_routing", "consumer_routing"):
        scoped = online.get(scope_key)
        if isinstance(scoped, dict):
            for overrides in scoped.values():
                if isinstance(overrides, dict):
                    for role, target in list(overrides.items()):
                        if target == TEMPLATE_WORKER_ID:
                            overrides[role] = CLAUDE_MEASUREMENT_WORKER_ID
    defaults = online.get("route_defaults")
    if isinstance(defaults, dict):
        for entry in defaults.values():
            if isinstance(entry, dict) and entry.get("current_default") == TEMPLATE_WORKER_ID:
                entry["current_default"] = CLAUDE_MEASUREMENT_WORKER_ID
    return data


def assert_measurement_dispatch(provider: str, model: str) -> None:
    """On a measurement Gateway every P1 dispatch must be the measurement model."""
    if measurement_claude_enabled() and (provider, model) != (
        CLAUDE_MEASUREMENT_PROVIDER,
        CLAUDE_MEASUREMENT_MODEL,
    ):
        raise ValueError(f"measurement_dispatch_not_claude:{provider}/{model}")


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
