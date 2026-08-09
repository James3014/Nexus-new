# TASK-OPENWIKI-INTEGRATION-PILOT-01 — OpenWiki canonical integration pilot scaffold

- task_id: `TASK-OPENWIKI-INTEGRATION-PILOT-01`
- **Campaign:** `CAMPAIGN-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- status: `RETAINED_FOR_REVIEW`
- **Source spec:** `SPEC-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- **Source spec SHA-256:** `f07c242de66a8eb5a0c5b904c282cb03cb5b5a6678247ff4a5a7cdc13557d9e1`
- **Source groups:** `OPENWIKI-PILOT-SCAFFOLD`
- **Requirements:** `REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006`
- **Acceptance:** `AC-001; AC-002; AC-003; AC-004; AC-005; AC-006`
- **Auto-chain:** `false`
- **Maximum claim:** `OPENWIKI_PILOT_SCAFFOLD_PHYSICALLY_PRESENT_ACCEPTANCE_UNPROVEN`
- **Depends on:** `none`
- **Dependency unlock evidence:** `none`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `small`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `OPENWIKI-INTEGRATION-PILOT-01`

## Goal

Create the bounded OpenWiki pilot scaffold without executing OpenWiki or integrating generated documentation.

## Observable outcome

Repository contains a manual-only, read-only OpenWiki pilot scaffold with V3 classification and fail-closed side-effect boundaries, without generated Wiki integration.

For the current reconciliation, this observable outcome is a physical-state
observation only. It is not acceptance, closure, canary, approval, integration,
release, or production/public readiness evidence.

## Non-goals

Do not run OpenWiki against canonical during implementation.

Do not create generated Wiki pages.

Do not modify `nexus_wiki_vault/`, `AGENTS.md`, `CLAUDE.md`, `MUSE_PROTO.md`, model-workforce policy, Nexus runtime/lifecycle code, or any file outside the three allowed implementation paths.

Do not approve, integrate, push, release, clean up, or auto-chain.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
| --- | --- | --- |
| REQ-001 | Derived authority contract | OpenWiki output stays derived and non-authoritative |
| REQ-002 | V3 classification contract | Six evidence/authority axes remain distinct |
| REQ-003 | Read-boundary contract | Governance/planning/runtime noise is excluded without hiding implementation roots |
| REQ-004 | Workflow contract | Manual-only, pinned, read-only workflow |
| REQ-005 | Side-effect contract | Root/workflow restoration and fail-closed changed-path checks |
| REQ-006 | Candidate contract | Exactly three implementation files and Owner-only downstream authority |
| AC-001 | Authority acceptance | Detects authority promotion |
| AC-002 | Classification acceptance | Detects missing axes or conflation |
| AC-003 | Ignore acceptance | Detects missing exclusions or overbroad source exclusion |
| AC-004 | Workflow acceptance | Detects trigger, permission, pin, telemetry, secret, or write-path violations |
| AC-005 | Containment acceptance | Detects missing restoration or path guards |
| AC-006 | Scope acceptance | Detects out-of-scope Candidate changes |

## Owner decisions

DEC-001: Governed OpenWiki pilot approved.

DEC-002: Manual Agy handoff is permitted while MCP to Agy dispatch remains unreliable.

DEC-003: ChatGPT owns contract authorship/review; Agy remains bounded Candidate implementer.

## Source and start state

- **Workspace/root:** `/Users/jameschen/Workspace/nexus`
- **Branch:** `nexus/integration/main`
- **Starting HEAD:** `dac6e7279981828ed135f27c1c42449b0a1fd9c7`
- **Dirty baseline:** `clean`
- **Required initial verification:** Re-read canonical root, branch, HEAD, dirty state, the exact source Spec SHA, Task Card bytes, and all mandatory source-audit paths immediately before implementation.
- **Freshness rule:** A newer canonical HEAD is permitted only after re-reading the mandatory source-audit paths and proving that no relevant authority, allowed implementation path, or contract assumption changed; otherwise stop and rebind the Task Card before mutation.

## Issue #11 reconciliation state

- **Disposition:** `RETAINED_FOR_REVIEW`; do not mark this card `COMPLETED`.
- **Physical scaffold:** The three historical implementation paths are
  physically present in the current tree: `.openwikiignore`,
  `openwiki/INSTRUCTIONS.md`, and `.github/workflows/openwiki-update.yml`.
- **Missing historical evidence:** No bound AC-001 through AC-006 validator
  output, exact Candidate commit/tree receipt, independent acceptance/closure
  receipt, or manual canary receipt is available in the current task evidence
  surface.
