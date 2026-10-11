"""Compatibility facade for governance-owned CapabilityGate."""

import warnings

from nexus.governance.capability_gate import CapabilityGate, Phase

warnings.warn(
    "nexus.core.capability_gate has no production caller and is kept as lab-only "
    "(use nexus.governance.capability_gate; see #1740).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["CapabilityGate", "Phase"]
