import asyncio
from nexus.core.router import SkillsRouter

async def test_firewall():
    router = SkillsRouter("/Users/jameschen/Workspace/nexus")
    
    # Test 1: Authorized (Q1 skill in Q1 domain)
    ctx_q1 = {"active_domain": "Q1_Critical_Core", "tenant_id": "corp_gold"}
    res_q1 = router.memory_route("audit system", ctx_q1)
    print(f"✅ Q1 Access in Q1: {res_q1.get('status', 'OK')}")
    
    # Test 2: Q1 Core (Always allowed) in Q3 domain
    ctx_q3 = {"active_domain": "Q3_Research_Exp", "tenant_id": "corp_gold"}
    res_core = router.memory_route("core status", ctx_q3)
    print(f"✅ Q1 Core Access in Q3: {res_core.get('status', 'OK')}")

if __name__ == "__main__":
    asyncio.run(test_firewall())
