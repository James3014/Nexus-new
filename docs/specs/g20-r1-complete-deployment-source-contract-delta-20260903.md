# G20 R1 Complete-Deployment Source Contract Delta

- **Spec ID:** `SPEC-G20-R1-COMPLETE-DEPLOYMENT-SOURCE-DELTA-20260903`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `James3014/Nexus-new` isolated worktree, base `1583a729cf611df0dc807a1f1b2458c8edff0359`, tree `ae49701e33da46fdfd1dab9b031331f2f80e6ac9`, clean at preflight
- **Supersedes:** only the Gitlink prohibition, fresh-main ancestry requirement for rollback predecessor, and same-authority retry assumption in `TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION`; all other R1 safety/lifecycle requirements remain in force
- **Claim ceiling:** source contract ready for bounded implementation and independent Candidate acceptance; no host recovery/runtime effect is authorized

## 1. Problem statement

G20 recovery is deterministically blocked before effect by two current R1 source assumptions that do not match the authorized repository topology:

1. `scripts/ops/mcp_gateway_durable.py` rejects every mode `160000` Gitlink even though the exact G20 desired commit/tree legitimately contains six Gitlinks.
2. R1 requires accepted, desired, and predecessor commits to be ancestors of fresh remote `main`, while Owner-authorized rollback predecessor `3d28fa7b65df30e207e53de7caadf93a2b7a8fc0` / tree `5e6476b2b12211e7cdcfe9294942b633ffbcef59` is an exact side-branch commit and is not a `main` ancestor.

A manager/Card change also changes the cryptographic recovery authority inputs. The failed R2 operation therefore cannot be replayed with changed semantics.

## 2. Desired outcome

R1 SHALL preserve exact source identity and fail-closed recovery while supporting the real Nexus topology:

- exact-tree-bound Gitlinks are inert repository metadata only;
- rollback predecessor is reconstructable from an Owner-authority-bound immutable artifact rather than inferred from fresh-main ancestry;
- a security-contract/manager change creates successor recovery authority/request/fence/operation identity rather than reusing the failed R2 operation.

## 3. Basis, coverage, and freshness

Freshly verified on 2026-09-03:

- GitHub `main`: `1583a729cf611df0dc807a1f1b2458c8edff0359` / tree `ae49701e33da46fdfd1dab9b031331f2f80e6ac9`.
- Existing R1 Card SHA-256: `b316a07965b070d1b76fa11fa20105d40bd2be1de325576e719a127bdc1d8609`.
- Existing manager SHA-256: `6625224ab881cdbd68f66607d190b1b0b7608c9175a1e69f0222653af467c125`.
- G20 desired commit `f45c6566521c65da38a8f46a987c54bc468e2dbb` is an ancestor of fresh `main`.
- Desired tree contains six mode-`160000` entries: `SWE-bench`, `nexus-mempalace`, `nexus-rust-v16`, `notebooklm-py-audit`, `packages/core`, and `repro/astropy__astropy-13398/astropy`.
- Rollback predecessor `3d28fa7b65df30e207e53de7caadf93a2b7a8fc0` resolves locally to the expected tree but is not an ancestor of fresh `main`.
- Existing durable operation `op_617dd8acf9f031b2` previously failed with `R1 Gitlink is forbidden`; it remains historical failed/reconciliation evidence and is not mutation authority for this delta.

