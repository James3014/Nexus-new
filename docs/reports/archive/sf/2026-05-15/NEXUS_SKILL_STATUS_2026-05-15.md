# Nexus Skill Status - 2026-05-15

Source inventory: `docs/reports/NEXUS_SKILL_INVENTORY_2026-05-15.json`

## Summary

- Total skills: 1759
- Runtime candidates: 19
- Reference candidates: 807
- Quarantined/read-only: 771
- Review needed: 162

## Status Counts

| Status | Count | Meaning |
|---|---:|---|
| `external_reference_candidate` | 759 | Useful reference skill; do not mount until imported/curated. |
| `candidate_quarantine` | 574 | Generated/candidate inbox; never auto-load. |
| `agents_pool_review_needed` | 162 | Mixed .agents pool item; manual triage before any use. |
| `worktree_copy_quarantine` | 136 | Non-canonical worktree copy; never auto-load. |
| `runtime_vendor_readonly` | 49 | Runtime/plugin/vendor capability; do not claim as Nexus policy. |
| `provider_mirror_reference` | 48 | Provider-specific mirror; read only for compatibility/design. |
| `nexus_curated_candidate` | 19 | Repo-local Nexus skill; eligible for capability mount review and e2e validation. |
| `archive_quarantine` | 12 | Historical backup; never auto-load. |

## Test Levels

| Test Level | Count |
|---|---:|
| `routing_reference` | 807 |
| `quarantine` | 771 |
| `inventory_plus_trigger_lint` | 162 |
| `routing_plus_e2e` | 19 |

## Capability Mount Hints

| Capability Hint | Count |
|---|---:|
| `none` | 1075 |
| `reference:repair_and_coding` | 315 |
| `reference:governance_and_trust` | 124 |
| `reference:benchmark_and_promotion` | 96 |
| `reference:research_and_source_discipline` | 83 |
| `reference:planning_and_handoff` | 46 |
| `repair_and_coding` | 5 |
| `governance_and_trust` | 4 |
| `benchmark_and_promotion` | 3 |
| `planning_and_handoff` | 3 |
| `reference:notebook_and_knowledge_injection` | 3 |
| `notebook_and_knowledge_injection` | 2 |

## Runtime Candidates

| Skill | Capability Hint | Test Level | Reason | Path |
|---|---|---|---|---|
| `diagnose` | `governance_and_trust` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/diagnose/SKILL.md` |
| `grill-me` | `repair_and_coding` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/grill-me/SKILL.md` |
| `grill-with-docs` | `repair_and_coding` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/grill-with-docs/SKILL.md` |
| `improve-codebase-architecture` | `repair_and_coding` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/improve-codebase-architecture/SKILL.md` |
| `nexus-benchmark-continuous-optimization` | `benchmark_and_promotion` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/nexus-benchmark-continuous-optimization/SKILL.md` |
| `nexus-benchmark-public-report` | `benchmark_and_promotion` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/nexus-benchmark-public-report/SKILL.md` |
| `nexus-capability-upgrade` | `benchmark_and_promotion` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/nexus-capability-upgrade/SKILL.md` |
| `nexus-goal-closure-executor` | `governance_and_trust` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/nexus-goal-closure-executor/SKILL.md` |
| `nexus-root-cause-probe` | `governance_and_trust` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/nexus-root-cause-probe/SKILL.md` |
| `nexus-yang-ding-yi-eternal-v5` | `needs_mount_decision` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/yang-ding-yi-nexus-eternal/SKILL.md` |
| `notebooklm-bulk-injector` | `notebook_and_knowledge_injection` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/notebooklm-bulk-injector/SKILL.md` |
| `notebooklm-context-bridge` | `notebook_and_knowledge_injection` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/notebooklm-context-bridge/SKILL.md` |
| `setup-matt-pocock-skills` | `governance_and_trust` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/setup-matt-pocock-skills/SKILL.md` |
| `tdd` | `repair_and_coding` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/tdd/SKILL.md` |
| `to-issues` | `planning_and_handoff` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/to-issues/SKILL.md` |
| `to-prd` | `planning_and_handoff` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/to-prd/SKILL.md` |
| `triage` | `planning_and_handoff` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/triage/SKILL.md` |
| `yang-ding-yi-perspective` | `needs_mount_decision` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/yang-ding-yi-perspective/SKILL.md` |
| `zoom-out` | `repair_and_coding` | `routing_plus_e2e` | `repo_local_nexus_skill` | `/Users/jameschen/Workspace/nexus/.agents/skills/zoom-out/SKILL.md` |

## Reference Candidate Counts By Root

| Root | Count |
|---|---:|
| `agents` | 672 |
| `claude` | 46 |
| `hermes` | 87 |
| `openclaw` | 2 |

## Quarantine Counts

| Status | Count |
|---|---:|
| `candidate_quarantine` | 574 |
| `worktree_copy_quarantine` | 136 |
| `runtime_vendor_readonly` | 49 |
| `archive_quarantine` | 12 |

## Operating Rule

Only `nexus_curated_candidate` skills can proceed to runtime route tests. Every other status is either reference-only, quarantine, read-only vendor, or manual triage.

## Next Tests

1. Inventory lint for all 1759 skills.
2. Quarantine enforcement tests for candidate, archive, worktree, and vendor statuses.
3. Trigger tests only for runtime candidates and selected reference candidates after import.
4. Flash benchmark only for skills with explicit capability mounts.
