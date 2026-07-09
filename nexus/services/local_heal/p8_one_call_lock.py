from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LOCK_PATH = Path("artifacts/effect_reports/p8_one_call_lock_v0.json")


@dataclass(frozen=True)
class P8OneCallLock:
    """P8-E2: One-call execution lock."""
    lock_version: str
    smoke_id: str
    lock_created: bool
    lock_acquired: bool
    previous_lock_present: bool
    previous_network_call_count: int
    max_network_calls: int
    duplicate_execution_blocked: bool
    network_execution_allowed: bool
    blocked_reasons: list[str] = field(default_factory=list)


def acquire_p8_one_call_lock(
    previous_network_call_count: int = 0,
) -> P8OneCallLock:
    """Attempt to acquire one-call lock."""
    blocked_reasons: list[str] = []
    previous_lock_present = LOCK_PATH.exists()

    if previous_lock_present:
        blocked_reasons.append("previous_lock_exists")
        return P8OneCallLock(
            lock_version="1.0",
            smoke_id="",
            lock_created=False,
            lock_acquired=False,
            previous_lock_present=True,
            previous_network_call_count=previous_network_call_count,
            max_network_calls=1,
            duplicate_execution_blocked=True,
            network_execution_allowed=False,
            blocked_reasons=blocked_reasons,
        )

    if previous_network_call_count > 0:
        blocked_reasons.append("previous_network_call_exists")
        return P8OneCallLock(
            lock_version="1.0",
            smoke_id="",
            lock_created=False,
            lock_acquired=False,
            previous_lock_present=False,
            previous_network_call_count=previous_network_call_count,
            max_network_calls=1,
            duplicate_execution_blocked=False,
            network_execution_allowed=False,
            blocked_reasons=blocked_reasons,
        )

    smoke_id = f"smoke-{int(time.time())}"
    lock_data = {
        "lock_version": "1.0",
        "smoke_id": smoke_id,
        "lock_created": True,
        "max_network_calls": 1,
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as f:
        json.dump(lock_data, f, indent=2)

    return P8OneCallLock(
        lock_version="1.0",
        smoke_id=smoke_id,
        lock_created=True,
        lock_acquired=True,
        previous_lock_present=False,
        previous_network_call_count=previous_network_call_count,
        max_network_calls=1,
        duplicate_execution_blocked=False,
        network_execution_allowed=True,
        blocked_reasons=[],
    )


def p8_one_call_lock_to_dict(lock: P8OneCallLock) -> dict[str, Any]:
    return {
        "p8_lock_version": lock.lock_version,
        "p8_smoke_id": lock.smoke_id,
        "p8_lock_created": lock.lock_created,
        "p8_lock_acquired": lock.lock_acquired,
        "p8_previous_lock_present": lock.previous_lock_present,
        "p8_previous_network_call_count": lock.previous_network_call_count,
        "p8_max_network_calls": lock.max_network_calls,
        "p8_duplicate_execution_blocked": lock.duplicate_execution_blocked,
        "p8_network_execution_allowed": lock.network_execution_allowed,
        "p8_blocked_reasons": lock.blocked_reasons,
    }
