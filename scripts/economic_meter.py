import os
import json
from datetime import datetime

# [SOTA 10/10] Nexus Economic Meter
# Implementation based on Sir's expert "Economic Layer" principles (Phase 4).

LEDGER_PATH = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/tenant_balance.json")

def record_earning(tenant_id, amount, reason):
    if not os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, "w") as f:
            json.dump({}, f)
            
    with open(LEDGER_PATH, "r") as f:
        balances = json.load(f)
        
    if tenant_id not in balances:
        balances[tenant_id] = {
            "nexus_tokens": 1000, # Initial grant
            "earned_from": [],
            "redeemable_for": ["premium_quota"]
        }
        
    balances[tenant_id]["nexus_tokens"] += amount
    balances[tenant_id]["earned_from"].append({
        "reason": reason,
        "amount": amount,
        "timestamp": datetime.now().isoformat()
    })
    
    with open(LEDGER_PATH, "w") as f:
        json.dump(balances, f, indent=2)
        
    print(f"// Nexus-Economic: Tenant [{tenant_id}] earned {amount} tokens. Reason: {reason}")

def measure_contribution(crystal):
    # Logic based on quality and adoption (mocked for now)
    base_points = 10
    if crystal.get("success_rate", 0) > 0.9:
        base_points += 5
    return base_points

if __name__ == "__main__":
    # Test earning
    record_earning("A", 50, "wisdom_share_bonus")
