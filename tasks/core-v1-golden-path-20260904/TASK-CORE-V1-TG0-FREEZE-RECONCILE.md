# TASK-CORE-V1-TG0-FREEZE-RECONCILE — Boundary, version, crosswalk, and legacy reconciliation

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-0 Boundary/version/crosswalk freeze
- **Requirements:** REQ-001;REQ-002;REQ-005;REQ-006;REQ-009
- **Acceptance:** AC-001;AC-003;AC-006;AC-013;AC-015
- **Auto-chain:** `false`
- **Maximum claim:** `CORE_V1_BOUNDARY_ADOPTED`
- **Depends on:** none
- **Dependency unlock evidence:** none
- **Task type:** `CONTRACT`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

The coordinator publishes the adopted boundary specification and validated campaign bundle under Ready Issue #763, including an additive supersession statement for the old Local ChangeSet card.

## Observable outcome

adopted two-core/version/invariant contract plus additive old-card reconciliation

## Non-goals

No Luna implementation worker, product/kernel/test/runtime implementation, live GitHub acquisition, runner, HTTP runtime, ledger, client, package, benchmark, second-repository selection, approval, integration, merge, push, release, deployment, or production claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-001 | ownership boundary | exactly Evidence Trust Core and Completion Core own truth |
| REQ-002 | invariant crosswalk | ten invariants have one owner and falsifiable seam |
| REQ-005 | version contract | public protocol and implementation schema stay separate |
| REQ-006 | contract binding | Acceptance Contract and Verification Plan bind exact ChangeSet |
| REQ-009 | claim ceiling | factual tri-state and bounded receipt cannot imply authority |
| AC-001 | witness | duplicate ownership and caller-minted truth are rejected |
| AC-003 | witness | stale/mismatched version and contract matrix is rejected |
| AC-006 | witness | reducer and receipt forgery probes preserve claim ceiling |
| AC-013 | witness | ten-invariant crosswalk is complete and uniquely owned |
| AC-015 | witness | Acceptance Contract and Verification Plan bind exact subjects |

## Owner decisions

DEC-001; DEC-006; DEC-007; DEC-008; DEC-009; DEC-010; DEC-011; DEC-012; DEC-013. Ready Issue #763 is the bounded authority. TG-0 must preserve old card/history and use formal additive supersession only.

## Source and start state

- **Workspace/root:** `/Users/jameschen/Workspace/Nexus-new`
- **Branch:** `main`
- **Starting HEAD:** `785751e109e90aa66a87a863dbc223618eceeffd`
- **Dirty baseline:** re-read at execution start; preserve unrelated changes
- **Required initial verification:** verify Issue #763, root, branch, HEAD/tree, dirty state, source spec SHA-256, and target-path absence/presence before publishing
- **Freshness rule:** re-read source HEAD, tree, dirty state, card state, and spec hash after any reconnect or before acceptance

## MCP execution profile

- **App/server and action snapshot:** not applicable; coordinator governance publishing under Ready Issue #763
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** one bounded Issue #763 publishing attempt; re-read target paths and diff before retry; never duplicate or overwrite unrelated files
- **Reconnect reconciliation:** re-read Issue #763, repository HEAD/tree, dirty state, and target-path diff before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller; CapabilityPlanner remains route authority
- **Execution authority:** primary controller under bounded Ready Issue #763 publishing authority; no Luna worker
- **Verification authority:** independent controller reviewer against source and Candidate evidence
- **Receipt authority:** source-spec/task-card validator reports and repository diff evidence; no product receipt is created
- **Approval/integration authority:** Owner-designated acceptance/integration authority only; not this card or worker

## Allowed scope

