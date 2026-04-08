#!/bin/bash
# Nexus Swarm Shadow Audit (v24 SRE Hardening)
# Purpose: Verify Observability, Security, and Degradation logic in a real-world scenario.

echo "🚀 Starting Nexus Swarm Phase 24 Shadow Audit..."

# 1. Start a Small Fleet (5 Nodes)
export NEXUS_ALLOWED_PATHS="./scripts,/tmp/nexus"
echo "🛡️  Enforcing Security Boundaries: $NEXUS_ALLOWED_PATHS"

# Setup ports 9201-9205
for i in {1..5}; do
    port=$((9200 + i))
    python3 scripts/engine/nexus_cli.py nexus:swarm --port $port --region us-east-1 &
    sleep 0.5
done

# Generate temporary nodes.json
cat <<EOF > nodes_shadow.json
[
  {"url": "http://localhost:9201", "region": "us-east-1"},
  {"url": "http://localhost:9202", "region": "us-east-1"},
  {"url": "http://localhost:9203", "region": "us-east-1"},
  {"url": "http://localhost:9204", "region": "us-east-1"},
  {"url": "http://localhost:9205", "region": "us-east-1"}
]
EOF

# 2. Start Manager with Fail-Open Bypass (Simulation)
export NEXUS_METRICS_PORT=9100
export NEXUS_GATE_BYPASS=true
echo "⚠️  Fail-Open (Bypass) mode activated for shadows."

(cd nexus-swarm && ./swarm-manager -nodes ../nodes_shadow.json) &
MANAGER_PID=$!
sleep 2

# 3. Verify Prometheus Metrics are reachable
echo "📊 Checking Metrics Endpoint..."
curl -s http://localhost:9100/metrics | grep nexus_tasks_processed_total
if [ $? -eq 0 ]; then
    echo "✅ Prometheus Metrics live at :9100"
else
    echo "❌ Prometheus Metrics unreachable!"
fi

# 4. Trigger a Security Violation (Intentional)
echo "🔒 Testing Security Boundary..."
# Task that tries to access /etc/passwd (blocked)
curl -X POST -H "Content-Type: application/json" \
     -d '{"id": "sec-violation", "path": "/etc/passwd", "status": "PENDING"}' \
     http://localhost:9201/sensing

echo -e "\n🛑 Security test triggered. Check Manager/Node logs for 'SECURITY_VIO'."

# 5. Cleanup
echo "🧹 Cleaning up shadow fleet..."
kill $MANAGER_PID
pkill -f "nexus_cli.py nexus:swarm"
rm nodes_shadow.json

echo "🏁 Shadow Audit complete."
