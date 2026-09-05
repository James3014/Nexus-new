---
artifact_authority: implementation_contract
owner: James Chen
status: active
issue: 806
mode: brownfield
---

# Nexus Break-Glass Governance Recovery 001

## Purpose and authority

This contract closes the self-hosting authority recursion recorded by GitHub
Issue #806. It adds one narrowly typed Owner-rooted recovery authority for a
governance-plane failure without creating a second normal lifecycle, Router,
Planner, standing grant, merge controller, or runtime manager.

Binding Owner activation for the first SOURCE_REPAIR canary is Issue #806
comment `5555340739`, canonical activation payload SHA-256
`d2313d38c4b15d16cf42497c267bd7071195bf3f58f485eea6d659ded6e09a95`,
bound to GitHub main `8e8e02911c888d4c8a4667d4b5dd13df85c20cfd` / tree
`78da10b2402f8c25f4d04ae5b470e7c10bd984f7` and recovery attempt
`BG-806-20260906 / BG-806-A1`.

#526 / PR #805 are incident witnesses only. This contract grants them no
retroactive Task Card, acceptance, merge, runtime, or release authority.

## Source ledger

| ID | Class | Statement |
|---|---|---|
| DEC-001 | OWNER_DECISION | Owner requires #806 to be carried through implementation and closure rather than stopping at G0 analysis. |
| DEC-002 | OWNER_DECISION | Owner selected an external Owner-rooted break-glass authority rather than permanent direct bypass; source repair, integration, and runtime recovery remain separate authorities. |
| DEC-003 | OWNER_DECISION | Issue #806 comment 5555340739 explicitly authorizes one SOURCE_REPAIR attempt only, with exact repo/base/tree/scope/expiry/verifiers/claim ceiling. |
| CUR-001 | CURRENT_STATE | Normal Task Card and standing-grant consumers are inside the governance plane and therefore cannot be the independent recovery root when that plane is the failed seam. |
| CUR-002 | CURRENT_STATE | Existing rollback guidance already defines bounded clean-base repair, immutable repair identity, tamper/retry checks, separate integration/activation, and live post-recovery proof, but previously did not materialize independent Owner authority. |
| DER-001 | DERIVATION | The smallest safe addition is an external Owner activation plus a host-local evidence consumer that never imports or calls Gateway, Task Card, lifecycle, Workforce Admission, or normal standing-grant authority. |

## Brownfield delta

- **ADDED:** canonical `nexus.break_glass_owner_activation.v1` authority payload.
- **ADDED:** externally materialized GitHub Owner comment envelope and exact payload hash binding.
- **ADDED:** durable host-local recovery evidence chain `PREPARED -> APPLIED -> VERIFIED -> CONSUMED`.
- **ADDED:** narrow operator CLI that reads fixed Git identity/diff evidence but performs no repair effect itself.
- **MODIFIED:** bootstrap recovery documentation now requires this canonical authority for governance-plane self-repair.
- **UNCHANGED:** normal standing grants, Task Cards, CapabilityPlanner, Workforce Admission, Candidate acceptance, protected merge, Gateway reload/rebind, release, and production authority.

## Requirements

### REQ-001 — Qualifying recovery authority

A break-glass attempt SHALL require a current external Owner activation bound to
`GOVERNANCE_PLANE_RECOVERY_REQUIRED`, exact repository, Issue, recovery ID,
attempt ID, base commit/tree, failure-evidence hash, allowed/forbidden paths,
verifier set, validity window, effect class, and claim ceiling. A bare caller
boolean, worker assertion, failed Task Card, expired standing grant, connector
session, or model identity SHALL NOT supply this authority.

### REQ-002 — Owner provenance and tamper binding

The consumer SHALL bind the exact GitHub Owner comment identity, author
`James3014`, Issue #806, canonical activation payload SHA-256, and comment URL.
Identity substitution, payload tamper, malformed hashes, or scope mismatch SHALL
fail closed before recovery evidence advances.

### REQ-003 — Independence from failed governance plane

The SOURCE_REPAIR authority consumer SHALL NOT import or call the normal
standing-grant store, unified Gateway, Task Card creation, lifecycle dispatch,
Workforce Admission, CapabilityPlanner, or runtime reload path. It may consume
an externally fetched Owner comment envelope and local physical repository
evidence only.

### REQ-004 — Phase separation

`SOURCE_REPAIR`, `EMERGENCY_INTEGRATION`, and `RUNTIME_RECOVERY` SHALL be
distinct effect classes. The #806 G1 activation authorizes SOURCE_REPAIR only.
SOURCE_REPAIR SHALL NOT imply Candidate acceptance, protected-main mutation,
merge, force push, ref deletion, runtime activation, release, or public/
production claim.

