"""Nightly quarantine entry: tests/unit/verifiers/concurrency/test_concurrency_red.py (#1928). See package docstring."""

from __future__ import annotations

# Fixed in #1928: target3 RED demonstrates the AB/BA inversion deterministically (barrier + acquire timeout).
ENTRY = None
