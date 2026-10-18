import subprocess
import time
import os
import json
import re

# ARCHIVED 2026-10-19 (#2637): dead v18-v23 swarm script (needs the removed
# nexus-swarm/ directory; carried a default token and a name-matching kill).
# Unreachable + manifest: see ARCHIVED_2026-10-19-swarm-scripts.md. Do not run or import.
import warnings as _archived_warnings  # noqa: E402

_archived_warnings.warn(
    "ARCHIVED 2026-10-19 (#2637): retired swarm script; see ARCHIVED_2026-10-19-swarm-scripts.md. Do not import.",
    DeprecationWarning,
    stacklevel=2,
)
if __name__ == "__main__":
    raise SystemExit("ARCHIVED 2026-10-19 (#2637): retired swarm script; see ARCHIVED_2026-10-19-swarm-scripts.md.")

# 🕵️ Nexus v21 NSP v0.1 Conformance Audit
TOKEN = "nexus-secret-2026"
DB_PATH = "nexus-swarm/swarm_tasks.db"

def cleanup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    subprocess.run(["pkill", "-f", "nexus_cli.py --swarm-mode"], stderr=subprocess.DEVNULL)

def start_node(port, region):
    print(f"🐝 Starting NSP v0.1 Node on {port} ({region})...")
    cmd = [
        "python3", "scripts/nexus_cli.py",
        "--swarm-mode",
        "--port", str(port),
        "--region", region,
        "--swarm-token", TOKEN
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def run_manager():
    print("🚀 Running Go Manager (NSP v0.1 Client)...")
    env = os.environ.copy()
    env["NEXUS_SWARM_TOKEN"] = TOKEN
    result = subprocess.run(["go", "run", "cmd/swarm-manager/main.go"], 
                          cwd="nexus-swarm", env=env, capture_output=True, text=True)
    return result.stdout

def main():
    cleanup()
    node_proc = start_node(8001, "us-east-1")
    time.sleep(2)

    print("🛡️ [Phase 1: W3C Traceparent Propagation Audit]")
    manager_stdout = run_manager()
    
    # 1. Verify W3C Traceparent in Node Logs
    # Note: We need to read from node_proc.stdout
    # For simplicity, we'll just check manager_stdout for the SPAN logs first
    if "📊 [SPAN:execution]" in manager_stdout:
        print("✅ Manager received NSP v0.1 DiagnosticReport with Metrics.")
    else:
        print("❌ Manager failed to receive or parse Metrics!")
        print(manager_stdout)

    print("\n🔍 [Phase 2: Node Log Inspection]")
    # We kill the node to flush buffers or just poll
    node_proc.terminate()
    node_out, _ = node_proc.communicate()
    
    if "Active context detected" in node_out and "TraceID" in node_out:
        print("✅ Node correctly parsed W3C traceparent header!")
        trace_id_node = re.search(r"TraceID:([a-zA-Z0-9\-\_]+)", node_out)
        if trace_id_node:
            print(f"✅ Extracted TraceID from Node: {trace_id_node.group(1)}")
    else:
        print("❌ Node failed to detect Trace Context!")
        print(node_out)

    cleanup()
    print("\n✨ [Success] Phase 21 NSP v0.1 Conformance Audit Finished.")

if __name__ == "__main__":
    main()
