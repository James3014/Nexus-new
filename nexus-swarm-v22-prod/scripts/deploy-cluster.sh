#!/bin/bash
# 🛡️ Nexus Swarm Multi-cluster Deployer (v22/v24)
# Usage: ./deploy-cluster.sh <CLUSTER_NAME> <REGION>

set -e

CLUSTER_NAME=$1
REGION=$2

if [ -z "$CLUSTER_NAME" ] || [ -z "$REGION" ]; then
    echo "❌ Usage: ./deploy-cluster.sh <CLUSTER_NAME> <REGION>"
    exit 1
fi

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🛡️ Deploying Nexus Swarm to $CLUSTER_NAME in $REGION...${NC}"

# 1. Update Kubeconfig
echo "🔗 Updating kubeconfig for $CLUSTER_NAME..."
aws eks update-kubeconfig --name $CLUSTER_NAME --region $REGION

# 2. Create Namespace
echo "📦 Creating nexus namespace..."
kubectl create namespace nexus --dry-run=client -o yaml | kubectl apply -f -

# 3. Provision Federation Secret
# In production, this should be pulled from Vault or Secreats Manager
echo "🔐 Deploying Federation Secret..."
kubectl create secret generic federation-token \
  --from-literal=token="prod-fed-token-20260404" \
  -n nexus --dry-run=client -o yaml | kubectl apply -f -

# 4. Helm Deployment (Production Rollout)
echo "🚀 Executing Helm Upgrade/Install..."
helm upgrade --install nexus-swarm ../helm/ \
  --namespace nexus \
  --values ../helm/values-prod.yaml \
  --set global.federation.clusterId=$CLUSTER_NAME \
  --set global.federation.region=$REGION \
  --set global.federation.token="prod-fed-token-20260404" \
  --wait --timeout 15m

# 5. Verify Rollout
echo "✅ Checking Pod Status..."
kubectl get pods -n nexus

echo -e "${GREEN}🛡️ $CLUSTER_NAME Rollout Complete.${NC}"
