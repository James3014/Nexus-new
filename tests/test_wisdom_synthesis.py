import importlib.util

import pytest

from nexus.services.wisdom_synthesizer import WisdomSynthesizer

# nexus.services.predictive_audit and nexus.services.construction_service were deleted
# 2026-10-17 (#2475, dead-code batch B4, ARCHIVED_2026-10-17_deadcode_b4.md). Their test
# ids are kept and assert the modules stay gone; the wisdom loop test is unchanged.


@pytest.fixture
def project_root(tmp_path):
    # Hermetic: a throwaway project root instead of a host-specific checkout.
    return tmp_path


@pytest.fixture
def synthesizer(project_root):
    return WisdomSynthesizer(project_root)


def test_wisdom_synthesis_loop(synthesizer):
    """🛡️ Test the full Lesson -> Wisdom induction loop."""
    result = synthesizer.sync_all()
    assert result["status"] in ["SUCCESS", "EMPTY"]
    assert "rules_synthesized" in result


def test_predictive_audit_risk_detection():
    assert importlib.util.find_spec("nexus.services.predictive_audit") is None


def test_construction_gate_block():
    assert importlib.util.find_spec("nexus.services.construction_service") is None