External design references are supporting context only: Git submodules/gitlinks are independent repositories and are not recursively populated without explicit submodule actions; OSTree/Nix/Guix bind rollback to immutable revision identity; Git bundles provide immutable offline object transport; SLSA/TUF and RIFL/idempotency patterns support identity-bound provenance and same-operation replay only when semantics/parameters remain unchanged.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness | Status | Limitation |
|---|---|---|---|---|---|---|
| `DEC-001` | Owner decision | Exact commit/tree-bound Gitlinks may exist as inert metadata; they must never be recursively fetched, materialized as nested repos, traversed for source authority, imported, or executed. | Owner decision in current G20 continuation | 2026-09-03 | BINDING | Source/runtime proof still required. |
| `DEC-002` | Owner decision | Exact rollback predecessor `3d28fa7b...` remains authoritative even though it is not a fresh-main ancestor; it must be reconstructable from an immutable authority-bound artifact. | Owner decision in current G20 continuation | 2026-09-03 | BINDING | Artifact is not yet issued/materialized. |
| `DEC-003` | Owner decision | Old R2 receipt/request/fence/op remain immutable historical evidence; changed manager/Card semantics require successor recovery authority and a new request/fence/op. | Owner decision in current G20 continuation | 2026-09-03 | BINDING | Successor authority is explicitly out of this source Candidate. |
| `CUR-001` | Current fact | `_r1_reject_gitlinks()` blanket-rejects any mode `160000` tree entry. | `scripts/ops/mcp_gateway_durable.py` at `1583a729...` | exact base | EVIDENCE | Candidate may change it. |
| `CUR-002` | Current fact | `_prepare_recovery_source()` requires accepted/desired/predecessor to be ancestors of fresh main. | same | exact base | EVIDENCE | Candidate may change it. |
| `CUR-003` | Current fact | desired `f45c656...` contains six Gitlinks and is fresh-main ancestry-compatible. | Git object evidence | exact base | EVIDENCE | Gitlink content itself is not source authority. |
| `CUR-004` | Current fact | predecessor `3d28fa7...` has expected tree and is not fresh-main ancestry-compatible. | Git object evidence | exact base | EVIDENCE | Remote/public provenance is not assumed. |
| `CON-001` | Canonical contract | R1 remains fail-closed, caller cannot select root/ref/path/network/follow-main, both desired and rollback bytes must be proven before effect, and no second process/effect authority may be introduced. | existing Task 09 + Issue #526 | current baseline | BINDING | Only named clauses are superseded. |
| `DER-001` | Derivation | Exact superproject commit/tree already binds Gitlink path and OID; a second six-path allowlist would duplicate authority. | `DEC-001 + CUR-003 + Git object model` | current | EVIDENCE | Requires negative tests against materialization/substitution. |
| `DER-002` | Derivation | Rollback correctness depends on exact reconstructable bytes/provenance/retention, not branch ancestry. | `DEC-002 + CUR-004` | current | EVIDENCE | Artifact contract must bind physical bytes. |
| `REJ-001` | Rejected | Hard-code the currently observed six Gitlink paths as an allowlist. | Owner-confirmed design review | 2026-09-03 | REJECTED | Would create a second SSOT. |
| `REJ-002` | Rejected | Reuse `op_617dd8acf9f031b2` after manager/Card semantics change. | `DEC-003` | 2026-09-03 | REJECTED | Violates receipt/request identity binding. |

## 5. Current verified state

The source implementation is repository-integrated but host/runtime G20 closure is not proven. R1 fails before staging on legitimate Gitlinks. Independently, even after removing that rejection, the current predecessor ancestry/source rule would reject the exact Owner-selected predecessor. No host recovery effect is authorized by this specification.

## 6. Owner decisions

- `DEC-001`: Gitlinks are exact-tree-bound inert metadata only.
- `DEC-002`: rollback predecessor identity is exact commit/tree plus authority-bound immutable reconstruction artifact, not fresh-main ancestry.
- `DEC-003`: semantic contract changes require successor recovery authority/request/fence/op; old R2 identities are immutable historical evidence.

## 7. Canonical terminology

- **Inert Gitlink:** mode `160000` superproject entry whose path/OID are bound by the exact superproject tree, but whose target repository/content is not fetched, recursively initialized, traversed, imported, or executed by R1.
- **Predecessor reconstruction artifact:** manager-fixed, caller-unselectable, self-contained Git object artifact bound by successor recovery authority to exact byte SHA-256/size and exact predecessor commit/tree, retained through the recovery authority lifetime and unresolved recovery state.
- **Successor recovery identity:** a new recovery authority/receipt/request/idempotency fence/durable operation created only after the changed Card/manager Candidate is independently accepted.

## 8. Change delta

**Mode: BROWNFIELD**

### MODIFIED — R1 Gitlink rule

**From:** any mode `160000` entry causes immediate `R1 Gitlink is forbidden` failure.

**To:** exact-tree-bound Gitlinks SHALL be accepted only as inert superproject metadata. R1 SHALL NOT invoke submodule init/update/fetch/recurse, SHALL NOT resolve Gitlink target bytes as source authority, and SHALL verify each materialized deployment contains no populated/substituted nested repository at Gitlink paths. Missing or empty inert paths are allowed; populated content, symlink escape, nested `.git`, or other substitution fails closed.

**Impact:** security-sensitive behavioral change; fail-closed boundary is preserved by replacing mode-based rejection with effect/materialization-based rejection.

### MODIFIED — predecessor source rule

**From:** predecessor commit must exist in the fixed fresh-main authority mirror and be an ancestor of fresh main.

**To:** accepted and desired source remain bound to the fixed fresh-main authority mirror. The exact predecessor may be outside fresh-main ancestry only when successor recovery authority binds a self-contained manager-fixed predecessor reconstruction artifact by SHA-256 and byte size plus the same exact predecessor commit/tree. The manager SHALL verify artifact ownership/mode, exact bytes, self-contained Git-bundle integrity, exact single predecessor role/head, object completeness/fsck, and commit/tree identity before constructing the semantic source set or promoting any worktree. Caller-selected path/ref/network/follow-main remains forbidden.

