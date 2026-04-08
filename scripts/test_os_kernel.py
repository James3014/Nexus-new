import requests
import json
import time
import os

BASE_URL = "http://127.0.0.1:5001"

def test_os_kernel():
    print("// Nexus-Singularity Test: Starting OS Kernel & Auto-Evolve Audit...")

    # 1. Spawn Multiple Governance Processes
    print("// Nexus-Singularity Test: Step 1 - Spawning parallel processes...")
    pids = []
    for i in range(5):
        headers = {"X-Tenant-ID": f"Tenant_{i}"}
        payload = {"repo": f"repo_{i}", "priority": i}
        res = requests.post(f"{BASE_URL}/govern", json=payload, headers=headers)
        pid = res.json().get("task_id")
        pids.append(pid)
        print(f"// Spawned: PID={pid} for Tenant_{i}")
        assert res.status_code == 200

    # 2. Verify Process Table (nexus_ps)
    print("// Nexus-Singularity Test: Step 2 - Verifying Process Table...")
    res_ps = requests.get(f"{BASE_URL}/os/ps")
    table = res_ps.json()
    print(f"// Active Processes tracked: {len(table)}")
    assert len(table) >= 5

    # 3. Trigger Auto-Evolution
    print("// Nexus-Singularity Test: Step 3 - Triggering Auto-Evolution Engine...")
    evolve_res = requests.post(f"{BASE_URL}/evolve", json={"focus": "repair_phase"})
    print(f"// Evolution Status: {evolve_res.json().get('status')}")
    assert evolve_res.status_code == 200

    # 4. Verify SOTA Leap in Leaderboard
    print("// Nexus-Singularity Test: Step 4 - Verifying SOTA Performance Leap...")
    with open(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/leaderboard.json"), "r") as f:
        board = json.load(f)
        new_sota = board.get("global_sota")
        print(f"// New System SOTA: {new_sota}% (Goal: > 85%)")
        assert new_sota >= 85.0
        assert board.get("version") == "v17_singularity"

    # 5. Cleanup (Kill one process)
    print("// Nexus-Singularity Test: Step 5 - Testing Kernel Kill...")
    kill_pid = pids[0]
    # In this mock, the proxy doesn't have a direct /os/kill endpoint but I can call it via script logic or just check ps table update
    from nexus_os_kernel import nexus_kill
    nexus_kill(kill_pid)
    
    res_ps_final = requests.get(f"{BASE_URL}/os/ps")
    final_table = res_ps_final.json()
    assert final_table[str(kill_pid)]["status"] == "terminated"

    print("// Nexus-Singularity Test: Phase 6 Singularity OS Audit SUCCESS. Singularity 10/10.")

if __name__ == "__main__":
    test_os_kernel()
