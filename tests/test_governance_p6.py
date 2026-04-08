from nexus.services.governance_sink import gov_sink
from nexus.core.p_loop_manager import PLoopManager, PPhase

def test_p6_governance():
    p_manager = PLoopManager("corp_gold")
    p_manager.transition_to(PPhase.P6_SETTLE, {"action": "final_delivery"})
    
    ev_id = p_manager.evidence_log[-1]["evidence_id"]
    essence = {
        "lineage": "session_12345",
        "active_domain": "Q3_Research_Exp",
        "delta": "+40% IQ Lift verified"
    }
    
    # 📝 P6a Execution
    draft_path = gov_sink.write_p6a_draft(essence, ev_id)
    print(f"📝 [P6a] Draft created at: {draft_path}")
    assert os.path.exists(draft_path)

    # 🚫 P6b Execution (Should fail/lock)
    promoted = gov_sink.request_p6b_promotion(ev_id)
    assert promoted == False
    print("✅ [P6b] Promotion Gate LOCKED as expected.")

import os
if __name__ == "__main__":
    test_p6_governance()
