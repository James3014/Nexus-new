#!/usr/bin/env python3
# 🛡️ Swarm Shadow Audit Stress Test (Multi-cluster Load)
import asyncio
import aiohttp
import time
import statistics
import json
from datetime import datetime

# 🔗 Production Endpoint (Local Proxy or Ingress)
SHADOW_WEBHOOK_URL = "http://localhost:8081/shadow-audit"

async def shadow_audit_pr(session, pr_num):
    payload = {
        "pr_number": pr_num,
        "repository": "nexus/nexus-swarm",
        "branch": "main",
        "author": f"stress-bot-{pr_num:03d}",
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "test_run": "P7-STAGING-ROLLOUT",
            "batch": 1
        }
    }
    
    start_time = time.perf_counter()
    try:
        async with session.post(SHADOW_WEBHOOK_URL, json=payload, timeout=10) as resp:
            duration = (time.perf_counter() - start_time) * 1000
            content = await resp.json()
            return {
                "pr": pr_num,
                "status": resp.status,
                "latency_ms": duration,
                "accepted": content.get("status") == "accepted"
            }
    except Exception as e:
        return {"pr": pr_num, "status": "ERROR", "error": str(e), "latency_ms": 0}

async def run_stress_test(total_pr=100, concurrency=20):
    print(f"🛡️ Launching Stress Test: {total_pr} PRs with concurrency {concurrency}...")
    print(f"🔗 Target: {SHADOW_WEBHOOK_URL}")
    
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [shadow_audit_pr(session, i) for i in range(1, total_pr + 1)]
        results = await asyncio.gather(*tasks)
        
    # Analyze Results
    successes = [r for r in results if r["status"] == 202 or r["status"] == 200]
    latencies = [r["latency_ms"] for r in successes if r["latency_ms"] > 0]
    
    print("\n" + "="*40)
    print("📋 STRESS TEST REPORT (Batch 7.1)")
    print("="*40)
    print(f"Total Requests: {total_pr}")
    print(f"Success/Accepted: {len(successes)}/{total_pr}")
    
    if latencies:
        print(f"Avg Latency: {statistics.mean(latencies):.2f}ms")
        print(f"P95 Latency: {statistics.quantiles(latencies, n=20)[18]:.2f}ms")
        print(f"Min/Max: {min(latencies):.2f}ms / {max(latencies):.2f}ms")
    
    if len(successes) == total_pr:
        print("\n✅ PASS: Swarm Capacity Validated.")
    else:
        print("\n❌ FAILURE: Some requests dropped or timed out.")
    print("="*40)

if __name__ == "__main__":
    # Ensure dependencies are available (In a real run, use 'uv run')
    try:
        asyncio.run(run_stress_test(100, 20))
    except KeyboardInterrupt:
        pass
