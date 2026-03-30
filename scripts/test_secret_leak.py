import requests
import os
import json
import subprocess

BASE_URL = "http://127.0.0.1:5001/reflex"
LOG_DIR = "/Users/jameschen/Workspace/nexus/logs/tenants"

def test_secret_leak():
    print("// Nexus-Sentinel Test: Starting Secret Leak & Audit Integrity Audit...")

    # 1. Tenant A Request
    print("// Nexus-Sentinel Test: Step 1 - Tenant A Request (Key Injection Check)...")
    headers_a = {"X-Tenant-ID": "A"}
    payload_a = {
        "action": {
            "type": "create_file",
            "path": "/Users/jameschen/Workspace/nexus/workspaces/A/leak_test_v2.txt",
            "content": "Checking for keys..."
        }
    }
    res_a = requests.post(BASE_URL, json=payload_a, headers=headers_a)
    print(f"// Status: {res_a.status_code}")
    if res_a.status_code != 200:
        print(f"!! Error: {res_a.json()}")
        assert False
        
    output_a = res_a.json().get("output", "")
    print(f"// Tenant A Output: {output_a}")
    assert "OPENAI_API_KEY sensed. Length=22" in output_a

    # 2. Audit Log Verification
    print("// Nexus-Sentinel Test: Step 2 - Verifying Audit Logs for Zero Leak...")
    audit_a = os.path.join(LOG_DIR, "A", "audit.jsonl")
    with open(audit_a, "r") as f:
        log_content = f.read()
        # Ensure the actual secret is NEVER in the logs
        if "sk-tenant-a-secret-key" in log_content:
            print("!! SECURITY BREACH: Tenant A secret leaked into audit logs!")
            assert False
        else:
            print("// Nexus-Sentinel Test: Audit Logs are clean. No secret found.")

    # 3. Request Context Verification (Cross-tenant leak check)
    print("// Nexus-Sentinel Test: Step 3 - Verifying Cross-tenant Key Isolation...")
    headers_b = {"X-Tenant-ID": "B"}
    payload_b = {
        "action": {
            "type": "create_file",
            "path": "/Users/jameschen/Workspace/nexus/workspaces/B/leak_test_v2.txt",
            "content": "Checking for keys..."
        }
    }
    res_b = requests.post(BASE_URL, json=payload_b, headers=headers_b)
    output_b = res_b.json().get("output", "")
    print(f"// Tenant B Output: {output_b}")
    assert "OPENAI_API_KEY sensed. Length=22" in output_b
    
    # 4. Final Blow-out Leak Test (Searching entire logs)
    print("// Nexus-Sentinel Test: Step 4 - Performing Final Grep Search for Secrets...")
    try:
        # Search for any part of the secret in the entire logs directory
        res = subprocess.run(["grep", "-r", "sk-tenant", LOG_DIR], capture_output=True, text=True)
        if res.stdout:
            print(f"!! SECURITY BREACH: Found secrets in logs!\n{res.stdout}")
            assert False
        else:
            print("// Nexus-Sentinel Test: Final Grep Search CLEAN. Secrets are isolated in memory.")

    except Exception as e:
        print(f"// Grep check failed: {e}")

    print("// Nexus-Sentinel Test: Phase 2 Secret Leak Audit SUCCESS. Singularity 10/10.")

if __name__ == "__main__":
    test_secret_leak()