- **Read:** AGENTS.md;docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md;tasks/core-v1-golden-path-20260904/INDEX.md;tasks/productization-local-changeset-certification-v1-20260817/00-contract-freeze.md;tests/product
- **Edit:** none
- **Create:** docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md;tasks/core-v1-golden-path-20260904/INDEX.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG0-FREEZE-RECONCILE.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG1-GITHUB-ACQUISITION.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG2-PYTHON-PROFILE.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG3-EVIDENCE-TRUST.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG4-LEDGER-RECONCILIATION.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG5-HTTP-TRACER.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG6-CLIENTS-PACKAGE.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG7-CORPUS-SHADOW.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG8-VALUE-GATE.md;tasks/core-v1-golden-path-20260904/TASK-CORE-V1-TG9-VALUE-PILOT.md
- **Delete:** none
- **Maximum touched production files:** 12
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** source spec binds DEC-007 through DEC-013; existing old card is physically preserved and current core has reducer/receipt seams.
- **Assumptions requiring verification:** formal supported terminal compatibility state for old card; exact additive reconciliation API; no second truth owner introduced.
- **Architecture risks:** adapter or legacy lifecycle could become an accidental third owner.
- **Evidence risks:** static crosswalk or reducer tests alone cannot prove live runtime behavior.
- **Missing owner decision:** none

## Mandatory source audit

Inspect Ready Issue #763, current source/spec, old card, target paths, and campaign structure; verify duplicate reducers, protocol/schema conflation, caller-supplied truth, unsupported legacy-card state, scope, and deletion boundaries before publishing.

## Start-state classification

`GUARD_PREEXISTS`

## RED or existing-guard proof

The publishing contract has no product RED; the bounded proof is a scope/deletion audit that rejects product/test/runtime edits, old-card changes, target-path drift, duplicate Task IDs, or source/spec hash mismatch.

## Implementation constraints

Keep the two permanent truth owners; preserve public protocol `0.1.0-experimental` and implementation schema `nexus.changeset_certification.v2` as separate axes; preserve old history byte-for-byte; use formal additive supersession; do not add approval or integration authority.

## GREEN and regression gates

AC-001, AC-003, AC-006, AC-013, and AC-015 are published only with source/tree-bound crosswalk, validated spec and task-card reports, exact hashes, additive supersession statement, and zero product/test/runtime edits.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG0-01 | TARGET_ROOT | `python3 -B /Users/jameschen/.agents/skills/nexus-to-spec/scripts/validate_nexus_spec.py docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md` | validate published adopted spec | exit 0 |
| TG0-02 | TARGET_ROOT | `python3 -B /Users/jameschen/.agents/skills/nexus-to-task-cards/scripts/validate_nexus_task_cards.py tasks/core-v1-golden-path-20260904 --source-spec docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md --report /tmp/core-v1-task-cards-validation.json` | validate published campaign paths | valid true |
| TG0-03 | TARGET_ROOT | `shasum -a 256 docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md` | bind published spec hash | expected hash recorded |
| TG0-04 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |
| TG0-05 | TARGET_ROOT | `git diff --name-status -- docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md tasks/core-v1-golden-path-20260904 tasks/productization-local-changeset-certification-v1-20260817` | scope and deletion audit | only authorized target paths changed; old card unchanged |

## Physical evidence

Capture Issue #763, source HEAD/tree, dirty baseline, spec/task-card report hashes, published file hashes, target-path scope/deletion audit, diff check, and final repository state. No product receipt, live runtime, or Stable evidence is created.

## Independent review

A fresh reviewer verifies Issue #763, source digest, decision lineage, physical diff, exact target file set, old-card byte identity, scope/deletion audit, validators, and absence of product implementation or approval/integration authority.

## Exit conditions

- **PASS:** independent acceptance verifies AC-001, AC-003, and AC-006 and records a Candidate-bound receipt.
- **BLOCK:** unsupported legacy terminal state, duplicate owner, source drift, failed negative control, or missing Candidate evidence.
- **Residual debt:** live runtime and downstream cards remain unverified.
- **Next gate:** make TG-1 and TG-2 parallel-ready after independent acceptance; do not auto-activate either.
