import asyncio
from nexus.core.router import SkillsRouter

async def verify_billing_gate():
    router = SkillsRouter(str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    
    # 🧪 Test Case 1: Active Tenant
    active_ctx = {"tenant_id": "corp_gold", "mode": "palace"}
    res_active = router.memory_route("hello", active_ctx)
    print(f"✅ Active Tenant Status: {res_active.get('status', 'OK')}")
    
    # ❌ Test Case 2: Suspended Tenant
    blocked_ctx = {"tenant_id": "tenant_blocked", "mode": "palace"}
    res_blocked = router.memory_route("hello", blocked_ctx)
    print(f"🛑 Blocked Tenant Status: {res_blocked.get('status')}")
    assert res_blocked.get("status") == "BLOCKED"

if __name__ == "__main__":
    asyncio.run(verify_billing_gate())
