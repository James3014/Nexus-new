#!/bin/bash
echo "🛡️ Nexus CLI surface check..."
uv run scripts/engine/nexus_cli.py --help > /dev/null 2>&1 && echo "✅ Nexus CLI surface check: PASS" || { echo "❌ Nexus CLI surface check: FAIL"; exit 1; }

echo "🛡️ CI gate dry-run..."
uv run scripts/ops/ci_gate.py --dry-run > /dev/null 2>&1 && echo "✅ CI gate dry-run: PASS" || { echo "❌ CI gate dry-run: FAIL"; exit 1; }

echo "[NEXUS v22 ACTIVE] Preflight complete. SHA: $(git rev-parse --short HEAD)"
