#!/bin/bash
# 🛡️ Nexus Physical Preflight - Protocol v2.1 Hardened

# 1. Path Injection (Mandatory for Mac uv environments)
export PATH="$HOME/.local/bin:$PATH"

echo "🛡️ Nexus CLI surface check..."
uv run scripts/engine/nexus_cli.py --help > /dev/null 2>&1 && echo "✅ Nexus CLI surface check: PASS" || { echo "❌ Nexus CLI surface check: FAIL"; exit 1; }

echo "🛡️ CI gate dry-run..."
uv run scripts/ops/ci_gate.py --dry-run > /dev/null 2>&1 && echo "✅ CI gate dry-run: PASS" || { echo "❌ CI gate dry-run: FAIL"; exit 1; }

# 2. Metadata Collection
COMMIT_SHA=$(git rev-parse --short HEAD)
SWARM_COUNT=$(ls -d .nexus-swarm-* 2>/dev/null | wc -l | xargs)

echo "[NEXUS v22 ACTIVE] Preflight complete."
echo "  Commit SHA: $COMMIT_SHA"
echo "  CI Dry-run: PASS"
echo "  50 Swarm Status: $SWARM_COUNT directories found"
