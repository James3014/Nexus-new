# TASK-001 — Verify and integrate the read-only Repository Intelligence PR sidecar

- **Campaign:** `CAMPAIGN-RIE-PR-SIDECAR-20260915`
- **Status:** `PLANNED`
- **Source spec:** `none`
- **Source spec SHA-256:** `none`
- **Source groups:** `ISSUE-969-RIE-SIDECAR`
- **Requirements:** `REQ-969`
- **Acceptance:** `AC-9691`; `AC-9692`; `AC-9693`; `AC-9694`; `AC-9695`; `AC-9696`; `AC-9697`; `AC-9698`
- **Auto-chain:** `false`
- **Maximum claim:** `NEXUS_NEW_RIE_READ_ONLY_PR_SIDECAR_INTEGRATED`
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

The exact governed PR candidate is independently verified and eligible to enter the repository's protected-merge gate without expanding RIE authority.

## Non-goals

- No Repository Intelligence implementation change.
- No new CI, verification, acceptance, Planner, Router, workforce, merge, release, deployment or runtime authority.
- No required-check or branch-protection change.
- No PR comment/approval/merge authority from RIE itself.
- No checkout or execution of pull-request code by RIE.
- No direct push or force-push to `main`.
- No runtime activation or production-safety claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `REQ-969` | bounded Issue #969 requirement | adopt only the canonical read-only RIE sidecar and inert governance artifacts |
| `AC-9691` | scope witness | exact changed-path set remains bounded and deletion-free |
| `AC-9692` | workflow-authority witness | read-only permissions and immutable `v0.1.1` action ref |
| `AC-9693` | identity-freshness witness | exact PR head/base/current-main must be rebound before acceptance and merge |
| `AC-9694` | CI witness | applicable existing CI must be terminal-success on the exact integration subject |
| `AC-9695` | RIE evidence witness | final-head RIE artifact remains structurally/hash valid and `ADVISORY_EVIDENCE_ONLY` |
| `AC-9696` | independent-review witness | reviewer must be independent of Candidate creation and bound to exact final Candidate |
| `AC-9697` | merge-authority witness | protected merge requires current standing grant, fresh completion host, exact-head/CAS and no bypass |
| `AC-9698` | post-merge witness | accepted workflow and governance artifacts must be read back from new `main` |
| `DEC-9691` | Owner decision | adopt RIE as an advisory PR evidence sidecar |
| `DEC-9692` | Owner decision | preserve existing CI and merge authority; RIE is not a merge verdict |
| `DEC-9693` | Owner decision | permit only inert Task Card/INDEX artifacts in addition to the workflow |
| `DEC-9694` | Owner decision | independent acceptance and protected merge remain separate gates |

## Owner decisions

- `DEC-9691`: adopt RIE as a read-only advisory PR evidence sidecar in Nexus-new.
- `DEC-9692`: preserve existing CI and merge authority; do not make RIE a required merge verdict in this change.
- `DEC-9693`: allow only inert Task Card/INDEX artifacts in addition to the workflow so the existing PR can satisfy Nexus-new governance without creating a second implementation PR.
- `DEC-9694`: protected merge remains a separate gate requiring independent acceptance, fresh identity/check evidence, current standing-grant authority and post-merge readback.

## Source and start state

- **Workspace/root:** `James3014/Nexus-new`
- **Branch:** `chore/repository-intelligence-g1-20260915`
- **Starting HEAD:** `32bc3b6844c24fc4ed9be691ce55674a27aab6ae`
- **Dirty baseline:** `remote-branch-no-local-dirty-input`
- **Required initial verification:** re-read Issue #969, PR #968, current GitHub `main`, changed paths, exact workflow bytes and final PR head before acceptance.
- **Freshness rule:** re-read PR head/base, current GitHub `main`, required checks, review state and completion-host source immediately before protected merge. Any drift invalidates prior merge eligibility.

## MCP execution profile

- **App/server and action snapshot:** GitHub connector plus Nexus protected completion surface; identities are rebound at use time.
- **Exact required actions:** `get_pr_info`; `list_pr_changed_filenames`; `fetch_pr_patch`; `fetch_commit_workflow_runs`; `fetch_workflow_run_artifacts`; `github_complete_pull_request`
- **Confirmation-required actions:** `github_complete_pull_request`
- **Idempotency and attempt rule:** every mutation is bound to exact expected head/base; after an unknown merge outcome, reconcile PR/main before any further mutation.
- **Reconnect reconciliation:** re-read PR merged state, exact `main`, accepted paths and current standing-grant state before retrying any external effect.
- **Transport blocker:** `none`

## Authority map

- **Selection authority:** Issue #969 plus Owner decisions; no Planner/Router authority is created.
- **Execution authority:** primary coordinator may perform only the bounded tracked Candidate actions separately authorized by the Owner and Issue contract.
- **Verification authority:** exact GitHub source/CI/RIE evidence plus an independent reviewer; Candidate creator/self-report is insufficient.
- **Receipt authority:** GitHub exact revision/check/artifact identities and repository-governed acceptance/standing-grant receipts.
- **Approval/integration authority:** independent acceptance does not merge; protected merge remains the primary coordinator under a valid exact Owner standing grant and current completion gates.

## Allowed scope

