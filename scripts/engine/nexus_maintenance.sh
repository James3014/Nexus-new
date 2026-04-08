#!/bin/bash
# scripts/engine/nexus_maintenance.sh

echo "🛡️ $(date): Running Nexus production maintenance..."

# 設定工作目錄
cd ./

# 1. Memory Hygiene: TTL cleanup (保留 90 天)
echo "🧹 Phase 1: Memory Hygiene (TTL 90 Days)..."
uv run python scripts/learning/cleanup_policy_memory.py . --ttl-days 90

# 2. Intelligence Evolution: Route Autotune (學習 7 天歷史)
echo "🧠 Phase 2: Route Weight Autotune (7 Day Window)..."
uv run python scripts/learning/autotune_route_weights.py . --window-days 7

# 3. Production Monitoring: Daily Audit
echo "📊 Phase 3: Daily Production Audit..."
uv run python scripts/learning/audit_production_chain.py . --days 1 > .nexus/knowledge/daily_audit_$(date +%F).json

echo "✅ $(date): Maintenance complete."
