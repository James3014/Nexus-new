# Issue #332 bounded DIRECT_DELEGATED authority campaign

- **Campaign ID:** `CAMPAIGN-NEXUS-332-DIRECT-DELEGATED-20260816`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-NEXUS-332-DIRECT-DELEGATED`
- **Source spec SHA-256:** `9d101c32dd559f4bf14713d49bb79e45dc1c0b1ad00157fa7319eb8d03de1f7a`
- **Source basis snapshot:** `James3014/Nexus-new`; Issue #332; baseline `cc88519b314a782785ec2703a87f458bde5d4625`; branch `codex/issue-332-direct-delegated`; durable scope comments `5306226300` and `5306246330`
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-332-001`
- **Maximum campaign claim:** `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY`

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| TG-001 | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005 | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006 | one exact Candidate adds bounded `DIRECT_DELEGATED` while preserving #163 merge authority | exact baseline `cc88519b...` and Issue #332 contract | focused tests + diff/path audit + exact-head CI + independent acceptance | `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY` | medium | `CANDIDATE` | none | TASK-332-001 |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| REQ-001 | AC-001 | TASK-332-001 | TASK-332-001 | FULL |
| REQ-002 | AC-002 | TASK-332-001 | TASK-332-001 | FULL |
| REQ-003 | AC-003 | TASK-332-001 | TASK-332-001 | FULL |
| REQ-004 | AC-004 | TASK-332-001 | TASK-332-001 | FULL |
| REQ-005 | AC-005 | TASK-332-001 | TASK-332-001 | FULL |
| REQ-005 | AC-006 | TASK-332-001 | TASK-332-001 | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-332-001 | ACTIVE | CONTRACT | TRACER_BULLET | none | none | none | One bounded Candidate makes `DIRECT_DELEGATED` explicit while leaving #163 protected-merge authority unchanged. | focused bootstrap authority/context tests; complete path/deletion audit; exact-head CI; independent Candidate acceptance | `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY` | medium | CANDIDATE | READY |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-332-001`
- **Selected frontier:** `TASK-332-001`
- **Selection rationale:** the validated specification has one handoff group, all owner semantics are settled, the GitHub typed-action transport is available, and no task dependency remains.
- **Exact unblock condition:** `none`

## 5. Campaign authority and non-goals

Issue #332 plus this validated campaign authorize one bounded issue-branch Candidate only. The primary coordinator may use repository-bound GitHub typed actions to create/update the authorized branch files, create the Candidate PR, and gather physical evidence. The task grants no delegated-worker self-approval, no protected merge, no branch-protection bypass, no Nexus runtime/route/lifecycle mutation, no Workforce policy/model promotion, no release, and no production/public claim. Independent Candidate acceptance is required before the existing #163 protected-merge Owner slot can even be requested. `AUTO_CHAIN=false` and no successor task is activated by completion.

## 6. Supersession and change history

- 2026-08-16: compiled from validated `SPEC-NEXUS-332-DIRECT-DELEGATED` at SHA-256 `9d101c32dd559f4bf14713d49bb79e45dc1c0b1ad00157fa7319eb8d03de1f7a`.
- Historical PR #320 is evidence only and is not an authority source or implementation base for this campaign.
