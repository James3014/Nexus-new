# TASK-001 — Verify and integrate the read-only Repository Intelligence PR sidecar

- **Campaign:** `CAMPAIGN-RIE-PR-SIDECAR-20260915`
- **Status:** `ACTIVE`
- **Source spec:** `none`
- **Source spec SHA-256:** `none`
- **Source groups:** `ISSUE-969-RIE-SIDECAR`
- **Requirements:** `REQ-969-1`
- **Acceptance:** `AC-969-1`; `AC-969-2`; `AC-969-3`; `AC-969-4`; `AC-969-5`; `AC-969-6`; `AC-969-7`; `AC-969-8`
- **Auto-chain:** `false`
- **Maximum claim:** before merge `NEXUS_NEW_RIE_READ_ONLY_PR_SIDECAR_CANDIDATE_VERIFIED`; after independently accepted protected merge + readback `NEXUS_NEW_RIE_READ_ONLY_PR_SIDECAR_INTEGRATED`
- **Depends on:** `none`
- **Dependency unlock evidence:** `none`
- **Task type:** `INTEGRATION_VERIFY`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `small`
- **Execution lane:** `DIRECT_TYPED_ACTIONS`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Bind existing PR #968 to Ready Issue #969 and verify the exact final Candidate for the canonical immutable `James3014/repository-intelligence-engine@v0.1.1` read-only pull-request evidence sidecar. Reuse the already-proven workflow; do not redesign or broaden Repository Intelligence.

## Observable outcome

A reviewable exact-head Candidate contains only the RIE workflow plus this Task Card and its campaign INDEX; the workflow produces `ADVISORY_EVIDENCE_ONLY` evidence on the exact final head, existing Nexus-new CI remains separate and terminal-success, an independent reviewer accepts the bounded Candidate, and only then may the repository's protected merge path integrate it and read back `main`.

## Non-goals

- No Repository Intelligence implementation change.
- No new CI, verification, acceptance, Planner, Router, workforce, merge, release, deployment or runtime authority.
- No required-check or branch-protection change.
- No PR comment/approval/merge authority from RIE itself.
- No checkout or execution of pull-request code by RIE.
- No direct push/force-push to `main`.
- No runtime activation or production-safety claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `ISSUE-969` | bounded owner contract | exactly the workflow plus inert governance artifacts; `AUTO_CHAIN=false`; maximum claim bounded to source/default-branch integration |
| `PR-968` | existing implementation Candidate | preserve canonical workflow semantics; final head must be rebound after governance artifacts are appended |
| `ISSUE-912` | parent consumer-integration tracker | remains parent/index only; this card does not broaden or replace it |
| `RIE-v0.1.1` | canonical dependency | immutable read-only advisory engine remains owned by `James3014/repository-intelligence-engine` |

## Owner decisions

- `DEC-969-1`: adopt RIE as a read-only advisory PR evidence sidecar in Nexus-new.
- `DEC-969-2`: preserve existing CI and merge authority; do not make RIE a required merge verdict in this change.
- `DEC-969-3`: allow only inert Task Card/INDEX artifacts in addition to the workflow so the existing PR can satisfy Nexus-new governance without creating a second implementation PR.
- `DEC-969-4`: protected merge remains a separate gate requiring independent acceptance, fresh identity/check evidence, current standing-grant authority and post-merge readback.

## Source and start state

- **Workspace/root:** GitHub collaboration repository `James3014/Nexus-new`; physical completion host must be rebound separately before merge.
- **Branch:** `chore/repository-intelligence-g1-20260915`
- **Starting HEAD:** original canary head `32bc3b6844c24fc4ed9be691ce55674a27aab6ae`; final Candidate head is the branch head after tracked governance artifacts are appended and must be re-read.
- **Dirty baseline:** remote GitHub branch; local dirty state is not mutation input.
- **Required initial verification:** re-read Issue #969, PR #968, current GitHub `main`, changed paths, exact workflow bytes and final PR head before acceptance.
- **Freshness rule:** re-read PR head/base, current GitHub `main`, required checks, review state and completion-host source immediately before protected merge. Any drift invalidates prior merge eligibility.

