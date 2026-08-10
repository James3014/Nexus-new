# Codex DX Reliability Campaign

- **Campaign ID:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source basis snapshot:** canonical code baseline b6601270edd95a756c4eab8c7a623006ee1b32d1; clean isolated Target /private/tmp/nexus-codex-dx-019fe8e1; owner decisions DEC-003 and DEC-004
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-CODEX-DX-002-HISTORY`
- **Maximum campaign claim:** owner-accepted immutable before-arm evidence and active history-receipt implementation; no benchmark lift, integration, release, or production claim

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| evidence-inventory | REQ-001 | AC-001 | complete bounded history receipt | working app/GitHub transports and stable cutoff | inventory negative control | coverage-bounded taxonomy | small | not applicable | none | TASK-CODEX-DX-002-HISTORY |
| context-contract | REQ-002 | AC-002 | one validated context/test index | approved index schema | static validator | bounded retrieval correctness | medium | not applicable | none | TASK-CODEX-DX-003-CONTEXT |
| core-bootstrap | REQ-003, REQ-004 | AC-003, AC-004 | secrets-free portable setup/doctor | clean isolated Target | clean-cache canary | core setup canary pass | medium | not applicable | none | TASK-CODEX-DX-004-BOOTSTRAP |
| test-contract | REQ-005 | AC-005 | truthful command matrix | core bootstrap contract | isolated command canary | command truth | medium | not applicable | none | TASK-CODEX-DX-005-TESTS |
| fixture-benchmark | REQ-006 | AC-006 | five deterministic smoke cases | test and fixture contracts | fixture negative control | fixture smoke 5/5 | medium | not applicable | none | TASK-CODEX-DX-006-FIXTURES |
| docs-convergence | REQ-007 | AC-007 | current docs point to canonical surfaces | context/setup/test contracts | docs command audit | static convergence | wide-mechanical | not applicable | none | TASK-CODEX-DX-007-DOCS |
| paired-benchmark | REQ-008, REQ-009 | AC-008, AC-009 | immutable before/after receipts | all product surfaces complete | 30 fresh-session trials | paired benchmark evidence only | medium | not applicable | none | TASK-CODEX-DX-001-BEFORE; TASK-CODEX-DX-009-AFTER |
| durable-feedback | REQ-010 | AC-010 | recurring failures map to one prevention seam | failure inventory and after benchmark | registry validation | prevention mapping | small | not applicable | none | TASK-CODEX-DX-008-FEEDBACK |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| REQ-001 | AC-001 | TASK-CODEX-DX-002-HISTORY | TASK-CODEX-DX-002-HISTORY | FULL |
| REQ-002 | AC-002 | TASK-CODEX-DX-003-CONTEXT | TASK-CODEX-DX-003-CONTEXT | FULL |
| REQ-003 | AC-003 | TASK-CODEX-DX-004-BOOTSTRAP | TASK-CODEX-DX-004-BOOTSTRAP | FULL |
| REQ-004 | AC-004 | TASK-CODEX-DX-004-BOOTSTRAP | TASK-CODEX-DX-004-BOOTSTRAP | FULL |
| REQ-005 | AC-005 | TASK-CODEX-DX-005-TESTS | TASK-CODEX-DX-005-TESTS | FULL |
| REQ-006 | AC-006 | TASK-CODEX-DX-006-FIXTURES | TASK-CODEX-DX-006-FIXTURES | FULL |
| REQ-007 | AC-007 | TASK-CODEX-DX-007-DOCS | TASK-CODEX-DX-007-DOCS | FULL |
| REQ-008 | AC-008 | TASK-CODEX-DX-001-BEFORE | TASK-CODEX-DX-009-AFTER | FULL |
| REQ-009 | AC-009 | TASK-CODEX-DX-009-AFTER | TASK-CODEX-DX-009-AFTER | FULL |
| REQ-010 | AC-010 | TASK-CODEX-DX-008-FEEDBACK | TASK-CODEX-DX-008-FEEDBACK | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-CODEX-DX-001-BEFORE | COMPLETED | IMPLEMENTATION | TRACER_BULLET | none | none | none | immutable before-arm receipt bound to b6601270e | benchmark schema tests and 15 fresh-session trial receipts | paired benchmark evidence only | medium | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-002-HISTORY | ACTIVE | IMPLEMENTATION | TRACER_BULLET | none | none | none | versioned history coverage receipt with honest transport gaps | schema tests and unavailable-transport negative control | coverage-bounded taxonomy | small | not applicable | AVAILABLE |
| TASK-CODEX-DX-003-CONTEXT | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CODEX-DX-001-BEFORE | EVIDENCE | accepted immutable before-arm context-cost receipt | one validated task-to-context index | static validator | bounded retrieval correctness | medium | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-004-BOOTSTRAP | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CODEX-DX-001-BEFORE | EVIDENCE | accepted immutable before-arm setup receipt | clean-cache secrets-free setup canary | clean-cache canary | core setup canary pass | medium | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-005-TESTS | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CODEX-DX-004-BOOTSTRAP | CONTRACT | accepted core setup and doctor command contract | isolated canonical command canary | isolated command canary | command truth | medium | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-006-FIXTURES | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CODEX-DX-005-TESTS | CONTRACT | accepted canonical test command contract | five deterministic smoke cases with negative control | fixture negative control | fixture smoke 5/5 | medium | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-007-DOCS | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CODEX-DX-003-CONTEXT; TASK-CODEX-DX-004-BOOTSTRAP; TASK-CODEX-DX-005-TESTS; TASK-CODEX-DX-006-FIXTURES | CONTRACT; CONTRACT; CONTRACT; CONTRACT | accepted context index identity; accepted setup command identity; accepted test command identity; accepted smoke benchmark identity | current developer docs resolve only canonical commands and authority | documentation command/path audit | static convergence | wide-mechanical | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-008-FEEDBACK | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CODEX-DX-002-HISTORY; TASK-CODEX-DX-006-FIXTURES | EVIDENCE; EVIDENCE | accepted failure taxonomy receipt; accepted fixture smoke receipt | recurring failures map to one prevention seam | prevention-registry validator | prevention mapping | small | not applicable | NOT_APPLICABLE |
| TASK-CODEX-DX-009-AFTER | PLANNED | INTEGRATION_VERIFY | TRACER_BULLET | TASK-CODEX-DX-002-HISTORY; TASK-CODEX-DX-003-CONTEXT; TASK-CODEX-DX-004-BOOTSTRAP; TASK-CODEX-DX-005-TESTS; TASK-CODEX-DX-006-FIXTURES; TASK-CODEX-DX-007-DOCS; TASK-CODEX-DX-008-FEEDBACK | EVIDENCE; CONTRACT; CONTRACT; CONTRACT; EVIDENCE; CONTRACT; EVIDENCE | accepted history coverage receipt; accepted context index receipt; accepted setup canary receipt; accepted test command receipt; accepted fixture smoke receipt; accepted docs audit receipt; accepted prevention mapping receipt | immutable after arm and paired comparison receipt | 30 fresh-session trials and independent aggregation | paired benchmark evidence only | medium | not applicable | NOT_APPLICABLE |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** TASK-CODEX-DX-002-HISTORY; TASK-CODEX-DX-003-CONTEXT; TASK-CODEX-DX-004-BOOTSTRAP
- **Selected frontier:** TASK-CODEX-DX-002-HISTORY
- **Selection rationale:** The Owner accepted Candidate `b5017f16fb3d969a654fccc0fd6c5c6d22911ae8` after its exact tests and fresh Luna review passed, then authorized continued execution. History transport is available and Card 002 can bind live bounded coverage before product-facing changes.
- **Exact unblock condition:** none

## 5. Campaign authority and non-goals

The Owner approved the source specification and continued governed work. Each implementation card may implement, verify, commit only its scoped changes, and form a Candidate through the repository-owned local governed lifecycle. Workers and reviewers cannot approve, integrate, push, merge, clean up, or claim production readiness. The dirty canonical checkout and unrelated linked worktrees remain out of scope. `AUTO_CHAIN=false` and parallel execution is forbidden.

## 6. Supersession and change history

Initial campaign compiled from owner-approved `SPEC-CODEX-DX-RELIABILITY-20260810`. It supersedes no campaign or Task Card. On 2026-08-10 the Owner accepted the immutable before-arm Candidate `b5017f16fb3d969a654fccc0fd6c5c6d22911ae8` and authorized the frontier transition to `TASK-CODEX-DX-002-HISTORY`.
