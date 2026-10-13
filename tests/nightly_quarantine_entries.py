"""Compatibility shim: the nightly quarantine list (Refs #1897).

The entries live one per module in tests/nightly_quarantine_items/ so parallel
PRs that add or remove entries do not conflict. This module keeps the historical
import path tests.nightly_quarantine_entries.QUARANTINE working.
"""

from __future__ import annotations

from tests.nightly_quarantine_items import QUARANTINE

__all__ = ["QUARANTINE"]
