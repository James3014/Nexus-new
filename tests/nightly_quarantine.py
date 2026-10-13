"""Explicit quarantine for the scheduled Tier 3 full regression (Refs #1897).

The list lives one module per entry in ``tests/nightly_quarantine_items/<slug>.py``
(``tests/nightly_quarantine_entries.py`` re-exports it; retire an entry with
``ENTRY = None``, never delete the file). It only applies when
``NEXUS_NIGHTLY_QUARANTINE=1``; every other run sees the tests unchanged.
Quarantined tests still run and are marked ``xfail(strict=False)``, so a fix
shows up as XPASS instead of being hidden by a skip.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import pytest

QUARANTINE_ENV = "NEXUS_NIGHTLY_QUARANTINE"
ISSUE_REFERENCE = re.compile(r"#[1-9][0-9]*")
DISPOSITIONS = frozenset({"quarantine", "delete-candidate", "quarantine-product-bug?"})


@dataclass(frozen=True)
class QuarantineEntry:
    file: str
    disposition: str
    issue: str
    cause: str
    tests: tuple[str, ...]


def load_quarantine(
    raw_entries: Iterable[Mapping[str, object]] | None = None,
) -> tuple[QuarantineEntry, ...]:
    if raw_entries is None:
        from tests.nightly_quarantine_entries import QUARANTINE

        raw_entries = QUARANTINE
    entries = []
    for item in raw_entries:
        entry = QuarantineEntry(
            file=str(item["file"]),
            disposition=str(item["disposition"]),
            issue=str(item["issue"]),
            cause=str(item["cause"]),
            tests=tuple(str(test) for test in item["tests"]),  # type: ignore[union-attr]
        )
        if entry.disposition not in DISPOSITIONS:
            raise ValueError(
                f"unknown quarantine disposition for {entry.file}: {entry.disposition}"
            )
        if not entry.cause.strip() or not entry.tests:
            raise ValueError(f"quarantine entry for {entry.file} needs a cause and tests")
        if not ISSUE_REFERENCE.fullmatch(entry.issue):
            raise ValueError(f"quarantine entry for {entry.file} needs a real Issue number (#N)")
        entries.append(entry)
    return tuple(entries)


def quarantine_reasons(entries: tuple[QuarantineEntry, ...]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for entry in entries:
        for test in entry.tests:
            node_id = f"{entry.file}::{test}"
            if node_id in reasons:
                raise ValueError(f"duplicate quarantine entry: {node_id}")
            reasons[node_id] = (
                f"NIGHTLY_QUARANTINE[{entry.disposition}; {entry.issue}]: {entry.cause}"
            )
    return reasons


def quarantine_enabled() -> bool:
    return os.environ.get(QUARANTINE_ENV) == "1"


def apply_quarantine(items: list[pytest.Item], reasons: dict[str, str]) -> int:
    marked = 0
    for item in items:
        reason = reasons.get(item.nodeid)
        if reason is not None:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
            marked += 1
    return marked
