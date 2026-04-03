#!/bin/bash
set -euo pipefail

NAMESPACE=${1:-nexus}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=$(pwd)/backup
BACKUP_DIR=$BACKUP_ROOT/swarm-$TIMESTAMP

echo "🛡️ Nexus Swarm Backup: $TIMESTAMP (Namespace: $NAMESPACE)"

# 1. 建立備份目錄
mkdir -p "$BACKUP_DIR"

# 2. 備份 PostgreSQL 數據
echo "🛡️ Backing up PostgreSQL..."
PG_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$PG_POD" -n "$NAMESPACE" -- pg_dumpall -U nexus > "$BACKUP_DIR/db_dump.sql"

# 3. 備份 Kubernetes Secrets (TLS & Auth)
echo "🛡️ Backing up Secrets..."
kubectl get secret -n "$NAMESPACE" -l app.kubernetes.io/instance=nexus-swarm -o yaml > "$BACKUP_DIR/secrets.yaml"

# 4. 備份 Helm Values 與 版本
echo "🛡️ Backing up Helm Context..."
helm get values nexus-swarm -n "$NAMESPACE" > "$BACKUP_DIR/values.yaml"
helm list -n "$NAMESPACE" > "$BACKUP_DIR/helm_list.txt"

# 5. 打包備份
cd "$BACKUP_ROOT"
tar -czf "swarm-$TIMESTAMP.tar.gz" "swarm-$TIMESTAMP"
rm -rf "swarm-$TIMESTAMP"

echo "✅ Backup complete: $BACKUP_ROOT/swarm-$TIMESTAMP.tar.gz"
