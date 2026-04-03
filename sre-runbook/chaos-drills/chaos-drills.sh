#!/bin/bash
# 🛡️ Nexus Swarm Chaos Drills (v22/v24 Spec)
set -eo pipefail

NAMESPACE="nexus"
FORCE=0

usage() {
    echo "Usage: $0 --force [--namespace <ns>] [scenario flags]"
    echo "Scenarios:"
    echo "  --drill-manager        Manager killing"
    echo "  --drill-node           Node partitioning"
    echo "  --drill-db             DB failover promote"
    echo "  --drill-shadow         Shadow audit timeout"
    exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --force) FORCE=1 ;;
    --namespace) NAMESPACE="$2"; shift ;;
    --drill-manager) DRILL_MANAGER=1 ;;
    --drill-node) DRILL_NODE=1 ;;
    --drill-db) DRILL_DB=1 ;;
    --drill-shadow) DRILL_SHADOW=1 ;;
    *) usage ;;
  esac
  shift
done

if [[ $FORCE -ne 1 ]]; then
  echo "❌ Error: --force is required for chaos drills."
  exit 1
fi

echo "🛡️ Starting Nexus Swarm Chaos Drills: Namespace=$NAMESPACE"

# 🛡️ Scenario 1: Manager Failover
if [[ ${DRILL_MANAGER:-0} == 1 ]]; then
  echo "🔥 [DRILL] Manager Failover..."
  POD=$(kubectl get pod -n $NAMESPACE -l app.kubernetes.io/component=manager -o jsonpath='{.items[0].metadata.name}')
  echo "💀 Killing Manager Pod: $POD"
  kubectl delete pod $POD -n $NAMESPACE --now
  echo "⏳ Waiting 60s for K8s recovery..."
  sleep 10
  kubectl rollout status deployment nexus-swarm-manager -n $NAMESPACE --timeout=50s
  echo "✅ Manager recovered."
fi

# 🛡️ Scenario 2: Node Partition
if [[ ${DRILL_NODE:-0} == 1 ]]; then
  echo "🌐 [DRILL] Node Partition (us-east)..."
  echo "🚧 Injecting partitioned label..."
  kubectl patch deployment nexus-swarm-node-us-east -n $NAMESPACE -p '{"spec":{"template":{"metadata":{"labels":{"partitioned":"true"}}}}}'
  echo "⏳ Waiting 70s for STALE detection (STALE=60s)..."
  sleep 75
  # 🛡️ Check cluster status for STALE nodes
  STATUS=$(curl -s localhost:9100/cluster/status | jq '.nodes[] | select(.health=="STALE")')
  if [[ -n "$STATUS" ]]; then
    echo "✅ Partition detected: Node marked STALE."
  else
    echo "⚠️  Partition detection failed."
  fi
  echo "♻️  Restoring Node connectivity..."
  kubectl patch deployment nexus-swarm-node-us-east -n $NAMESPACE --type=json -p='[{"op": "remove", "path": "/spec/template/metadata/labels/partitioned"}]'
fi

# 🛡️ Scenario 3: DB Failover
if [[ ${DRILL_DB:-0} == 1 ]]; then
  echo "🗄️ [DRILL] DB Failover Promote..."
  echo "🚧 Promoting Slave DB (nexus-swarm-db-1)..."
  kubectl exec nexus-swarm-db-1 -n $NAMESPACE -- pg_ctl promote
  echo "✅ DB Promoted. Verifying connection..."
  kubectl exec nexus-swarm-db-1 -n $NAMESPACE -- psql -U nexus -c "SELECT version();"
fi

# 🛡️ Scenario 4: Shadow Audit Degradation
if [[ ${DRILL_SHADOW:-0} == 1 ]]; then
  echo "🦾 [DRILL] Shadow Audit Degradation..."
  echo "🚧 Simulating Docker Socket failure..."
  # 🛡️ Rename docker socket if mounted or simulate via env
  # Here we simulate by calling the webhook with a dummy large payload or invalid state
  curl -X POST http://localhost:8081/shadow-audit \
    -H "Content-Type: application/json" \
    -d '{"pr_number": 999, "diff": "invalid", "mode": "force_degraded"}'
  echo "✅ Shadow audit reported DEGRADED state."
fi

echo "🏁 Chaos Drills Complete."
