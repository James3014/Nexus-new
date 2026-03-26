#!/bin/bash

# 🛡️ Nexus-Go Swarm v18.2 Pragmatic Hardening Test
REPO_ROOT=$(pwd)
TOKEN="nexus-secret-2026"

echo "🛡️ [Setup] Starting 3 Nodes with Security Token..."

# 啟動 Node 1 (Correct Token)
python3 scripts/nexus_cli.py --swarm-mode --port 8001 --swarm-token $TOKEN > /tmp/nexus_node_8001.log 2>&1 &
# 啟動 Node 2 (Correct Token)
python3 scripts/nexus_cli.py --swarm-mode --port 8002 --swarm-token $TOKEN > /tmp/nexus_node_8002.log 2>&1 &
# 啟動 Node 3 (No Token - Secure Mode Default)
python3 scripts/nexus_cli.py --swarm-mode --port 8003 > /tmp/nexus_node_8003.log 2>&1 &

sleep 3

echo "🕵️ [Security:Test] Testing Unauthorized Access (No Token to Node 8001)..."
curl -s -X POST http://localhost:8001/sensing -d '{"task_key": "hack"}' | grep "Unauthorized" && echo "  - ✅ Blocked as expected."

echo "🚀 [Sharding:Test] Running Go Swarm Manager with Task Sharding..."
export NEXUS_SWARM_TOKEN=$TOKEN
cd nexus-swarm
go run cmd/swarm-manager/main.go

echo "🧹 [Cleanup] Shutting down nodes..."
pkill -f "nexus_cli.py --swarm-mode"

echo "✅ [Complete] v18.2 Pragmatic Hardening verification finished."
