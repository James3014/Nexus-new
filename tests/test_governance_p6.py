import importlib.util

from nexus.core.p_loop_manager import PLoopManager, PPhase


def test_p6_governance():
    # nexus.services.governance_sink (the P6a/P6b draft sink this test drove) was deleted
    # 2026-10-17 (#2475, dead-code batch B4, ARCHIVED_2026-10-17_deadcode_b4.md). The test
    # id is kept: the P6 settle transition still records evidence, and the sink stays gone.
    p_manager = PLoopManager("corp_gold")
    p_manager.transition_to(PPhase.P6_SETTLE, {"action": "final_delivery"})

    assert p_manager.evidence_log[-1]["evidence_id"]
    assert importlib.util.find_spec("nexus.services.governance_sink") is None


if __name__ == "__main__":
    test_p6_governance()
