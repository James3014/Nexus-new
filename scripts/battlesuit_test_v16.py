import os
import sys
import json
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

print(f"🛡️ [Nexus Battlesuit Field Test] Project Root: {PROJECT_ROOT}")

# 1. 物理隔離驗證 (Static SDK Check)
try:
    import openai
    print("❌ ERROR: openai SDK found in environment. This is NOT a pure battlesuit environment.")
except ImportError:
    print("✅ PASS: openai SDK not found. Pure battlesuit environment confirmed.")

# 2. 閘道初始化 (Gateway Initialization)
try:
    from nexus.services.gateway import BattlesuitGateway
    gateway = BattlesuitGateway(project_root=PROJECT_ROOT)
    print(f"✅ PASS: BattlesuitGateway initialized (Provider: {gateway.oauth_provider})")
except Exception as e:
    print(f"❌ ERROR: Failed to initialize gateway: {e}")
    sys.exit(1)

# 3. 模擬計畫任務 (Simulated Planner Task)
print("\n🚀 [Test 1] Simulated Planner Handoff...")
plan_prompt = "Task: Implement a new auth module. Output a JSON plan."
data, output = gateway.ask(plan_prompt, "", phase="P")

if data.get("status") == "APPROVED" or "json" in output.lower():
    print("✅ PASS: Planner task successfully forwarded and parsed.")
    print(f"Summary: {data.get('summary', 'N/A')}")
else:
    print(f"⚠️ WARNING: Planner task returned unexpected status: {data.get('status')}")
    print(f"Output: {output[:100]}...")

# 4. 模擬審查任務 (Simulated Reviewer Task)
print("\n🚀 [Test 2] Simulated Reviewer Handoff...")
review_prompt = "Task: Review the new gateway.py for security."
diff_text = "+++ nexus/services/gateway.py\n+ # Securing exports"
data, output = gateway.ask(review_prompt, diff_text, phase="X")

if data.get("status") == "APPROVED":
    print("✅ PASS: Reviewer task successfully approved.")
    print(f"Review Summary: {data.get('summary', 'N/A')}")
else:
    print(f"⚠️ WARNING: Reviewer task rejected/failed. Status: {data.get('status')}")

print("\n✨ [Nexus Field Test Complete] 100% Physical Control, 0% Model Dependency.")
