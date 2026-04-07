---
id: program
type: doc
status: active
created: 2026-04-07T07:29:29Z
updated: 2026-04-07T07:29:29Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: /program.md
---
Waiver: 00_Home/[System Overview](../00_Home/System Overview.md).md
[source: 00_Home/[System Overview](../00_Home/System Overview.md).md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
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


---
[System Overview](../00_Home/System Overview.md)