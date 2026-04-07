---
id: skill
type: doc
status: active
created: 2026-04-07T07:29:39Z
updated: 2026-04-07T07:29:39Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/skills/logmemory/SKILL.md
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
PHASES: P,D,R
TRIGGERS: memory, recall, lessons, reminder, hydration, deps, strike
DESCRIPTION: 統一四源 (.codex_lessons, crystal.jsonl, tracelog, patterns) 到 [[Module - Memory Repository|LanceDB]]，per-round RAG top-3 reminders。
OUTPUT SCHEMA: reminders.json {"reminders": [{"source": str, "content": any, "relevance": float}], "total_sources": int}
NEGATIVE: 無 relevance <0.7，限 3 項防噪音。
HOOK: [[Module - Intelligence and Context Core|Context Hub]] pre-phase 注入。


---
[[System Overview]]