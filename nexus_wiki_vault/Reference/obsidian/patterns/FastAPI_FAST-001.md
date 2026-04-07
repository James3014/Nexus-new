---
id: fastapi_fast-001
type: doc
status: active
created: 2026-04-07T07:29:41Z
updated: 2026-04-07T07:29:41Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/obsidian/patterns/FastAPI_FAST-001.md
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
# [FastAPI] Dependency Override Failure
- **ID**: FAST-001
- **Context**: [[testing]] FastAPI endpoints with dependency overrides.

## 🛑 Problem (The Bug)
App is instantiated before overrides are applied in tests.

## ✅ Solution (The Fix)
Use app.dependency_overrides[dependency] = mock_dep inside test function or fixture.

---
#NexusKnowledge #v7 Mastered


---
[[System Overview]]