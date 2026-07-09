"""P7-A7: Operator Runbook Tests."""
from __future__ import annotations

import os
import pytest


def test_runbook_exists():
    assert os.path.exists("docs/runbooks/local_model_nexus_armor_operator_runbook_v0.md")


def test_runbook_mentions_phases():
    with open("docs/runbooks/local_model_nexus_armor_operator_runbook_v0.md") as f:
        text = f.read()
    assert "P3" in text
    assert "P6" in text
    assert "P2" in text
    assert "P4" in text
    assert "P5" in text


def test_runbook_forbids_production():
    with open("docs/runbooks/local_model_nexus_armor_operator_runbook_v0.md") as f:
        text = f.read()
    assert "No production rollout" in text or "production_ready=false" in text


def test_runbook_requires_human_approval():
    with open("docs/runbooks/local_model_nexus_armor_operator_runbook_v0.md") as f:
        text = f.read()
    assert "human approval" in text.lower() or "human-approved" in text.lower()


def test_runbook_has_rollback_triggers():
    with open("docs/runbooks/local_model_nexus_armor_operator_runbook_v0.md") as f:
        text = f.read()
    assert "Rollback Triggers" in text
