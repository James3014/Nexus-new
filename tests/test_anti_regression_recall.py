from nexus.core.router import SkillsRouter
from nexus.core.p_loop_manager import PPhase

def test_negative_context_injection():
    router = SkillsRouter("/Users/jameschen/Workspace/nexus")
    ctx = {"tenant_id": "corp_gold", "active_domain": "Q1_Critical_Core", "skill_id": "core"}
    
    # 🏃 1. Simulate P3 Failure
    router.p_loop.transition_to(PPhase.P3_IMPLEMENT)
    router.p_loop.handle_p3_failure("LINT_ERROR", "def foo(): print('bad')")
    
    # 🧠 2. Check if P2 route contains the lesson
    res = router.memory_route("Redesign the logic", ctx)
    
    print(f"🧠 [Recall] Negative Lessons found: {len(res.get('negative_lessons'))}")
    print(f"🧠 [Recall] First lesson error: {res.get('negative_lessons')[0]['evidence']['error']}")
    
    assert len(res.get('negative_lessons')) == 1
    assert res.get('negative_lessons')[0]['evidence']['error'] == "LINT_ERROR"
    assert res.get('p_phase') == "P2_DESIGN"
    print("✅ [ANTI-REGRESSION] Negative Lessons correctly injected into P2 context.")

if __name__ == "__main__":
    test_negative_context_injection()
