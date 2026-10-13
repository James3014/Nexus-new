"""Nightly quarantine entry: tests/unit/local_heal/test_local_model_executor.py (#1924). See package docstring."""

from __future__ import annotations

# Fixed in #1924: was polluted by run_june_regression_pack env leak; run_pack now restores env.
ENTRY = None