**Impact:** source provenance model changes for predecessor only; desired/current source trust boundary does not broaden.

### MODIFIED — recovery supersession

**From:** same request/fence/op can reconcile the same accepted recovery semantics.

**To:** same request/fence/op remains valid only for byte/semantic-identical authority. A Card hash, manager hash, artifact binding, or recovery security-contract change requires a successor recovery authority and new request/fence/op. Old R2 operation remains historical evidence and SHALL NOT be rewritten or replayed under new semantics.

**Impact:** operational identity change; no host effect in this implementation batch.

## 9. Scope

Included source surfaces:

- recovery contract/schema needed to bind predecessor artifact identity;
- durable manager source preparation/bundle/import/worktree verification;
- focused contract and manager tests;
- exact successor Task Card binding.

## 10. Non-goals

- no host Gateway reload/recovery, LaunchAgent/plist mutation, process effect, OAuth/client effect, or DevSpace recovery action;
- no successor receipt issuance in this Candidate;
- no reuse/cleanup/edit of old R2 ledger or `op_617dd8acf9f031b2`;
- no Gitlink target repository validation or code execution;
- no hard-coded current six-path Gitlink allowlist;
- no network fallback or caller-selected preservation ref/path;
- no G21 work.

## 11. Architecture and authority boundaries

`CapabilityPlanner`, Task Cards, independent acceptance, Owner recovery authority, and the fixed durable Gateway manager remain separate authorities. This delta changes only R1 source admissibility/provenance. The predecessor artifact is evidence/byte source only after the successor Owner-issued recovery authority binds its hash/size/commit/tree; it cannot authorize itself.

## 12. Requirements

### REQ-001 — Inert Gitlink acceptance

- **Status:** SETTLED
- **Source:** `DEC-001, CON-001, CUR-003, DER-001`
- **Behavior:** R1 SHALL accept mode `160000` entries in an exact bound superproject commit/tree without recursively materializing or trusting the target repository.
- **Failure behavior:** populated/substituted/symlinked/nested-repository Gitlink paths SHALL fail closed before recovery effect.
- **Authority/interface:** durable manager source verification.

### REQ-002 — Exact predecessor artifact reconstruction

- **Status:** SETTLED
- **Source:** `DEC-002, CON-001, CUR-004, DER-002`
- **Behavior:** R1 SHALL reconstruct an out-of-main predecessor only from a fixed manager-owned self-contained Git artifact whose SHA-256/size and exact predecessor commit/tree are bound by successor recovery authority.
- **Failure behavior:** missing, stale, wrong-owner/mode, hash/size-mismatched, prerequisite-dependent, wrong-ref/head, incomplete, or commit/tree-mismatched artifact SHALL block before target promotion/effect.
- **Authority/interface:** recovery authority contract + durable manager.

### REQ-003 — Desired-source trust boundary preserved

- **Status:** SETTLED
- **Source:** `CON-001, DEC-002`
- **Behavior:** accepted/desired source identity SHALL continue to come from the fixed clean fresh-main authority mirror; predecessor artifact support SHALL NOT become a generic source/ref/path selector or network fallback.
- **Failure behavior:** caller-selected source/ref/path or fresh-main/desired drift SHALL fail closed.

### REQ-004 — Successor recovery identity

- **Status:** SETTLED
- **Source:** `DEC-003`
- **Behavior:** the changed Card/manager/artifact-binding contract SHALL invalidate old R2 recovery authority for new execution; later host recovery requires a successor receipt/request/fence/op.
- **Failure behavior:** old authority/request identity presented to the changed manager SHALL not authorize new recovery semantics.

## 13. Verification seam

Highest seam in this batch is exact Candidate source + deterministic contract/manager tests. Required falsification includes legitimate Gitlink positive coverage, nested-repo/materialization tamper, side-branch predecessor positive reconstruction, artifact hash/size/ref/prerequisite/object tamper, mirror/desired drift, and old-authority incompatibility. Host runtime remains outside this batch.

## 14. Acceptance criteria

### AC-001 — Legitimate Gitlinks no longer false-block
- **Requirement:** `REQ-001`
- **Evidence level:** FIXTURE
- **Verification seam:** real temporary Git superproject + detached worktree staging
- **Pass:** exact commit/tree with one or more mode `160000` entries stages desired/predecessor while Gitlink targets remain absent/empty and untrusted.
- **Negative control:** create populated/nested `.git` or symlink substitution at a Gitlink path; worktree verification rejects it.
- **Fail:** blanket Gitlink rejection remains or target content is traversed/materialized.

