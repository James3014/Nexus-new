import subprocess
import time
import os
import signal
import argparse
import json
import random

# 🐝 Nexus Node Fleet Manager v22
# Helps start/stop many virtual nodes for scaling tests.

NODES_FILE = "nexus-swarm/nodes.json"

def get_node_id(port, region):
    return f"node-{port}-{region}"

def start_fleet(count, token):
    print(f"🚀 Starting {count} Virtual Nodes...")
    regions = ["us-east-1", "ap-northeast-1", "eu-central-1"]
    nodes_info = []
    
    for i in range(count):
        port = 8001 + i
        region = random.choice(regions)
        cmd = [
            "python3", "scripts/nexus_cli.py",
            "--swarm-mode",
            "--port", str(port),
            "--region", region,
            "--swarm-token", token
        ]
        # Run in background, redirect output to suppress terminal noise
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        nodes_info.append({
            "url": f"http://localhost:{port}",
            "region": region
        })
        if i % 10 == 0 and i > 0:
            print(f"  ... {i} nodes launched.")

    # Save to nodes.json
    with open(NODES_FILE, "w") as f:
        json.dump(nodes_info, f, indent=2)
    
    print(f"✅ Fleet of {count} nodes is live. nodes.json updated.")

def stop_fleet():
    print("🛑 Shutting down all Nexus nodes...")
    # Using pkill for simplicity in this environment
    subprocess.run(["pkill", "-f", "nexus_cli.py --swarm-mode"])
    if os.path.exists(NODES_FILE):
        os.remove(NODES_FILE)
    print("✅ All nodes stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop"])
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--token", type=str, default="nexus-secret-2026")
    
    args = parser.parse_args()
    if args.action == "start":
        start_fleet(args.count, args.token)
    elif args.action == "stop":
        stop_fleet()
