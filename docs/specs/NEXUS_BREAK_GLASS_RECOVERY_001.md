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
| DEC-004 | OWNER_DECISION | Issue #806 comment 5555313946 selects Dev MCP / DevSpace OWNER_DIRECT as the independent recovery execution substrate and forbids creation of a second general recovery executor. |
| CUR-001 | CURRENT_STATE | Normal Task Card and standing-grant consumers are inside the governance plane and therefore cannot be the independent recovery root when that plane is the failed seam. |
| CUR-002 | CURRENT_STATE | Existing rollback guidance already defines bounded clean-base repair, immutable repair identity, tamper/retry checks, separate integration/activation, and live post-recovery proof, but previously did not materialize independent Owner authority. |
| DER-001 | DERIVATION | The smallest safe addition is an external Owner activation plus a host-local evidence consumer that never imports or calls Gateway, Task Card, lifecycle, Workforce Admission, or normal standing-grant authority. |

## Brownfield delta

- **ADDED:** canonical `nexus.break_glass_owner_activation.v1` authority payload.
- **ADDED:** externally materialized GitHub Owner activation, verification, emergency-integration, and terminal/revocation comment envelopes with exact canonical payload hash binding.
- **ADDED:** durable host-local source-repair evidence chain `PREPARED -> APPLIED -> VERIFIED -> CONSUMED` plus a separate emergency-integration `PREPARED -> CONSUMED` chain.
- **ADDED:** narrow operator CLI that reads fixed Git/GitHub evidence but performs no repair, merge, push, reload, or release effect itself.
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

VERIFIED SHALL require a separately materialized Owner verification comment
whose canonical payload binds the same repair commit/tree/full-diff plus a
non-empty set of exact-head successful CI/check run identities. The production
consumer SHALL re-read that GitHub comment and SHALL NOT accept a caller-supplied
`verifier_id` or opaque verification hash as sufficient evidence. The verifier
identity SHALL differ from the implementer identity. Check-head, comment,
payload, or repair-subject substitution SHALL fail closed.

### REQ-007A — Emergency integration authority

When normal integration authority is part of the unavailable governance plane,
merge requires a separate Owner `EMERGENCY_INTEGRATION` comment bound to exact
source activation, exact Owner verification payload, PR number, accepted
head/tree/diff, the freshly observed integration-time main/base, `merge`
integration method, successful exact-head checks, expiry, and claim ceiling.
The source-repair base remains immutable provenance and MAY differ from the
integration-time main after benign concurrent main movement; the integration
grant MUST rebind current main rather than silently reuse the source base. The
validated grant may be consumed only by an existing bounded exact-head/CAS merge
sink such as `git_merge_pull_request`.
A bare `ownerConfirmation=true` is an effect confirmation, not the break-glass
authority source. Break-glass integration does not permit squash or rebase,
preserving the accepted head as merge lineage. No force push, ref deletion,
unrelated merge, runtime
activation, release, or production/public claim is granted.

### REQ-008 — Crash/retry/replay safety

Each source or integration attempt SHALL use stable recovery/effect identity and
durable immutable transition records with canonical hashes and predecessor
binding. Exact same-operation reconciliation MAY return the same terminal
record; conflicting retry SHALL fail closed. Phase gaps, hash tamper, symlink
state, or post-CONSUMED replay SHALL fail closed. After an uncertain remote
merge acknowledgement, the controller SHALL read back the same PR/default-branch
state before deciding whether any effect remains; it SHALL NOT blindly invoke a
second merge attempt.

### REQ-009 — Authority collapse

SOURCE_REPAIR `CONSUMED` SHALL exist only after VERIFIED plus a fresh typed
normal-governance canary proving source/runtime identity, action binding, normal
authority readback, one bounded governance operation receipt, and verifier
receipt. It SHALL record SOURCE_REPAIR as the only granted source effect plus
explicit excluded effects. Emergency integration has its own terminal record
bound to authoritative merge/main readback. After recovery succeeds, the Owner
SHALL also publish a canonical `nexus.break_glass_owner_terminal.v1` comment
bound to the source activation, integrated main and canary evidence (or an
explicit REVOKED reason). Production recovery consumers SHALL scan #806 for that
terminal witness before source mutation so a fresh session with no host-local
state cannot replay the old grant. After either local or global terminality,
effect replay through that attempt SHALL be denied. Runtime recovery, if
actually required, needs a third Owner authority artifact.

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
| AC-005 | REQ-006/007 | APPLIED and VERIFIED bind one immutable repair subject; VERIFIED is rooted in an Owner GitHub verification comment whose exact-head checks are all successful. | Caller-only verifier/hash, verifier==implementer, check-head substitution, and commit substitution fail. |
| AC-006 | REQ-008 | Exact PREPARED retry is idempotent; source and integration attempts reconcile through durable terminal records. | Phase skip, conflicting APPLIED retry, transition tamper, symlink state, and blind post-merge retry fail. |
| AC-007 | REQ-007A/009 | A separate Owner integration grant rebinds the freshly observed current main and exact PR/head/checks; only an existing exact-head/CAS merge sink may consume it. Source-repair base may remain older immutable provenance. Source CONSUMED requires a fresh normal-governance canary plus a global Owner terminal/revocation comment. | Source authority cannot merge; stale integration base is rejected by the merge sink; integration grant cannot widen effect; local and fresh-session global post-consume replay fail. |
| AC-008 | REQ-010 | Integrated revision passes focused/regression evidence and a fresh normal-governance canary, then terminal/replay-denial evidence is recorded. | Green source tests alone or merged PR without canary cannot close #806. |
| AC-009 | REQ-003/007A/009 | Controlled self-hosting E2E starts with normal governance unavailable, exercises real break-glass source/integration contracts, restores the normal-path canary, consumes emergency authority, and proves replay denial. | Harness that never begins in a failed-governance state or never exercises replay denial is not sufficient. |

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
