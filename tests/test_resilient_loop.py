from nexus.core.p_loop_manager import PLoopManager, PPhase
from nexus.core.router import SkillsRouter

def test_non_linear_learning():
    p_manager = PLoopManager("corp_gold")
    
    # 1. P1 -> P2 -> P3
    p_manager.transition_to(PPhase.P2_DESIGN)
    p_manager.transition_to(PPhase.P3_IMPLEMENT)
    assert p_manager.current_phase == PPhase.P3_IMPLEMENT
    print(f"📡 [Test:P3] Current State: {p_manager.get_hud_status()}")

    # 🔄 2. FAILURE IN P3 -> JUMP TO P2
    p_manager.handle_retry("Test failed in P3: Stripe Keys missing")
    assert p_manager.current_phase == PPhase.P2_DESIGN
    assert len(p_manager.session_failures) == 1
    print(f"🔄 [Test:RETRY] HUD updated: {p_manager.get_hud_status()}")
    print(f"🧠 [Test:RETRY] Failure Evidence: {p_manager.session_failures[0]['evidence_id']}")

if __name__ == "__main__":
    test_non_linear_learning()
