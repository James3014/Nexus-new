import os
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:5001"
PILOT_KEY_ENV = "NEXUS_PILOT_API_KEY"


def test_pilot_live():
    pilot_key = os.environ.get(PILOT_KEY_ENV, "").strip()
    if not pilot_key:
        raise RuntimeError(f"{PILOT_KEY_ENV} is required for the live pilot test")

    print("// Nexus-Pilot Test: Initiating Live Test for [Tenant_Friend]...")
    
    # 1. Enqueue a governance task with the live key
    headers = {"X-Tenant-ID": "Tenant_Friend"}
    payload = {
        "api_key": pilot_key,
        "repo": "https://github.com/nexus-friend/pilot-repo",
        "action": {
            "type": "create_file",
            "path": str(Path(__file__).resolve().parents[1] / "workspaces/Tenant_Friend/pilot_proof.txt"),
            "content": "Nexus OS v17: Live key injection confirmed."
        }
    }
    
    print("// Nexus-Pilot Test: Dispatching /govern request...")
    res = requests.post(f"{BASE_URL}/govern", json=payload, headers=headers)
    
    if res.status_code == 200:
        data = res.json()
        pid = data.get("task_id")
        print(f"// Nexus-Pilot Test: SUCCESS. Task Spawned as PID [{pid}].")
        
        # 2. Verify Output & Sensing
        time.sleep(5)
        proof_path = str(Path(__file__).resolve().parents[1] / "workspaces/Tenant_Friend/pilot_proof.txt")
        if os.path.exists(proof_path):
            with open(proof_path, "r") as f:
                content = f.read()
                print(f"// Nexus-Pilot Test: Execution Proof found: {content}")
                assert "Live key injection confirmed" in content
        else:
            print("!! Nexus-Pilot Test: Execution Proof NOT FOUND.")
            assert False
    else:
        print(f"!! Nexus-Pilot Test: Request FAILED with {res.status_code} - {res.text}")
        assert False

if __name__ == "__main__":
    test_pilot_live()
