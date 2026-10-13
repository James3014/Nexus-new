"""Compatibility facade for governance-owned CapabilityGate."""

import warnings

from nexus.governance.capability_gate import CapabilityGate, Phase

warnings.warn(
    "ARCHIVED 2026-10-13 (#1906): nexus.core.capability_gate facade has no production caller "
    "(lab-only since #1740; use nexus.governance.capability_gate); "
    "see ARCHIVED_2026-10-13.md. Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["CapabilityGate", "Phase"]