### REQ-005 — Exact scope/base fence

Before PREPARED, the consumer SHALL verify the observed repository HEAD/tree
matches the activated base exactly. Before APPLIED, every changed path SHALL be
inside `allowed_paths` and outside `forbidden_paths`. Stale base, tree
substitution, path widening, relative-path escape, or forbidden-path mutation
SHALL fail closed.

### REQ-006 — Immutable repair evidence

APPLIED SHALL bind exact repair commit, tree, full-diff SHA-256, changed paths,
and implementer identity. The consumer SHALL record evidence only; it SHALL NOT
run the source mutation, commit, push, merge, or runtime effect itself.

### REQ-007 — Verification binding

VERIFIED SHALL bind the same repair commit/tree/diff plus verifier evidence.
The verifier identity SHALL differ from the implementer identity. Verification
subject substitution SHALL fail closed.

### REQ-008 — Crash/retry/replay safety

Each `recovery_id + attempt_id` SHALL use durable immutable phase transition
records with canonical hashes and predecessor chaining. Exact same-operation
retry MAY return the same transition; conflicting retry SHALL fail closed.
Phase gaps, hash tamper, symlink state, or post-CONSUMED replay SHALL fail
closed. A retry after uncertain acknowledgement SHALL inspect the same attempt
rather than create a replacement authority identity.

### REQ-009 — Authority collapse

CONSUMED SHALL exist only after VERIFIED and SHALL record SOURCE_REPAIR as the
only granted effect plus explicit excluded effects. After CONSUMED, mutation
replay through that recovery attempt SHALL be denied. Runtime recovery and
emergency integration, if actually required, need new Owner authority artifacts.

### REQ-010 — Post-recovery closure

Issue #806 SHALL NOT be considered complete merely because source tests pass or
a PR merges. Closure additionally requires fresh normal-governance canary
evidence exercising the incident-relevant path, followed by proof that the
break-glass authority is terminal and replay is denied.

## Acceptance criteria

| AC | Requirement | Pass condition | Negative / false-green control |
|---|---|---|---|
| AC-001 | REQ-001/002 | Real #806 activation payload hashes to the frozen SHA and validates against Owner/comment identity. | Forged author, comment ID swap, payload hash tamper, stale/not-yet-valid activation fail. |
| AC-002 | REQ-003 | Static/source inspection shows no dependency on standing-grant/Gateway/lifecycle/Task Card/Workforce execution consumers. | Import/search check fails if forbidden authority modules are referenced by recovery consumer. |
| AC-003 | REQ-004 | G1 activation validates only SOURCE_REPAIR. | EMERGENCY_INTEGRATION or RUNTIME_RECOVERY substitution fails. |
| AC-004 | REQ-005 | Exact base/tree prepares and authorized paths apply. | Wrong base/tree, README scope widening, forbidden standing-grant path, and `..` escape fail. |
| AC-005 | REQ-006/007 | APPLIED and VERIFIED bind one immutable repair subject and distinct implementer/verifier identities. | Verifier==implementer and commit substitution fail. |
| AC-006 | REQ-008 | Exact PREPARED retry is idempotent; valid chain reaches CONSUMED. | Phase skip, conflicting APPLIED retry, transition tamper and symlink state fail. |
| AC-007 | REQ-009 | CONSUMED explicitly records `SOURCE_REPAIR_ONLY` and excluded merge/runtime/release effects. | Second consume and post-consume apply fail with replay denial. |
| AC-008 | REQ-010 | Integrated revision passes focused/regression evidence and a fresh normal-governance canary, then terminal/replay-denial evidence is recorded. | Green source tests alone or merged PR without canary cannot close #806. |

## Verification set for G1 source Candidate

```text
python3 -m pytest tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py -q
python3 -m pytest tests/nexus/orchestrator/test_standing_grant_store.py tests/ops/test_bootstrap_authority_files.py -q
python3 -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py
git diff --check
```

The verifier also inspects complete changed/deleted/out-of-scope paths and the
full diff. These checks establish source Candidate evidence only; they do not
mint merge or runtime authority.

## Recovery closure chain

```text
qualifying failure evidence
  -> Owner GitHub activation comment
  -> external validation + exact source-repair scope
  -> PREPARED
  -> immutable repair commit/tree/diff
  -> APPLIED
  -> independent physical verification
  -> VERIFIED
  -> separately authorized integration if needed
  -> separately authorized runtime recovery if needed
  -> fresh normal-Governance canary
  -> CONSUMED / authority terminal proof
  -> replay denied
  -> normal Governance
```
