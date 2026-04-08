import os
import json
import subprocess
import time
import signal

# [SOTA 10/10] Nexus Agent OS Kernel
# Implementation based on Sir's expert "Singularity OS" principles (Phase 6).

PROCESS_TABLE = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/process_table.json")

def nexus_spawn(config):
    tenant = config.get("tenant", "default")
    repo = config.get("repo", "unknown")
    phase = config.get("phase", "PXDRAC")
    api_key = config.get("api_key", "sk-default-dummy")
    action = config.get("action", {})
    
    # 1. Prepare Command (Execution Layer)
    # We construct a full ReflexRequest JSON payload
    request_payload = {
        "version": "v1.0",
        "request_id": f"os_task_{int(time.time())}",
        "tenant_id": tenant,
        "actor": "Nexus-OS-Kernel",
        "intent": "Pilot Live Test",
        "action": action
    }
    
    binary_path = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "nexus-reflex/target/debug/nexus-reflex-core")
    cmd = [
        binary_path,
        "--action", json.dumps(request_payload)
    ]
    
    # 2. Secret Silo Injection (Phase 2A)
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    
    # 3. Spawn Process
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    pid = proc.pid
    print(f"// Nexus-Kernel: [SPAWN] PID={pid} Tenant={tenant} Repo={repo} Action={action.get('type')}")
    
    # Record in process table
    table = {}
    if os.path.exists(PROCESS_TABLE):
        with open(PROCESS_TABLE, "r") as f:
            table = json.load(f)
            
    table[str(pid)] = {
        "tenant": tenant,
        "repo": repo,
        "phase": phase,
        "start_time": time.ctime(),
        "status": "running"
    }
    
    with open(PROCESS_TABLE, "w") as f:
        json.dump(table, f, indent=2)
        
    return pid

def nexus_kill(pid):
    try:
        os.kill(int(pid), signal.SIGTERM)
        print(f"// Nexus-Kernel: [KILL] PID={pid} terminated.")
        
        if os.path.exists(PROCESS_TABLE):
            with open(PROCESS_TABLE, "r") as f:
                table = json.load(f)
            if str(pid) in table:
                table[str(pid)]["status"] = "terminated"
                table[str(pid)]["end_time"] = time.ctime()
                with open(PROCESS_TABLE, "w") as f:
                    json.dump(table, f, indent=2)
        return True
    except ProcessLookupError:
        print(f"// Nexus-Kernel: [ERROR] PID={pid} not found.")
        return False

def nexus_ps():
    if not os.path.exists(PROCESS_TABLE):
        return {}
    with open(PROCESS_TABLE, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    # Test Kernel Operations
    pid = nexus_spawn({"tenant": "A", "repo": "/workspaces/A/monorepo", "phase": "PXDRAC"})
    print(f"// Current Processes: {json.dumps(nexus_ps(), indent=2)}")
    time.sleep(2)
    nexus_kill(pid)
