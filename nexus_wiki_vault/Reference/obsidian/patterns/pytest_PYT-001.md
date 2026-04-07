---
id: pytest_pyt-001
type: doc
status: active
created: 2026-04-07T07:29:40Z
updated: 2026-04-07T07:29:40Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/obsidian/patterns/pytest_PYT-001.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
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
# [pytest] [[async]] Fixture Scope Mismatch
- **ID**: PYT-001
- **Context**: Using [[async]] fixtures with different scopes.

## 🛑 Problem (The Bug)
Scope mismatch when [[async]] fixture depends on a module-scoped fixture.

## ✅ Solution (The Fix)
Ensure all dependent [[async]] fixtures share compatible scopes or use pytest-asyncio strict mode.

---
#NexusKnowledge #v7 Mastered


---
[[System Overview]]