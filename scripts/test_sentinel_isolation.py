import requests
import time
import os
import json

BASE_URL = "http://127.0.0.1:5001/reflex"

# [SOTA 10/10] Multi-tenant Sentinel Isolation Test
# Verification based on Sir's expert E2E criteria.

def test_isolation():
    print("// Nexus-Sentinel Test: Starting E2E Isolation Audit...")
    
    # 1. Tenant A: Create file in its own workspace
    print("// Nexus-Sentinel Test: Step 1 - Tenant A creating file...")
    payload_a = {
        "action": {
            "type": "create_file",
            "path": str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/A/test_A.txt"),
            "content": "Secret content for Tenant A"
        }
    }
    headers_a = {"X-Tenant-ID": "A"}
    res_a = requests.post(BASE_URL, json=payload_a, headers=headers_a)
    print(f"// Tenant A Result: {res_a.status_code} - {res_a.json().get('status')}")
    assert res_a.status_code == 200

    # 2. Tenant B: Attempt to write to Tenant A's workspace (Malicious)
    print("// Nexus-Sentinel Test: Step 2 - Tenant B attempting to write to Tenant A's workspace...")
    payload_b_malicious = {
        "action": {
            "type": "create_file",
            "path": str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/A/test_B_malicious.txt"),
            "content": "I am Tenant B"
        }
    }
    headers_b = {"X-Tenant-ID": "B"}
    res_b_malicious = requests.post(BASE_URL, json=payload_b_malicious, headers=headers_b)
    print(f"// Tenant B Malicious Result: {res_b_malicious.status_code} - Error expected.")
    # Expected result: Rust core returns 403 (mapped by proxy) due to guard_action TENANT_VIOLATION
    assert res_b_malicious.status_code == 403
    assert "TENANT_VIOLATION" in res_b_malicious.json().get("message")

    # 3. Tenant B: Actions in its own workspace
    print("// Nexus-Sentinel Test: Step 3 - Tenant B creating its own file...")
    payload_b_valid = {
        "action": {
            "type": "create_file",
            "path": str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/B/test_B.txt"),
            "content": "Secret content for Tenant B"
        }
    }
    res_b_valid = requests.post(BASE_URL, json=payload_b_valid, headers=headers_b)
    print(f"// Tenant B Valid Result: {res_b_valid.status_code} - {res_b_valid.json().get('status')}")
    assert res_b_valid.status_code == 200

    print("// Nexus-Sentinel Test: E2E Isolation Audit SUCCESS. Singularity 10/10.")

if __name__ == "__main__":
    test_isolation()
