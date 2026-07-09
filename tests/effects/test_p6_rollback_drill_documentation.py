"""P6-G7: Rollback Drill Tests."""
from __future__ import annotations

import json
import os
import pytest


def test_drill_artifact_exists():
    assert os.path.exists("artifacts/effect_reports/p6_rollback_drill_v0.json")


def test_drill_simulated_only():
    with open("artifacts/effect_reports/p6_rollback_drill_v0.json") as f:
        drill = json.load(f)
    assert drill["simulated_only"] is True
    assert drill["runtime_changed"] is False
    assert drill["public_claim_allowed"] is False
    assert drill["production_ready"] is False


def test_drill_has_triggers():
    with open("artifacts/effect_reports/p6_rollback_drill_v0.json") as f:
        drill = json.load(f)
    assert len(drill["rollback_triggers_tested"]) > 0
    assert len(drill["rollback_actions"]) > 0
