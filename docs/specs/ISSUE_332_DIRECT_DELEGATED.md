# Enable bounded DIRECT_DELEGATED execution without changing merge authority

- **Spec ID:** `SPEC-NEXUS-332-DIRECT-DELEGATED`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `James3014/Nexus-new`; `main=cc88519b314a782785ec2703a87f458bde5d4625`; branch `codex/issue-332-direct-delegated`; Issue #332; comments `5306226300`, `5306246330`
- **Supersedes:** `none`
- **Claim ceiling:** `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY`

## 1. Problem statement

Current authority escalates direct work to governed execution solely when implementation is delegated. Issue #332 settles a narrow external delegation exception while preserving #163 protected-merge authority.

## 2. Desired outcome

An explicit Owner request can select one bounded `DIRECT_DELEGATED` milestone through an approved non-Nexus control plane; the coordinator independently verifies the result and stops. The lane grants no Nexus route, admission, approval, integration, merge, release, or production authority.

## 3. Basis, coverage, and freshness

Repository source at `cc88519b314a782785ec2703a87f458bde5d4625`, Issue #332, comments `5306226300` and `5306246330`, current `AGENTS.md`, task-execution/workforce overlays, and active #163 merge-slot semantics are the binding basis. PR #320 is historical evidence only. Rebind before acceptance if `main` changes.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| DEC-001 | DEC | Add one bounded Owner-authorized `DIRECT_DELEGATED` lane. | Issue #332 | current | BINDING | implementation only |
| DEC-002 | DEC | Preserve #163 exact protected-merge semantics. | Issue #332 | current | BINDING | merge remains separate |
| DEC-003 | DEC | Keep semantic and governance metadata scope minimal. | Issue #332 comments | current | BINDING | scope only |
| CUR-001 | CUR | `main=cc88519b314a782785ec2703a87f458bde5d4625`. | GitHub main | exact SHA | EVIDENCE | may drift |
| CUR-002 | CUR | Root authority currently makes delegated implementation a governed-escalation trigger. | `AGENTS.md` | CUR-001 | EVIDENCE | source fact |
| CUR-003 | CUR | Task contract currently treats delegation as escalation and preserves exact merge-slot authority. | task contract | CUR-001 | EVIDENCE | source fact |
| CUR-004 | CUR | Workforce overlay governs Nexus provider execution and has no external direct-delegation carve-out. | workforce overlay | CUR-001 | EVIDENCE | source fact |
| CON-001 | CON | Protected merge requires exact fresh `MERGE_SLOT_GRANTED`; `MERGE_INTENT` is evidence only. | #163/current authority | CUR-001 | BINDING | merge only |
| HIS-001 | HIS | PR #320 mixed useful direct-delegation ideas with rejected merge-authority drift. | PR #320 | historical | CONTEXT_ONLY | do not copy wholesale |
| REJ-001 | REJ | Broader generic Owner integration authority is rejected for this change. | Issue #332 | current | REJECTED | must remain absent |

## 5. Current verified state

At CUR-001 there is no authoritative `DIRECT_DELEGATED` lane; delegation alone escalates direct work, Nexus runtime remains admission-governed, and CON-001 governs protected merge.

## 6. Owner decisions

`DEC-001`, `DEC-002`, and `DEC-003` are settled. No product/business decision remains open.

## 7. Canonical terminology

`DIRECT_DELEGATED` = Owner -> primary coordinator -> approved non-Nexus control plane -> exactly one bounded external worker -> independent coordinator verification -> STOP. External identity binding is transport evidence only. Protected merge authority remains CON-001.

## 8. Change delta

Mode: BROWNFIELD.

Baseline: CUR-001.

### ADDED

Explicit `DIRECT_DELEGATED`, bounded eligibility/identity/isolation/retry/verification/STOP rules, external-vs-Nexus admission boundary, and tests.

### MODIFIED

Delegation alone no longer forces governed execution when all direct-delegated conditions hold; conditional-load and workforce-overlay guidance gains the new lane.

### REMOVED

The unconditional implication that delegation by itself always requires governed execution.

### RENAMED

none.

## 9. Scope

Semantic files: `AGENTS.md`, `docs/agents/TASK_EXECUTION_CONTRACT.md`, `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`, `tests/ops/test_bootstrap_authority_files.py`, `tests/ops/test_bootstrap_context_budget.py`. Governance metadata: `docs/specs/ISSUE_332_DIRECT_DELEGATED.md`, campaign `INDEX.md`, one active Task Card.

## 10. Non-goals

