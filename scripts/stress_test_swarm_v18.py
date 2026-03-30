import subprocess
import time
import requests
import os
import signal

def run_stress_test():
    print("🚀 [Stress:Start] Initiating v18.1 Reliability Test...")
    
    # 1. Start 3 Nodes
    nodes = []
    env = os.environ.copy()
    # Ensure nodes can see the nexus_core.so in scripts/engine
    env["PYTHONPATH"] = f"{os.getcwd()}/scripts/engine:{env.get('PYTHONPATH', '')}"

    for port in [8001, 8002, 8003]:
        p = subprocess.Popen(
            ["python3", "scripts/nexus_cli.py", "--swarm-mode", "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env
        )
        nodes.append({"port": port, "proc": p})
        print(f"  - Node on {port} started (PID: {p.pid})")

    time.sleep(3) # Wait for startup

    # 2. Kill one node (first one) to force fallback
    print("💀 [Stress:Attack] Killing Node on 8001 to simulate fault...")
    nodes[0]["proc"].terminate()
    
    # 3. Run Go Swarm Manager
    print("📡 [Stress:Dispatch] Running Swarm Manager with one dead node...")
    try:
        result = subprocess.run(
            ["go", "run", "cmd/swarm-manager/main.go"],
            cwd="nexus-swarm",
            capture_output=True, text=True
        )
        print("\n--- Swarm Manager Output ---")
        print(result.stdout)
        
        if "connect: connection refused" in result.stdout or "context deadline exceeded" in result.stdout:
            print("✅ [Stress:Success] Manager correctly identified the dead node and timed out/failed gracefully.")
        else:
            print("❌ [Stress:Fail] Manager did not report the expected failure.")

    except Exception as e:
        print(f"💥 [Stress:Error] {e}")

    # Cleanup
    print("\n🧹 [Stress:Cleanup] Cleaning up remaining nodes...")
    for node in nodes:
        try:
            os.kill(node["proc"].pid, signal.SIGTERM)
        except:
            pass

if __name__ == "__main__":
    run_stress_test()