### AC-002 — Side-branch predecessor reconstructs from authority-bound artifact
- **Requirement:** `REQ-002, REQ-003`
- **Evidence level:** FIXTURE
- **Verification seam:** mirror lacking predecessor + self-contained predecessor bundle
- **Pass:** exact non-main predecessor reconstructs and fsck/commit/tree/entrypoint identity matches while accepted/desired remain mirror-bound.
- **Negative control:** missing/tampered/wrong-size/wrong-ref/prerequisite-dependent/incomplete artifact blocks before promotion/effect.
- **Fail:** predecessor still requires fresh-main ancestry or generic external source selection becomes possible.

### AC-003 — Recovery identity supersession is enforced
- **Requirement:** `REQ-004`
- **Evidence level:** STATIC + FIXTURE
- **Verification seam:** changed Card hash/manager hash and recovery authority validation
- **Pass:** new source contract requires successor authority binding including predecessor artifact; old R2 receipt/request cannot authorize changed manager semantics.
- **Negative control:** attempt to self-rehash/substitute old authority or omit artifact binding fails closed.
- **Fail:** same old request/fence/op can be repurposed after contract change.

### AC-004 — Existing R1 invariants remain green
- **Requirement:** `REQ-001, REQ-002, REQ-003, REQ-004`
- **Evidence level:** FIXTURE
- **Verification seam:** full affected contract/manager suite + `git diff --check`
- **Pass:** all affected tests pass on the exact Candidate and changed paths are within the Task Card scope.
- **Negative control:** retain existing caller-selected path/ref/network, CAS, symlink, wrong-owner/mode, lost-ack, and zero-effect failure tests.
- **Fail:** regression or out-of-scope mutation.

## 15. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence | Claim ceiling | Task-card group |
|---|---|---|---|---|---|---|
| `REQ-001` | `DEC-001, CON-001, CUR-003` | MODIFIED Gitlink rule | `AC-001, AC-004` | FIXTURE | Candidate source only | R1 source repair |
| `REQ-002` | `DEC-002, CON-001, CUR-004` | MODIFIED predecessor rule | `AC-002, AC-004` | FIXTURE | Candidate source only | R1 source repair |
| `REQ-003` | `CON-001, DEC-002` | MODIFIED predecessor provenance | `AC-002, AC-004` | FIXTURE | Candidate source only | R1 source repair |
| `REQ-004` | `DEC-003` | MODIFIED recovery identity | `AC-003, AC-004` | STATIC/FIXTURE | successor-authority readiness only | R1 source repair |

## 16. Evidence and claim ceiling

Passing this specification's acceptance proves only that an exact R1 source Candidate implements the settled contract under deterministic tests. It does not prove GitHub integration, installed manager identity, successor authority issuance, Gateway recovery, G20 runtime Task I/J/K, OFF/ON causality, restart, rollback, or final G20 closure.

## 17. Rollback and failure handling

No host effect is performed in this batch. Candidate rejection leaves current main and old R2 evidence unchanged. Old recovery operation/state is never edited. Missing predecessor artifact evidence is a zero-effect block, not a reason to fall back to fresh-main ancestry, network fetch, caller refs, or manual state edits.

## 18. Risks and unknowns

- Exact predecessor artifact bytes are intentionally not produced by this source Candidate; successor authority issuance must bind and retain them before recovery.
- Git worktree behavior for inert Gitlink paths must be tested on the supported host Git version rather than assumed.
- Current live Gateway remains bound to an older source realm; this does not affect source Candidate acceptance but prevents runtime G20 claims.

## 19. Unresolved owner decisions

none

## 20. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope | Minimum profile | Blocker |
|---|---|---|---|---|---|---|---|---|---|
| R1 source repair | `REQ-001..004` | `AC-001..004` | exact Candidate safely supports inert Gitlinks and authority-bound side-branch predecessor artifact while forcing successor recovery identity | this spec + current main | affected pytest + diff/scope review + independent Candidate acceptance | `R1_SOURCE_CANDIDATE_ACCEPTED` | medium | CANDIDATE | none before implementation |

## 21. Out of scope

Successor recovery receipt/request/fence/op issuance, host recovery, Gateway adoption, runtime G20 witnesses, integration/merge, release, and G21.

## 22. Supersession and change history

2026-09-03: Owner accepted A+B+C after external pattern review. This specification supersedes only the three named R1 assumptions; all existing fail-closed, fixed-manager, no-caller-source, no-network/follow-main, pre-effect rollback-readiness, durable ledger, reconcile, and authority-separation requirements remain binding.
