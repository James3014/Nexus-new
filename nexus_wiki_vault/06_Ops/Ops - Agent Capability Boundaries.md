---
ci_hash: pend-audit
created: 2026-04-07 07:16:04+00:00
governance: Trident 3.0
id: ops
landscape: structural
owner: nexus-core
path: nexus_wiki_vault/06_Ops/Ops - Agent Capability Boundaries.md
priority: P2
soul_alignment: harmonized
status: active
tags:
- nexus
- governance
type: doc
updated: 2026-04-07 07:16:04+00:00
version: v1.0.0
visibility: internal
---


Waiver: 00_Home/[System Overview](../00_Home/System Overview.md).md
[source: nexus_wiki_vault/00_Home/System Overview.md]].md]

agent-capability-boundaries
type: doc
status: active
created: 2026-04-07T07:13:41Z
updated: 2026-04-07T07:13:41Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: /Users/jameschen/Workspace/nexus/nexus_wiki_vault/06_Ops/Ops - Agent Capability Boundaries.md
---

## One-sentence summary
- TODO

## Role / responsibility
- TODO

## Upstream
- TODO

## Downstream
- TODO

## Related modules / files
- TODO

## Source notes
- TODO

## Open questions / conflicts
- TODO

---
# Ops - Agent Capability Boundaries

## 🛡️ Strategic Boundary Rules

| Rule | Definition | Enforced By |
| --- | --- | --- |
| **allowed_paths** | Project root, `scripts/ops/`, `nexus_wiki_vault/`, `docs/` | `agent_protocol_check.py` |
| **forbidden_paths** | `.obsidian/`, `benchmarks/`, `logs/`, `nexus_swarm/`, `packages/` | `ci_gate.py` |
| **max_files_touched** | 10 | `Nexus [CI Gate](Ops - CI/CD Promotion Gate.md)` |

## 🚀 Protocol Requirements

- **Semantic Completion**: "Passed" tests do not mean the [task](../Reference/task.md) is finished. The agent must confirm all intended behaviors are achieved.
- **Evidence-Driven Reporting**: No claims of completion without providing specific command outputs.
- **Fail-to-Lesson Writeback**: Every failure must be converted into a lesson and recorded in the `Learning Closure Matrix`.


---
[System Overview](../00_Home/System Overview.md)