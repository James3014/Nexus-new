from nexus.core.router import SkillsRouter
from nexus.services.metabolism_engine import metabolism

def test_hud_visibility():
    router = SkillsRouter("/Users/jameschen/Workspace/nexus")
    ctx = {"tenant_id": "corp_gold", "active_domain": "Q1_Critical_Core", "skill_id": "core"}
    
    # 📡 Check P1 Default
    res = router.memory_route("Check status", ctx)
    print(f"📡 [HUD-P1] Status: {res.get('hud')}")
    assert "P1_RESEARCH" in res.get("hud")

    # 🔄 Trigger P4 via Metabolism
    router.p_loop.transition_to(router.p_loop.current_phase, {"action": "manual_trigger"}) # Get an EV-ID
    metabolism.distill({"goal": "test"}, p_manager=router.p_loop)
    
    print(f"📡 [HUD-P4] Status: {router.p_loop.get_hud_status()}")
    assert "P4_METABOLIZE" in router.p_loop.get_hud_status()

if __name__ == "__main__":
    test_hud_visibility()
