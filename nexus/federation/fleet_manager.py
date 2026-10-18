from typing import Any, Dict, List, Optional, Tuple
import subprocess
import os
import random
import warnings

warnings.warn(
    "ARCHIVED 2026-10-12 (#1850; was lab-only #1740): stub fleet manager; "
    "see ARCHIVED_2026-10-12.md. Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)


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
    # #2637: the old body killed every process whose command line matched
    # "nexus_cli.py --swarm-mode" (name-matching kill), which breaks the
    # kill-by-PID-only rule and could hit other sessions' processes.
    raise RuntimeError(
        "ARCHIVED (#2637): stop_fleet no longer kills processes by name; "
        "stop nodes by PID. See ARCHIVED_2026-10-19-swarm-scripts.md."
    )

if __name__ == "__main__":
    # #2637: the CLI (hard-coded default token, name-matching stop) is retired.
    raise SystemExit("ARCHIVED (#2637): fleet manager CLI retired; see ARCHIVED_2026-10-19-swarm-scripts.md.")