- **Claim boundary:** The physical scaffold can be recorded as present, but
  that presence cannot be promoted to acceptance, closure, canary success,
  approval, integration, release, or production/public readiness.
- **Reconcile edit scope:** This Owner-directed reconciliation may edit only
  this card and its campaign `INDEX.md`. It does not create, modify, run, or
  integrate the OpenWiki scaffold or generated Wiki content.

## MCP execution profile

- **App/server and action snapshot:** `not applicable`
- **Exact required actions:** `not applicable`
- **Confirmation-required actions:** `none`
- **Idempotency and attempt rule:** `not applicable`
- **Reconnect reconciliation:** `not applicable`
- **Transport blocker:** `none`

## Authority map

- **Selection authority:** Owner-approved Git-tracked Task Card; CapabilityPlanner and HybridRouteDecision remain Nexus route authority.
- **Execution authority:** One bounded isolated Candidate worker using the exact Task Card.
- **Verification authority:** Deterministic static verifiers plus an independent reviewer.
- **Receipt authority:** Exact Candidate commit/tree, source Spec SHA, Task Card SHA, command evidence, and final diff.
- **Approval/integration authority:** James Chen / separate explicit Owner gate only.

## Allowed scope

- **Read:** `AGENTS.md; .github/workflows/benchmark-ci.yml; nexus_wiki_vault/99_Schema/WIKI_GOVERNANCE_CHARTER.md; nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml; tasks/SPEC-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808.md; tasks/openwiki-canonical-integration-pilot-20260808/INDEX.md; tasks/openwiki-canonical-integration-pilot-20260808/00-OPENWIKI-INTEGRATION-PILOT-01.md`
- **Edit:** `none`
- **Create:** `.openwikiignore; openwiki/INSTRUCTIONS.md; .github/workflows/openwiki-update.yml`
- **Delete:** `none`
- **Maximum touched production files:** `3`
- **Maximum touched test files:** `0`

## Unknown scan (reconciled)

- **Known facts:** The three implementation paths are physically present in the
  current tree; repository governance, Wiki authority, and the existing
  GEMINI_API_KEY convention are identified.
- **Assumptions requiring verification:** OpenWiki 0.3.1 remains installable and operational only at later canary time; implementation does not claim provider availability.
- **Architecture risks:** Generated documentation may conflate implementation existence, wiring, runtime surface, and authority if V3 instructions are weakened.
- **Evidence risks:** The current task surface lacks historical AC-001 through
  AC-006 validator output, Candidate/closure receipt, independent acceptance,
  and canary receipt. Static scaffold presence proves neither acceptance nor
  OpenWiki output quality or GitHub Actions runtime success.
- **Missing owner decision:** `none`

## Mandatory source audit

Before mutation, re-read root `AGENTS.md`, the current OpenWiki source Spec, campaign INDEX, active Task Card, Wiki governance charter/authority manifest, and `.github/workflows/benchmark-ci.yml`.

The historical implementation pass required verifying that `.openwikiignore`,
`openwiki/INSTRUCTIONS.md`, and `.github/workflows/openwiki-update.yml` did not
exist before treating them as Create scope. The current reconciliation records
that those paths are now physically present; it does not treat that presence as
acceptance or closure evidence.

If an allowed implementation path already exists or any relevant authority changed, stop rather than silently converting Create scope into Edit scope.

## Start-state classification

RETAINED_FOR_REVIEW

## RED or existing-guard proof

Nexus already has repository authority, route authority, Wiki authority,
Candidate, and Owner-only integration guards. The scaffold is physically
present, but its historical acceptance/closure/canary evidence is missing.
That evidence gap is the retained review condition and is not evidence of a
production defect.

## Implementation constraints

Create exactly the three allowed implementation files.

`.openwikiignore` must include at least:

`nexus_wiki_vault/`
`tasks/`
`.nexus/`
`nexus-evolve`
`MUSE_PROTO.md`
`.antigravitycli/`
`.pyre/`
`docs/incidents/LATEST_RCA.md`

It must not globally exclude:

`nexus/`
`scripts/`
`src/`
`tests/`

`openwiki/INSTRUCTIONS.md` must preserve all six V3 axes:

`implementation_status`
`wiring_status`
`runtime_surfaces`
`authority_roles`
`evidence_basis`
`claim_ceiling`

It must state `authority: derived_non_authoritative`, preserve CapabilityPlanner and HybridRouteDecision route authority, distinguish existence from wiring and wiring from authority, and preserve uncertainty when evidence is insufficient.