## MCP execution profile

- **App/server and action snapshot:** GitHub connector + Nexus protected completion surface, both rebound at use time.
- **Exact required actions:** GitHub PR/head/base/diff reads; exact-head workflow/check/artifact reads; independent acceptance audit; `nexus.github_complete_pull_request` for ordinary protected completion when its canonical source is fresh.
- **Confirmation-required actions:** protected merge requires explicit Owner confirmation plus a valid current `GITHUB_MERGE` standing-grant receipt.
- **Idempotency and attempt rule:** every mutation is bound to exact expected head/base; no blind retry after unknown merge outcome; reconcile remote PR/main state first.
- **Reconnect reconciliation:** after transport uncertainty, re-read PR merged state, exact `main`, and accepted paths before any further mutation.
- **Transport blocker:** as observed before this card was appended, the live Nexus completion source reported commit `6d1e32216434bdda7930c0cf21921209d9243c6d` while GitHub `main` was `68d8b5408f3d4fe60a701d9c79ccd6a2129549c5`. Final protected completion must fail closed until the bound completion host proves current GitHub-main source identity.

## Authority map

- **Selection authority:** Issue #969 + Owner decisions; no Planner/Router involvement is created.
- **Execution authority:** primary coordinator may perform the bounded tracked candidate mutations explicitly authorized by the Owner and Issue contract.
- **Verification authority:** exact GitHub source/CI/RIE evidence plus independent reviewer evidence; worker/self-report is insufficient.
- **Receipt authority:** GitHub exact revision/check/artifact identities and repository-governed acceptance/standing-grant receipts.
- **Approval/integration authority:** independent acceptance does not merge; protected merge remains the primary coordinator under a valid exact Owner standing grant and current completion gates.

## Allowed scope

- **Read:** Issue #969; #912; PR #968; current `main`; `.github/workflows/repository-intelligence.yml`; `tasks/rie-pr-sidecar-20260915/*`; exact-head checks/artifacts; repository governance instructions.
- **Edit:** `tasks/rie-pr-sidecar-20260915/INDEX.md`; `tasks/rie-pr-sidecar-20260915/TASK-001.md` only for evidence-bound contract corrections before acceptance.
- **Create:** `tasks/rie-pr-sidecar-20260915/INDEX.md`; `tasks/rie-pr-sidecar-20260915/TASK-001.md`.
- **Delete:** `none`.
- **Maximum touched production files:** `1` (`.github/workflows/repository-intelligence.yml`, already implemented before this card).
- **Maximum touched test files:** `0`.

## Unknown scan

- **Known facts:** original #968 canary workflow succeeded and produced a valid advisory artifact; seven sibling repos merged the same pattern; GitHub main matched #968 base before governance artifacts were appended.
- **Assumptions requiring verification:** final head still contains byte-equivalent accepted workflow semantics; exact-head normal CI and RIE reruns succeed after Task Card/INDEX commits; no review/blocker appears; completion host is rebound to current GitHub main before merge.
- **Architecture risks:** accidentally treating RIE workflow success as merge readiness; accidentally creating a second CI/acceptance authority; stale base/host source identity.
- **Evidence risks:** early RIE snapshot may precede terminal CI; old original-head artifacts cannot prove the new final head; stale standing grant must never be reused.
- **Missing owner decision:** `none` for this bounded candidate/acceptance continuation. A fresh merge receipt still must be materialized at the merge gate.

## Mandatory source audit

Before acceptance, verify:

1. root `AGENTS.md` protected-merge contract and current operating-mode constraints;
2. Issue #969 exact body/state and parent #912 relationship;
3. PR #968 final exact changed paths and patch;
4. current GitHub `main` and PR base/head identity;
5. `repository-intelligence-engine@v0.1.1` release immutability/ref binding already established by Wave 1, with no stronger claim inferred;
6. final-head RIE run/artifact envelope and evidence completeness;
7. all applicable existing Nexus-new CI on the exact final head;
8. no duplicate authority or unexpected deletions;
9. completion-host source identity and standing-grant validity immediately before merge.

