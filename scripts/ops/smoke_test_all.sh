#!/bin/bash
# 🛡️ Nexus Cross-Generation Smoke Test
set -e
echo "🚀 [Smoke] Verifying v0.8 Meta-Learning..."
uv run scripts/engine/nexus_cli.py meta-run --count 10 > /dev/null
echo "✅ v0.8 Alive."

echo "🚀 [Smoke] Verifying v0.9 Federated Intelligence..."
uv run scripts/engine/nexus_cli.py fed-run > /dev/null
echo "✅ v0.9 Alive."

echo "🚀 [Smoke] Verifying v23.7 Fleet Command..."
uv run scripts/engine/nexus_cli.py nexus delegate "Smoke Task" > /dev/null
echo "✅ v23.7 Alive."

echo "🏆 [Smoke] All generations are functional."