- **Read:** `AGENTS.md`; `.github/workflows/repository-intelligence.yml`; `tasks/rie-pr-sidecar-20260915/INDEX.md`; `tasks/rie-pr-sidecar-20260915/TASK-001.md`
- **Edit:** `none`
- **Create:** `.github/workflows/repository-intelligence.yml`; `tasks/rie-pr-sidecar-20260915/INDEX.md`; `tasks/rie-pr-sidecar-20260915/TASK-001.md`
- **Delete:** `none`
- **Maximum touched production files:** `3`
- **Maximum touched test files:** `0`

## Unknown scan

- **Known facts:** original #968 canary workflow succeeded and produced a valid advisory artifact; seven sibling repos merged the same pattern; GitHub main matched #968 base before governance artifacts were appended.
- **Assumptions requiring verification:** final head still contains byte-equivalent accepted workflow semantics; exact-head normal CI and RIE reruns succeed after Task Card/INDEX commits; no review blocker appears; completion host is current when the merge gate is attempted.
- **Architecture risks:** treating RIE workflow success as merge readiness; creating a second CI/acceptance authority; stale base or completion-host identity.
- **Evidence risks:** early RIE snapshot may precede terminal CI; original-head artifacts cannot prove the new final head; the Nexus completion host was previously observed on source `6d1e32216434bdda7930c0cf21921209d9243c6d` while GitHub `main` was `68d8b5408f3d4fe60a701d9c79ccd6a2129549c5`, so merge-time freshness must be re-proved; stale standing grants must never be reused.
- **Missing owner decision:** `none`

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

No product defect is claimed. The existing guard is the Nexus-new governance requirement that a protected merge cannot be justified by a green workflow alone. Prior Wave 1 evidence proved the original canary works; this task must prove the final governed Candidate preserves workflow semantics and satisfies independent acceptance/merge gates.

## Implementation constraints

- Preserve the existing workflow content unless verification finds a real contract violation.
- Governance artifacts are inert evidence/authority-binding documents only; they must not be loaded as runtime configuration.
- Keep `repository-intelligence-engine` as the sole implementation owner.
- Keep RIE `ADVISORY_EVIDENCE_ONLY`; do not map its success/check conclusion to acceptance or merge approval.
- Do not invent Issue, Task, Candidate, verifier or acceptance hashes. Derive all material identities from actual artifacts/evidence.
- Do not bypass a stale completion host, missing standing grant, nonterminal CI, head/base drift or independent-review gap.

## GREEN and regression gates

- `AC-9691`: exact changed-path set is the workflow plus two governance artifacts, with no deletions.
- `AC-9692`: workflow permissions remain read-only and action ref remains `James3014/repository-intelligence-engine@v0.1.1`.
- `AC-9693`: final PR head/base/current-main identities are fresh and mutually consistent at acceptance/merge time.
- `AC-9694`: applicable existing CI is terminal-success on the exact final integration subject.
- `AC-9695`: final-head RIE artifact is structurally/hash valid, complete as collected, and claim ceiling is `ADVISORY_EVIDENCE_ONLY`.
- `AC-9696`: independent review accepts scope, semantics, evidence and authority boundaries for the exact final Candidate.
- `AC-9697`: protected merge executes only after fresh standing-grant, completion-host and expected-head/CAS gates pass.
- `AC-9698`: post-merge `main` readback confirms accepted workflow and governance artifact bytes/semantics.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | `TARGET_ROOT` | `git diff --check` | verify patch whitespace integrity on an exact Candidate checkout | exit code `0` |

## Physical evidence

Record at minimum:

- Issue #969 observed state/update identity;
- PR #968 exact final head/base/current-main;
- changed path set and exact patch/workflow bytes;
- exact-head workflow/check run IDs and terminal conclusions;
- RIE artifact ID/digest plus report review identity/content hash/claim ceiling/completeness;
- independent reviewer identity and acceptance bound to the exact candidate head/tree/diff/card/contract evidence;
- standing-grant receipt hash/action/Goal/coordinator/repository/expiry/revocation state at merge time;
- protected merge result plus expected head/base;
- post-merge `main` SHA and readback of all accepted paths.

## Independent review

A fresh reviewer that did not create the final Candidate must inspect the exact Issue/Card/INDEX, PR diff, workflow semantics, final-head CI/RIE evidence, scope/deletion set, canonical-owner boundary, claim ceiling and merge authority boundary. Acceptance must be bound to the exact final Candidate revision; prior Wave 1 review cannot be silently reused after head movement.

## Exit conditions

- **PASS:** final Candidate is independently accepted; protected merge gates pass; merge completes without head/base substitution; accepted paths are read back from new `main`; Issue #969 can be reconciled as completed at the source-integration claim ceiling.
- **BLOCK:** unexpected path/deletion; workflow authority broadening; stale/moved head/base without requalification; missing/nonterminal/failed required checks; invalid/incomplete RIE artifact where required; independent acceptance missing; standing grant invalid/expired/revoked/out-of-scope; completion host stale/dirty/unbound; unknown merge outcome not reconciled.
- **Residual debt:** terminal post-CI RIE snapshot and automatic Nexus consumption remain separate future design gates.
- **Next gate:** rebind the final #968 head, verify exact-head evidence, then run independent Candidate acceptance. Informational only; `AUTO_CHAIN=false` remains authoritative.
