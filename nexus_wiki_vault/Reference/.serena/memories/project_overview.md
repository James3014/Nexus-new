---
id: project_overview
type: doc
status: active
created: 2026-04-07T07:29:30Z
updated: 2026-04-07T07:29:30Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/.serena/nexus_wiki_vault/Reference/.serena/memories/project_overview.md
---
Waiver: 00_Home/[System Overview](../../../00_Home/System Overview.md).md
[source: 00_Home/[System Overview](../../../00_Home/System Overview.md).md]
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
# Nexus v7: Night Shift Code Factory

## Purpose
The project aims to transition from single-[task](../../task.md) AI coding to an automated "Night Shift" factory capable of producing 10+ PRs per night with a 95%+ success rate.

## Tech Stack
- **Language**: Python 3.9+
- **Database**: [LanceDB](../../../02_Modules/Module - Memory Repository.md) (v2)
- **AI Models**: Multi-model (Claude for planning, Gemini for review)
- **Framework**: P-D-X-R-A-C (Plan, Diagnose, eXternal research, Repair, Audit, Crystallize)
- **Metadata**: JSON/JSONL (.musestate, plan.json)

## Key Commands
- `python3 scripts/nexus_cli.py nexus:bug --[task](../../task.md) "..."`: General bug fixing [task](../../task.md).
- `python3 scripts/nexus_cli.py nexus:feature --[task](../../task.md) "..."`: Feature implementation.
- `codex-loop`: Core cognitive loop auditor.
- `uv run`: Preferred way to execute scripts with dependencies.

## Structure
- `scripts/core/`: Core orchestrator and contract definitions.
- `scripts/legacy/`: Deprecated duplicated scripts.
- `.muse_state`: Global [task](../../task.md) state persistence.


---
[System Overview](../../../00_Home/System Overview.md)