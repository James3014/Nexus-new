# Nexus Phase I/O Matrix

## P — Planning
| | Code Task | Conversation Task |
|---|---|---|
| **Input** | Bug report, error log, task description | User question, user goal, prior context |
| **Output** | `plan.json`, scope, `task_type` | `conversation_id`, `user_goal`, initial constraints |

## D — Diagnosis
| | Code Task | Conversation Task |
|---|---|---|
| **Input** | `plan.json`, codebase, memory | `user_goal`, `confirmed_constraints`, `unresolved_points` |
| **Output** | `NexusDiagnosis`, root cause | Clarification result, updated `key_context_facts` |

## X — Research
| | Code Task | Conversation Task |
|---|---|---|
| **Input** | Diagnosis, external search query | `needs_research=True`, research prompt |
| **Output** | `NexusResearch`, findings | Research findings injected to conversation pack |

## R — Repair (Answer Generation)
| | Code Task | Conversation Task |
|---|---|---|
| **Input** | Diagnosis + research context, repair pack | Conversation pack, `user_goal`, constraints |
| **Output** | Patched code diff | `answer_draft`, `answer_draft_status` |

## A — Audit (Review)
| | Code Task | Conversation Task |
|---|---|---|
| **Input** | Staged code changes, git diff, linter output | Conversation pack (compressed), candidate answer |
| **Output** | `APPROVED / REJECTED`, violations | `APPROVED / REJECTED / SKIPPED_QUOTA`, `audit_flags`, `return_target_phase`, `audit_metadata.audit_profile = "conversation"` |
| **Routing on REJECT** | Fixed → D | Dynamic → D / X / R based on `return_target_phase` |

## C — Crystal (Learning)
| | Code Task | Conversation Task |
|---|---|---|
| **Input** | Approved fix, full loop trace | Approved answer, conversation metadata |
| **Output** | Crystal lessons persisted to memory | High-value user preferences, confirmed facts |