No route/CapabilityPlanner/lifecycle/runtime/provider-selection change; no Workforce policy/model promotion; no CI redesign; no protected merge/approval/integration/release/production authority; no test weakening; no auto-chain.

## 11. User and operator stories

The Owner can explicitly choose one bounded DevSpace/Agy milestone without Nexus machinery solely because a worker is delegated; crossing a governed boundary fails closed; protected merge still follows #163.

## 12. Architecture and authority boundaries

The delegated worker cannot approve, integrate, merge, push protected refs, clean unrelated state, release, claim production/public readiness, or self-verify. `AUTO_CHAIN=false`. Nexus runtime still requires Nexus Workforce Admission.

## 13. Requirements

### REQ-001 — Explicit direct-delegated lane

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-002, CUR-003`
- **Behavior:** Repository authority SHALL define explicit current-Owner-authorized `DIRECT_DELEGATED` for exactly one bounded external milestone and SHALL NOT escalate solely because implementation is delegated when lane conditions hold.
- **Failure behavior:** Missing/implicit lane selection or unconditional delegation escalation fails acceptance.
- **Rationale:** delegation transport alone should not require Nexus governance.
- **Authority/interface:** root authority and task contract.
- **Non-goal linkage:** section 10.

### REQ-002 — Bounded and independently verified

- **Status:** `SETTLED`
- **Source:** `DEC-001`
- **Behavior:** The lane SHALL bind one worker, exact external identity, bounded scope, isolation, session reconciliation, independent coordinator verification, STOP, `AUTO_CHAIN=false`, and stable fail-closed escalation.
- **Failure behavior:** Self-approval, auto-chain, blind replacement retry, or silent scope/authority widening blocks the lane.
- **Rationale:** direct delegation conserves authority.
- **Authority/interface:** task contract and bootstrap tests.
- **Non-goal linkage:** section 10.

### REQ-003 — External identity is not Nexus admission

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-004`
- **Behavior:** Non-Nexus `DIRECT_DELEGATED` SHALL bind external control-plane/profile/provider/model/workspace/scope evidence directly and SHALL NOT require Nexus Workforce Admission solely for that lane; Nexus runtime SHALL retain fresh admission requirements.
- **Failure behavior:** External identity treated as Nexus authority, or weakened Nexus-runtime admission, blocks acceptance.
- **Rationale:** separate transport identity from Nexus execution authority.
- **Authority/interface:** workforce overlay and authority tests.
- **Non-goal linkage:** section 10.

### REQ-004 — Preserve protected merge authority

- **Status:** `SETTLED`
- **Source:** `DEC-002, CON-001, REJ-001`
- **Behavior:** The change SHALL preserve fresh exact `MERGE_SLOT_GRANTED`, evidence-only `MERGE_INTENT`, exact repo/PR/head/base binding, drift invalidation, required checks, and expected-head/CAS semantics.
- **Failure behavior:** Any generic integration-authority substitution or weakening blocks acceptance.
- **Rationale:** direct delegation is implementation authority only.
- **Authority/interface:** root/task contract and merge-slot tests.
- **Non-goal linkage:** section 10.

### REQ-005 — Minimal physical Candidate

- **Status:** `SETTLED`
- **Source:** `DEC-003, DEC-002`
- **Behavior:** The Candidate SHALL change only the five semantic files plus three authorized metadata files, with no deletion or unrelated CI/runtime/product delta, and SHALL preserve/add truthful negative witnesses.
- **Failure behavior:** Out-of-scope paths, deletion, test weakening, stale evidence, or false-green verification blocks acceptance.
- **Rationale:** isolate the one-time authority change.
- **Authority/interface:** exact diff and verification evidence.
- **Non-goal linkage:** section 10.

## 14. Behavioral and interface decisions

Lane selection is explicit Owner authority. Worker PASS is implementation evidence only. Timeout/disconnect reconciles the same session/filesystem/provider state before retry. DevSpace worktree isolation is not a Nexus Target/Candidate.

## 15. Verification seam

Use focused authority/context tests, `git diff --check`, complete changed/deleted-path audit, exact-head required GitHub CI, preservation of merge-slot negative controls, and independent Candidate acceptance.

## 16. Acceptance criteria

### AC-001 — Lane explicit

- **Requirement:** `REQ-001`
- **Evidence level:** `STATIC`
- **Verification seam:** root/task source and bootstrap tests.
- **Pass:** `DIRECT_DELEGATED` is explicit and delegation alone is no longer unconditional escalation.
- **Negative control:** other governed escalation conditions remain.
- **Fail:** lane implicit/missing or delegation still always governed.
- **Receipt binding:** exact Candidate commit/tree/diff.

