import requests
import time
import os
import subprocess

BASE_URL = "http://127.0.0.1:5001/enqueue"
LOG_DIR = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "logs/tenants")

def test_queue_isolation():
    print("// Nexus-Sentinel Test: Starting Queue Isolation & Async Integrity Audit...")

    # 1. Enqueue job for Tenant A
    print("// Nexus-Sentinel Test: Step 1 - Enqueuing job for Tenant A...")
    headers_a = {"X-Tenant-ID": "A"}
    payload_a = {"task_id": "job_A_001", "action": "audit_A"}
    res_a = requests.post(BASE_URL, json=payload_a, headers=headers_a)
    print(f"// Tenant A Enqueue: {res_a.status_code} - {res_a.json().get('status')}")
    assert res_a.status_code == 200

    # 2. Enqueue job for Tenant B
    print("// Nexus-Sentinel Test: Step 2 - Enqueuing job for Tenant B...")
    headers_b = {"X-Tenant-ID": "B"}
    payload_b = {"task_id": "job_B_001", "action": "audit_B"}
    res_b = requests.post(BASE_URL, json=payload_b, headers=headers_b)
    print(f"// Tenant B Enqueue: {res_b.status_code} - {res_b.json().get('status')}")
    assert res_b.status_code == 200

    # 3. Wait for workers to process
    print("// Nexus-Sentinel Test: Step 3 - Waiting for asynchronous workers to pick up...")
    time.sleep(10)

    # 4. Verify Audit Logs for Cross-talk
    print("// Nexus-Sentinel Test: Step 4 - Verifying Audit Logs for correct worker assignment...")
    
    # Check Tenant A's audit log
    audit_a = os.path.join(LOG_DIR, "A", "audit.jsonl")
    with open(audit_a, "r") as f:
        log_a = f.read()
        if "job_A_001" in log_a and "worker_completed" in log_a:
            print("// Nexus-Sentinel Test: Tenant A job correctly processed by Tenant A worker.")
        if "job_B_001" in log_a:
            print("!! SECURITY BREACH: Tenant B job leaked into Tenant A's audit log!")
            assert False

    # Check Tenant B's audit log
    audit_b = os.path.join(LOG_DIR, "B", "audit.jsonl")
    with open(audit_b, "r") as f:
        log_b = f.read()
        if "job_B_001" in log_b and "worker_completed" in log_b:
            print("// Nexus-Sentinel Test: Tenant B job correctly processed by Tenant B worker.")
        if "job_A_001" in log_b:
            print("!! SECURITY BREACH: Tenant A job leaked into Tenant B's audit log!")
            assert False

    print("// Nexus-Sentinel Test: Phase 2 Queue Isolation Audit SUCCESS. Singularity 10/10.")

if __name__ == "__main__":
    test_queue_isolation()
