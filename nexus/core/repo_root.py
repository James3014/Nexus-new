"""Repository root of this Nexus-new checkout (host-owned, explicit for runtime planner calls)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