## Start-state classification

`PROOF_ONLY_NO_DEFECT_CLAIM`

## RED or existing-guard proof

No product defect is claimed. The existing guard is the Nexus-new governance requirement that a protected merge cannot be justified by a green workflow alone. Prior Wave 1 evidence proved the original canary works; this task must prove the final governed Candidate remains semantically identical in workflow behavior and satisfies independent acceptance/merge gates.

## Implementation constraints

- Preserve the existing workflow content unless verification finds a real contract violation.
- Governance artifacts are inert evidence/authority-binding documents only; they must not be loaded as runtime configuration.
- Keep `repository-intelligence-engine` as the sole implementation owner.
- Keep RIE `ADVISORY_EVIDENCE_ONLY`; do not map its success/check conclusion to acceptance or merge approval.
- Do not invent Issue, Task, Candidate, verifier or acceptance hashes. Derive all material identities from actual artifacts/evidence.
- Do not bypass a stale completion host, missing standing grant, nonterminal CI, head/base drift or independent-review gap.

## GREEN and regression gates

- `AC-969-1`: exact changed-path set is the workflow + two governance artifacts, no deletions.
- `AC-969-2`: workflow permissions remain read-only and action ref remains `James3014/repository-intelligence-engine@v0.1.1`.
- `AC-969-3`: final PR head/base/current-main identities are fresh and mutually consistent at acceptance/merge time.
- `AC-969-4`: applicable existing CI is terminal-success on the exact final integration subject.
- `AC-969-5`: final-head RIE artifact is structurally/hash valid, complete as collected, and claim ceiling is `ADVISORY_EVIDENCE_ONLY`.
- `AC-969-6`: independent review accepts scope, semantics, evidence and authority boundaries for the exact final Candidate.
- `AC-969-7`: protected merge executes only after fresh standing-grant + completion-host + expected-head/CAS gates pass.
- `AC-969-8`: post-merge `main` readback confirms accepted workflow and governance artifact bytes/semantics.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | `not applicable` | typed GitHub/Nexus actions only; no shell command is required to validate or merge this remote-only Candidate | preserve bounded typed mutation/read path | exact API/tool results are recorded; no unverified shell-side mutation |

## Physical evidence

Record at minimum:

- Issue #969 observed state/update identity;
- PR #968 exact final head/base/current-main;
- changed path set and exact patch/workflow bytes;
- exact-head workflow/check run IDs and terminal conclusions;
- RIE artifact ID/digest + report review identity/content hash/claim ceiling/completeness;
- independent reviewer identity and acceptance bound to the exact candidate head/tree/diff/card/contract evidence;
- standing-grant receipt hash/action/Goal/coordinator/repository/expiry/revocation state at merge time;
- protected merge result + expected head/base;
- post-merge `main` SHA and readback of all accepted paths.

## Independent review

A fresh reviewer that did not create the final Candidate must inspect the exact Issue/Card/INDEX, PR diff, workflow semantics, final-head CI/RIE evidence, scope/deletion set, canonical-owner boundary, claim ceiling and merge authority boundary. Acceptance must be bound to the exact final Candidate revision; prior Wave 1 review cannot be silently reused after head movement.

## Exit conditions

- **PASS:** final Candidate is independently accepted; protected merge gates pass; merge completes without head/base substitution; accepted paths are read back from new `main`; Issue #969 can be reconciled as completed at the source-integration claim ceiling.
- **BLOCK:** unexpected path/deletion; workflow authority broadening; stale/moved head/base without requalification; missing/nonterminal/failed required checks; invalid/incomplete RIE artifact where required; independent acceptance missing; standing grant invalid/expired/revoked/out-of-scope; completion host stale/dirty/unbound; unknown merge outcome not reconciled.
- **Residual debt:** terminal post-CI RIE snapshot and automatic Nexus consumption remain separate future design gates.
- **Next gate:** rebind final #968 head after this card/INDEX commit, verify exact-head evidence, then run independent Candidate acceptance. Informational only; `AUTO_CHAIN=false` remains authoritative.
