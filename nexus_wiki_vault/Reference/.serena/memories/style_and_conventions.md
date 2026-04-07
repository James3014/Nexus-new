---
id: style_and_conventions
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
path: nexus_wiki_vault/06_Ops/Reference/.serena/memories/style_and_conventions.md
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
# Code Style and Conventions

- **Programming Language**: Python
- **Format**: PEP8 compliant.
- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes.
- **Type Hints**: Mandatory for core library functions.
- **Bilingual Docs**: All [[documentation]] must be provided in both English and Traditional Chinese.
- **Contract Driven**: Use Pydantic models for data [[Validation|validation]] (see `scripts/core/state_contracts.py`).


---
[[System Overview]]