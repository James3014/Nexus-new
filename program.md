# Nexus-AutoResearch Rules v7.2
- Target: repairfinal.py (optimizer/train loop)
- Metric: val_flashjudge > prev_score - 0.1
- Budget: 300s/round, max 3 LLM calls
- Rollback: No improve → git reset --hard
- Forbidden: codebase-wide changes, infinite loops

# React Hydration Rules
- Target: components/HydrationGuard.tsx
- Issue: Text content did not match server-rendered HTML
- Strategy: Use useEffect for client-only mounting, or suppressHydrationWarning
- Metric: FlashJudge Score > 9.0
# Redis Migration Rules
- Target: scripts/migrate_redis.py
- Issue: Inconsistent data during cluster migration
- Strategy: Use multi-phase sync (SCAN -> DUMP -> RESTORE) with lock-free semantics
- Metric: Data integrity check > 99.9%
