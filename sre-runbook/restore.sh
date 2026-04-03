#!/bin/bash
set -euo pipefail

BACKUP_ARCHIVE=$1
NAMESPACE=${2:-nexus}

if [ -z "$BACKUP_ARCHIVE" ]; then
    echo "❌ Usage: ./restore.sh <backup-archive.tar.gz> [namespace]"
    exit 1
fi

echo "🛡️ Nexus Swarm Restore: $BACKUP_ARCHIVE (Namespace: $NAMESPACE)"

# 1. 解壓縮備份
TEMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_ARCHIVE" -C "$TEMP_DIR"
BACKUP_PATH=$(ls -d "$TEMP_DIR"/swarm-*)

# 2. 暫停 Swarm 服務以確保數據一致性
echo "🛡️ Scaling down Swarm services..."
kubectl scale deployment -n "$NAMESPACE" -l app.kubernetes.io/instance=nexus-swarm --replicas=0

# 3. 恢復 Secrets
echo "🛡️ Restoring Secrets..."
kubectl apply -f "$BACKUP_PATH/secrets.yaml" -n "$NAMESPACE"

# 4. 恢復 PostgreSQL 數據
echo "🛡️ Restoring PostgreSQL..."
PG_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}')
cat "$BACKUP_PATH/db_dump.sql" | kubectl exec -i "$PG_POD" -n "$NAMESPACE" -- psql -U nexus

# 5. 恢復服務 (Scale up via Helm)
echo "🛡️ Scaling up Swarm services..."
helm upgrade nexus-swarm nexus-swarm/helm/ -n "$NAMESPACE" --wait

# 6. 清理
rm -rf "$TEMP_DIR"
echo "✅ Restore complete."