The workflow must be `workflow_dispatch` only, use `contents: read`, pin OpenWiki to `0.3.1`, disable telemetry, use `GEMINI_API_KEY`, upload `openwiki/` only as an artifact, restore `AGENTS.md`, `CLAUDE.md`, and its own workflow file from `HEAD`, explicitly guard `nexus_wiki_vault/`, and fail if any remaining changed path is outside `openwiki/`.

No OpenWiki execution is permitted while implementing this Task Card.

## GREEN and regression gates

AC-001 through AC-006 must all be witnessed by the mandatory command manifest and complete Candidate diff.

A worker-authored PASS report does not satisfy the gate without command evidence and independent review. No such historical acceptance/closure receipt is currently available; therefore these gates remain unreconciled.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
| --- | --- | --- | --- | --- |
| C1 | TARGET_ROOT | `git diff --check` | Reject whitespace errors | exit 0 |
| C2 | TARGET_ROOT | `python3 -c "assert all(x in __import__('pathlib').Path('.github/workflows/openwiki-update.yml').read_text() for x in ['workflow_dispatch:','contents: read','openwiki@0.3.1','OPENWIKI_TELEMETRY_DISABLED','GEMINI_API_KEY','actions/upload-artifact@v4'])"` | Verify manual pinned read-only artifact workflow contract | assertion passes |
| C3 | TARGET_ROOT | `python3 -c "assert all(x not in __import__('pathlib').Path('.github/workflows/openwiki-update.yml').read_text() for x in ['schedule:','contents: write','pull-requests: write','permissions: write-all','git push','gh pr create'])"` | Reject schedule, write permission, push, and PR automation | assertion passes |
| C4 | TARGET_ROOT | `python3 -c "assert all(x in __import__('pathlib').Path('.github/workflows/openwiki-update.yml').read_text() for x in ['git restore','AGENTS.md','CLAUDE.md','.github/workflows/openwiki-update.yml','git status --porcelain','nexus_wiki_vault/','openwiki/'])"` | Verify explicit restoration and fail-closed path containment tokens | assertion passes |
| C5 | TARGET_ROOT | `python3 -c "assert all(x in __import__('pathlib').Path('openwiki/INSTRUCTIONS.md').read_text() for x in ['implementation_status','wiring_status','runtime_surfaces','authority_roles','evidence_basis','claim_ceiling','derived_non_authoritative','CapabilityPlanner','HybridRouteDecision'])"` | Verify V3 classification and authority tokens | assertion passes |
| C6 | TARGET_ROOT | `python3 -c "assert all(x in __import__('pathlib').Path('.openwikiignore').read_text() for x in ['nexus_wiki_vault/','tasks/','.nexus/','nexus-evolve','MUSE_PROTO.md','.antigravitycli/','.pyre/','docs/incidents/LATEST_RCA.md'])"` | Verify required ignore boundaries | assertion passes |
| C7 | TARGET_ROOT | `python3 -c "assert all(x not in set(line.strip() for line in __import__('pathlib').Path('.openwikiignore').read_text().splitlines()) for x in ['nexus/','scripts/','src/','tests/'])"` | Reject overbroad exclusion of implementation roots | assertion passes |
| C8 | TARGET_ROOT | `git diff --name-only HEAD^ HEAD` | Verify single-commit Candidate scope | exactly `.openwikiignore`, `.github/workflows/openwiki-update.yml`, and `openwiki/INSTRUCTIONS.md` |

## Physical evidence

Require the implementation Candidate base SHA, commit SHA, tree SHA, complete single-commit diff, source Spec SHA-256, Task Card SHA-256, exact C1-C8 outputs, changed-path set, and final isolated working-tree status.

Separate static scaffold evidence from any later OpenWiki canary evidence.

Current reconciliation records physical scaffold presence only. It does not
backfill absent historical validator, Candidate, acceptance, closure, or canary
receipts.

## Independent review

A reviewer independent from the Agy implementation pass must compare the exact Candidate against the source Spec, Task Card, complete diff, AC-001 through AC-006, command outputs, authority boundaries, and final state.

The reviewer cannot approve or integrate on behalf of the Owner.

## Exit conditions

- **PASS:** All six acceptance criteria are physically witnessed, C1-C8 pass, the exact three-file Candidate scope is preserved, and no authority boundary is expanded.
- **RETAINED_FOR_REVIEW:** Scaffold is physically present but historical acceptance, closure, independent review, or canary receipt evidence is missing. Do not claim `COMPLETED`.
- **BLOCK:** Any out-of-scope mutation, authority expansion, generated Wiki commit, canonical OpenWiki execution, stale material source assumption, or verifier failure.
- **Residual debt:** Actual OpenWiki generation quality and workflow-runtime behavior remain for a later manual canary.
- **Next gate:** Independent Candidate acceptance before separate Owner approval/integration.
