import subprocess
import os
import argparse
import random
from typing import List, Dict, Any

def get_node_id(port: int, region: str) -> str:
    return f"node-{port}-{region}"

def start_fleet(count: int, token: str) -> None:
    print(f"🚀 Starting {count} Virtual Nodes...")
    regions = ["us-east-1", "ap-northeast-1", "eu-central-1"]
    
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
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if i % 10 == 0 and i > 0:
            print(f"  ... {i} nodes launched.")

    print(f"✅ Fleet of {count} nodes is live. They will self-register via heartbeat.")

def stop_fleet() -> None:
    print("🛑 Shutting down all Nexus nodes...")
    subprocess.run(["pkill", "-f", "nexus_cli.py --swarm-mode"])
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
