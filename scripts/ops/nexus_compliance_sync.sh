#!/bin/bash
export PATH=$PATH:/Users/jameschen/.local/bin
# 🛡️ Nexus Compliance Master Sync (v22.5)
# This script runs the full compliance pipeline: Collect -> Transform -> Wiki.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "--- [$(date)] Nexus Compliance Sync Started ---"

# 1. Collect raw evidence
echo "📦 Step 1: Collecting raw evidence..."
uv run scripts/ops/collect_compliance_data.py

# 2. Transform to Wiki
echo "📝 Step 2: Transforming to Wiki format..."
uv run scripts/ops/compliance_to_wiki.py

# 3. Update Audit Trail
echo "📜 Step 3: Archiving audit trail to /compliance/audit/..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp ".nexus/reports/enterprise_audit.json" "compliance/audit/evidence_$TIMESTAMP.json" 2>/dev/null

echo "✅ [$(date)] Compliance Sync Complete."
echo "--- Dashboard: nexus_wiki_vault/07_Compliance/Compliance_Dashboard.md ---"
