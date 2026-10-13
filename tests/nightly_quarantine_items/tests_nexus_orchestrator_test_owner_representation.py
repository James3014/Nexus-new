"""Nightly quarantine entry: tests/nexus/orchestrator/test_owner_representation.py (#1924). See package docstring."""

from __future__ import annotations

# Removed (#1924): Owner decision inventories the workforce_model_autoupdate.py
# gh issue/pr create calls as a BOUNDED_INTERNAL_ONLY own-repo route
# (INVENTORIED_INTERNAL_WRITE_SINKS), so the source scan passes again.
ENTRY = None
