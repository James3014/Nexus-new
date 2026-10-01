# G20 R1 complete-deployment source contract delta

```yaml
campaign_id: github-issue-526-g20-r1-source-contract-delta-20260903
repository: James3014/Nexus-new
source_spec: docs/specs/g20-r1-complete-deployment-source-contract-delta-20260903.md
source_spec_sha256: 5b88f83c2a6557e49348200bf9224fee20ccc2f06b4e84132aa0897517d367af
base_main: 1583a729cf611df0dc807a1f1b2458c8edff0359
base_tree: ae49701e33da46fdfd1dab9b031331f2f80e6ac9
auto_chain: false
claim_ceiling: R1_SOURCE_CANDIDATE_ACCEPTED_ONLY
task_card_sha256: 010e641d79515cecf28a5a40c718e73b7b79b4185cfffa177864d5a65c5fff84
execution_transport: EXTERNAL_BOOTSTRAP_RECOVERY
```

## Coverage

| Requirement | Acceptance | Implementing/witness card |
|---|---|---|
| `REQ-001` | `AC-001`, `AC-004` | `TASK-G20-R1-SOURCE-CONTRACT-DELTA` |
| `REQ-002` | `AC-002`, `AC-004` | `TASK-G20-R1-SOURCE-CONTRACT-DELTA` |
| `REQ-003` | `AC-002`, `AC-004` | `TASK-G20-R1-SOURCE-CONTRACT-DELTA` |
| `REQ-004` | `AC-003`, `AC-004` | `TASK-G20-R1-SOURCE-CONTRACT-DELTA` |

## Dependency graph and frontier

Single tracer-bullet card. Dependency is the Owner-settled 2026-09-03 A+B+C decision and exact source spec above. No host/runtime dependency is consumed by this source-only task.

| Order | Task | Status | Dependency | Unlock evidence |
|---|---|---|---|---|
| 1 | `TASK-G20-R1-SOURCE-CONTRACT-DELTA` | ACTIVE | source spec READY_FOR_TASK_CARDS | exact spec SHA above |

`AUTO_CHAIN=false`. The current Gateway cannot prove trustworthy current-card/current-main mutation identity for this authority repair, so the active card uses the current rollback-runbook `EXTERNAL_BOOTSTRAP_RECOVERY` transport in an exact clean DevSpace worktree. That transport does not create a second Nexus lifecycle or authority. The card ends at a committed source Candidate with implementer verification. Independent Candidate acceptance is coordinator-owned and occurs after the worker stops. Successor recovery authority/request/fence/op issuance is a later Gate and is not authorized by this campaign.