### AC-002 — Boundaries fail closed

- **Requirement:** `REQ-002`
- **Evidence level:** `STATIC`
- **Verification seam:** task contract and bootstrap tests.
- **Pass:** one-worker/identity/isolation/retry/independent-verification/STOP rules are present.
- **Negative control:** worker has no self-approval/integration/merge/release authority.
- **Fail:** any silent widening or auto-chain exists.
- **Receipt binding:** exact Candidate commit/tree/diff.

### AC-003 — Admission split preserved

- **Requirement:** `REQ-003`
- **Evidence level:** `STATIC`
- **Verification seam:** workforce overlay and authority tests.
- **Pass:** external direct delegation uses direct identity binding while Nexus runtime still requires admission.
- **Negative control:** external binding grants no Nexus authority.
- **Fail:** admission boundary is blurred or weakened.
- **Receipt binding:** exact Candidate commit/tree/diff.

### AC-004 — Merge authority unchanged

- **Requirement:** `REQ-004`
- **Evidence level:** `STATIC`
- **Verification seam:** merge paragraphs/assertions plus independent review.
- **Pass:** all CON-001 semantics remain.
- **Negative control:** no generic Owner integration-authority substitution and no removed merge-slot witnesses.
- **Fail:** any merge-authority weakening appears.
- **Receipt binding:** exact Candidate commit/tree/diff.

### AC-005 — Physical scope bounded

- **Requirement:** `REQ-005`
- **Evidence level:** `STATIC`
- **Verification seam:** complete path/deletion audit and `git diff --check`.
- **Pass:** only eight authorized paths change and zero files are deleted.
- **Negative control:** compare the complete path set, not selected hunks.
- **Fail:** unauthorized path/deletion or unrelated change exists.
- **Receipt binding:** exact Candidate commit/tree/diff.

### AC-006 — Exact-head verification current

- **Requirement:** `REQ-005`
- **Evidence level:** `STATIC`
- **Verification seam:** focused tests, required CI, independent acceptance.
- **Pass:** all required evidence is current and successful on the exact Candidate head.
- **Negative control:** stale/skipped/worker-self-reported evidence is insufficient.
- **Fail:** any required evidence fails, is stale, or is unknown.
- **Receipt binding:** exact Candidate head and check/run identities.

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| REQ-001 | DEC-001, CUR-002, CUR-003 | ADDED/MODIFIED | AC-001 | STATIC | direct-delegated source only | TG-001 |
| REQ-002 | DEC-001 | ADDED | AC-002 | STATIC | bounded-lane source only | TG-001 |
| REQ-003 | DEC-001, CUR-004 | ADDED/MODIFIED | AC-003 | STATIC | external-identity boundary only | TG-001 |
| REQ-004 | DEC-002, CON-001, REJ-001 | preserved | AC-004 | STATIC | merge-preservation only | TG-001 |
| REQ-005 | DEC-003, DEC-002 | verification constraint | AC-005, AC-006 | STATIC | Candidate only | TG-001 |

## 18. Evidence and claim ceiling

Before merge the maximum claim is `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY`; no current-main/runtime/release/production claim is permitted.

## 19. Rollback and failure handling

Authority ambiguity, merge-policy drift, test weakening, incompatible main drift, or evidence gaps fail closed. This task does not authorize rollback or merge of `main`.

## 20. Documentation and learning write-back

Only the three authority documents, their tests, this spec, INDEX, and one Task Card are required. No extra ADR/report is created.

## 21. Risks and unknowns

PR #320 must not be copied wholesale. `main` may drift and requires rebind. No unresolved product/business semantics remain.

## 22. Unresolved owner decisions

none

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| TG-001 | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005 | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006 | one exact Candidate adds bounded `DIRECT_DELEGATED` while preserving #163 merge authority | exact baseline `cc88519b...` and Issue #332 contract | focused tests + diff/path audit + exact-head CI + independent acceptance | `DIRECT_DELEGATED_AUTHORITY_CANDIDATE_ONLY` | medium | `CANDIDATE` | none |

## 24. Out of scope

Anything outside the five semantic files and three metadata files; any merge-policy rewrite; any Nexus runtime/route/lifecycle/workforce-policy implementation; any CI redesign; any approval/integration/merge/release/production/public action or claim.

## 25. Supersession and change history

2026-08-16: compiled from Issue #332, exact main baseline, current authority, active #163 merge contract, and rejected PR #320 merge-policy drift. It does not supersede #163 or make PR #320 authoritative.
