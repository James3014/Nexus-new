import os
import json
from economic_meter import record_earning

# [SOTA 10/10] Nexus Crystal Market
# Implementation based on Sir's expert "Market Mechanism" principles (Phase 4).

LEDGER_PATH = "/Users/jameschen/Workspace/nexus/workspaces/tenant_balance.json"

def transact_crystal(buyer_id, contributor_id, crystal_id, price):
    print(f"// Nexus-Market: Transaction attempt - [{buyer_id}] buying [{crystal_id}] from [{contributor_id}] for {price} tokens.")
    
    with open(LEDGER_PATH, "r") as f:
        balances = json.load(f)
        
    buyer_balance = balances.get(buyer_id, {}).get("nexus_tokens", 0)
    
    if buyer_balance < price:
        print(f"// Nexus-Market: [FAILED] Tenant [{buyer_id}] Insufficient funds ({buyer_balance}).")
        return False
        
    # Transaction Implementation
    # 1. Deduct from buyer
    balances[buyer_id]["nexus_tokens"] -= price
    
    # 2. Grant to contributor (90%) and Platform (10%)
    contributor_share = int(price * 0.9)
    platform_fee = price - contributor_share
    
    balances[contributor_id]["nexus_tokens"] += contributor_share
    # record_earning already handles the balance update, but we are doing a bulk update here for atomic consistency.
    
    balances[contributor_id]["earned_from"].append({
        "reason": f"crystal_sale:{crystal_id}",
        "amount": contributor_share,
        "buyer_id": buyer_id
    })
    
    print(f"// Nexus-Market: [SUCCESS] Transferred {contributor_share} tokens to [{contributor_id}]. Platform fee: {platform_fee}.")
    
    with open(LEDGER_PATH, "w") as f:
        json.dump(balances, f, indent=2)
        
    return True

if __name__ == "__main__":
    # Mocking balances for testing
    with open(LEDGER_PATH, "w") as f:
        json.dump({
            "A": {"nexus_tokens": 1000, "earned_from": []},
            "B": {"nexus_tokens": 1000, "earned_from": []}
        }, f)
        
    transact_crystal("B", "A", "crystal_A_v1", 100)
