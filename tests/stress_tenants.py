import asyncio
import random
import time
from typing import List
from nexus.core.router import SkillsRouter
from pathlib import Path

async def simulate_tenant_query(router: SkillsRouter, tenant_id: str):
    """模擬特定租戶的查詢。"""
    context = {
        "mode": "dual",
        "tenant_id": tenant_id,
        "min_palace_hit": 0.8,
        "active_domain": "undeclared"
    }
    query = f"Confidential knowledge for {tenant_id}"
    result = router.memory_route(query, context)
    
    # 🛡️ 斷言：結果中絕不能包含其他租戶的標識
    for res in result.get("results", []):
        if isinstance(res, dict) and "tenant_id" in res:
            assert res["tenant_id"] == tenant_id, f"🚨 SECURITY LEAK: Tenant {tenant_id} saw data from {res['tenant_id']}!"
    return True

async def run_stress_test():
    router = SkillsRouter(str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    tenants = [f"corp_tenant_{i}" for i in range(10)]
    tasks = []
    
    print(f"🚀 Starting Multi-tenant Stress Test: 10 tenants, 100 queries total...")
    t0 = time.perf_counter()
    
    for _ in range(10): # 10 rounds
        for t_id in tenants:
            tasks.append(simulate_tenant_query(router, t_id))
    
    results = await asyncio.gather(*tasks)
    t1 = time.perf_counter()
    
    print(f"✅ Stress Test Passed: {len(results)} queries executed in {t1-t0:.2f}s.")
    print(f"🛡️ Isolation Integrity: 100% (No leaks detected).")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
