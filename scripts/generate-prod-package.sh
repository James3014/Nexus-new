#!/bin/bash
# 🛡️ Nexus Swarm v22 Production Package Generator
# [NEXUS v22 PRODUCTION CERTIFIED]

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$REPO_ROOT/nexus-swarm-v22-prod"
CA_KEY="$REPO_ROOT/nexus-swarm/certs/ca.key"

echo "🛡️ Generating Nexus Swarm v22 Production Package..."

# 1. Prepare Directory
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"/{helm,sre-runbook,stress-test,scripts,certs}

# 2. Collect Production Assets
echo "📦 Collecting assets..."
cp -r "$REPO_ROOT/nexus-swarm/manager" "$PACKAGE_DIR/"
cp -r "$REPO_ROOT/nexus-swarm/node" "$PACKAGE_DIR/"
cp -r "$REPO_ROOT/nexus-swarm/helm" "$PACKAGE_DIR/"
cp -r "$REPO_ROOT/nexus-swarm/scripts" "$PACKAGE_DIR/"
cp -r "$REPO_ROOT/nexus-swarm/stress-test" "$PACKAGE_DIR/"
cp -r "$REPO_ROOT/nexus-swarm/certs" "$PACKAGE_DIR/" # Public certs for trust

# 3. Create manifest and signing
echo "🖋️ Signing release..."
tar -czf "$REPO_ROOT/nexus-swarm-v22-prod.tar.gz" -C "$REPO_ROOT" nexus-swarm-v22-prod
openssl dgst -sha256 -sign "$CA_KEY" "$REPO_ROOT/nexus-swarm-v22-prod.tar.gz" > "$REPO_ROOT/v22-prod.sig"

# 4. Generate Metadata
echo "📄 Generating metadata..."
sha256sum "$REPO_ROOT/nexus-swarm-v22-prod.tar.gz" > "$REPO_ROOT/v22-prod.sha256"

echo "✅ Production Package Ready:"
echo "   Archive: nexus-swarm-v22-prod.tar.gz"
echo "   Signature: v22-prod.sig"
echo "   Checksum: v22-prod.sha256"
ls -lh "$REPO_ROOT/nexus-swarm-v22-prod.tar.gz" "$REPO_ROOT/v22-prod.sig"
