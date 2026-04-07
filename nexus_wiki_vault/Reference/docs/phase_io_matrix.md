---
id: phase_io_matrix
type: doc
status: active
created: 2026-04-07T07:29:31Z
updated: 2026-04-07T07:29:31Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/phase_io_matrix.md
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
# Nexus Phase I/O Matrix

## P — Planning
| | Code [[task]] | Conversation [[task]] |
|---|---|---|
| **Input** | Bug report, error log, [[task]] description | User question, user goal, prior context |
| **Output** | `plan.json`, scope, `task_type` | `conversation_id`, `user_goal`, initial constraints |

## D — Diagnosis
| | Code [[task]] | Conversation [[task]] |
|---|---|---|
| **Input** | `plan.json`, codebase, memory | `user_goal`, `confirmed_constraints`, `unresolved_points` |
| **Output** | `NexusDiagnosis`, root cause | Clarification result, updated `key_context_facts` |

## X — Research
| | Code [[task]] | Conversation [[task]] |
|---|---|---|
| **Input** | Diagnosis, external search query | `needs_research=True`, research prompt |
| **Output** | `NexusResearch`, findings | Research findings injected to conversation pack |

## R — Repair (Answer Generation)
| | Code [[task]] | Conversation [[task]] |
|---|---|---|
| **Input** | Diagnosis + research context, repair pack | Conversation pack, `user_goal`, constraints |
| **Output** | Patched code diff | `answer_draft`, `answer_draft_status` |

## A — Audit (Review)
| | Code [[task]] | Conversation [[task]] |
|---|---|---|
| **Input** | Staged code changes, git diff, linter output | Conversation pack (compressed), candidate answer |
| **Output** | `APPROVED / REJECTED`, violations | `APPROVED / REJECTED / SKIPPED_QUOTA`, `audit_flags`, `return_target_phase`, `audit_metadata.audit_profile = "conversation"` |
| **Routing on REJECT** | Fixed → D | Dynamic → D / X / R based on `return_target_phase` |

## C — Crystal (Learning)
| | Code [[task]] | Conversation [[task]] |
|---|---|---|
| **Input** | Approved fix, full loop trace | Approved answer, conversation metadata |
| **Output** | Crystal lessons persisted to memory | High-value user preferences, confirmed facts |


---
[[System Overview]]