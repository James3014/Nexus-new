#!/bin/zsh
# Nexus v17.0 Status Dashboard
# 🚀 提供 100% 透明的浸泡測試 (Soak Test) 實時觀測

NEXUS_ROOT="/Users/jameschen/Workspace/nexus"
STATE_FILE="$NEXUS_ROOT/.nexus/runner_supervisor_state.json"
ACCEPTANCE_FILE="$NEXUS_ROOT/.nexus/reports/acceptance_check.md"
REPORTS_DIR="$NEXUS_ROOT/docs"

clear
echo "===================================================="
echo "🛡️  Nexus Singularity OS v17.0 - Hardened Dashboard"
echo "===================================================="
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo "----------------------------------------------------"

# 1. 基礎建設狀態
echo " [Infrastructure]"
lsof -i :6379 >/dev/null 2>&1 && echo "  - Redis (6379): ✅ ONLINE" || echo "  - Redis (6379): ❌ OFFLINE"
pgrep -x mds >/dev/null && echo "  - Spotlight Indexer: ⚠️ RUNNING (Suppressed for Nexus)" || echo "  - Spotlight Indexer: ✅ STOPPED"
echo "----------------------------------------------------"

# 2. 治理統計 (Acceptance Gate)
echo " [Acceptance Gate]"
if [[ -f "$ACCEPTANCE_FILE" ]]; then
    STATUS=$(grep "status:" "$ACCEPTANCE_FILE" | awk '{print $NF}')
    RATE=$(grep "recent_regression_pass_rate_avg:" "$ACCEPTANCE_FILE" | awk '{print $NF}')
    [[ "$STATUS" == "PASS" ]] && COLOR="\033[32m" || COLOR="\033[31m"
    echo -e "  - Overall Status: ${COLOR}${STATUS}\033[0m"
    echo "  - Regression Pass Rate: ${RATE}% (Target: 95.0%)"
else
    echo "  - Acceptance Report: ❌ MISSING"
fi
echo "----------------------------------------------------"

# 3. 運行中任務 (Supervisor)
echo " [Supervisor State]"
if [[ -f "$STATE_FILE" ]]; then
    python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); print(f'  - Status: {d.get(\"status\")}\n  - Last Updated: {d.get(\"updated_at\")}\n  - Round Log: {d.get(\"latest_round_log\")}')" 2>/dev/null
else
    echo "  - Supervisor State: ❌ IDLE"
fi
echo "----------------------------------------------------"

# 4. 學習閉環 (Learning Loop v23.5)
echo " [Learning Loop (L-Gate)]"
METRICS_FILE="$NEXUS_ROOT/.nexus/metrics/learning_metrics.jsonl"
if [[ -f "$METRICS_FILE" ]]; then
    # Calculate stats from the last 100 entries
    python3 -c "
import json, sys
lines = open('$METRICS_FILE').readlines()[-100:]
data = [json.loads(l) for l in lines]
total = len(data)
ingest_ok = sum(1 for d in data if d.get('status') in ['NEW', 'MERGED', 'NEW_INITIAL'])
dedup_hits = sum(1 for d in data if d.get('status') in ['DISCARDED', 'MERGED'])
hit_rate = sum(d.get('retrieval_hit', 0) for d in data) / total if total > 0 else 0

# 🚀 Phase 32 Dual-Mode Metrics
palace_hits = sum(1 for d in data if d.get('mode_used') == 'palace')
arweave_sync = sum(1 for d in data if d.get('arweave_tx') is not None)

print(f'  - Ingest Success: {ingest_ok}/{total}')
print(f'  - Dedup Ratio: {int(dedup_hits/total*100 if total>0 else 0)}%')
print(f'  - Retrieval Hit: {int(hit_rate*100)}% (Target: 85%)')
print(f'  - Dual-Mode L1 (Palace): {int(palace_hits/total*100 if total>0 else 0)}%')
print(f'  - Arweave Sync: {int(arweave_sync/total*100 if total>0 else 0)}%')
" 2>/dev/null
else
    echo "  - Learning Metrics: ❌ NO DATA (Waiting for Hook)"
fi
echo "----------------------------------------------------"

# 5. 最近報告 (Latest Reports)
echo " [Latest Reports]"
ls -t "$REPORTS_DIR"/EXEC_REPORT_*.md 2>/dev/null | head -n 3 | xargs -I {} basename {} | sed 's/^/  - /'
echo "===================================================="
echo " (Tip: Use 'watch -n 5 ./STATUS_DASHBOARD.sh' for live view)"
