---
artifact_authority: current
owner: James Chen
status: active
purpose: Governed task-card and Owner-authorized direct-delegated execution contracts.
---

# Task Execution Contract

This is the L1 contract loaded for a governed mutating task and for
`DIRECT_DELEGATED` work. The active Git-tracked Task Card remains the
task-specific authority for governed work; this document supplies the shared
schema and gates. It is not required for an eligible Owner-authorized
`DIRECT_CANONICAL` change.

## Direct canonical boundary

An explicit current Owner request may authorize the primary agent to make one
bounded change directly in the canonical checkout without a Task Card or
lifecycle state. The agent freezes the request-derived file scope, preserves
unrelated dirty state, runs relevant checks plus `git diff --check`, and reports
the exact changed files and evidence.

The Owner chooses the execution lane; defaults, launchers, skills, and agents
must not relabel that explicit choice. The lane governs authorization, not
correctness: source behavior, tests, and required verifiers decide whether the
program works.

### Self-hosting stabilization and future default transition

The current repository operating mode remains `BOOTSTRAP`, which is the
self-hosting stabilization phase for execution-lane selection. G10 proves that a
canonical Nexus grant can drive a live `NEXUS_GOVERNED` DevSpace execution; it
is not an automatic repository-wide switch to governed-by-default work.
Eligible bounded Nexus development may therefore continue through
`DIRECT_CANONICAL` or `DIRECT_DELEGATED` while this operating mode remains in
force, subject to every existing direct-lane scope, verification, escalation,
and authority boundary in this contract.

Nexus execution lanes (`DIRECT_CANONICAL`, `DIRECT_DELEGATED`, `GOVERNED`) and
DevSpace authority modes (`OWNER_DIRECT`, `NEXUS_GOVERNED`) are related but not
identical. DevSpace is execution plumbing and does not choose the Nexus lane.
An attempt already admitted as governed / `NEXUS_GOVERNED` must never fall back
to a direct / `OWNER_DIRECT` attempt merely because authority is missing, stale,
expired, unreachable, or a transport fails. The same attempt must fail closed to
block, rebind, or reconciliation; any direct recovery is a separately
Owner-authorized attempt with a distinct authority identity.

`NEXUS_GOVERNANCE_DEFAULT_READY` may be declared only by the Owner after a fresh
readiness review. At minimum, that review should bind evidence that:

- representative real tasks complete end to end under governed authority;
- continuation, timeout, reconciliation, and restart behavior has been exercised;
- Nexus can modify itself without routine authority-recursion deadlocks;
- Task Card, grant, admission, and execution contracts are stable enough for
  normal work rather than repeated bootstrap exceptions;
- common Nexus engineering no longer requires routine direct bypass; and
- the direct recovery path can restore a failed governance plane.

G10, CI, tests, Task Cards, agents, or runtime state cannot self-declare this
milestone. After the Owner declares it, a separate policy revision may make
governed execution the default and narrow direct authority. Until then,
narrowly typed DevSpace `OWNER_DIRECT` bootstrap/environment capabilities such
as `workspace_clone` and `dependency_sync` remain valid stabilization tools and
are not considered governance defects solely because they are not yet
`NEXUS_GOVERNED`.

Direct work becomes governed before mutation when it changes
route/lifecycle/workforce authority, weakens security, changes migration or
schema authority, requires protected branch/ref operations, or makes
production/public claims, or otherwise exceeds the `DIRECT_CANONICAL` or
`DIRECT_DELEGATED` boundary. Direct work does not commit, push, merge, delete,
or auto-chain without exact Owner authority. The standing coordinator grant does
not expand `DIRECT_CANONICAL`; it applies only to the governed GitHub Ready-Issue
actions defined below.

## Direct delegated boundary

This governed contract is not required solely because implementation is
delegated when the root `AGENTS.md` `DIRECT_DELEGATED` contract is satisfied.
Escalate to this governed contract when delegated work exceeds the
`DIRECT_DELEGATED` boundary, requires Nexus lifecycle/Candidate authority,
changes route/lifecycle/workforce/security authority, requires protected
integration, or otherwise meets a governed-work condition.

`DIRECT_DELEGATED` means:

Owner -> primary coordinator -> approved non-Nexus control plane such as
DevSpace -> exactly one bounded external implementation worker -> independent
primary-coordinator verification -> STOP.

It is not Nexus runtime, Task Card, Nexus lifecycle, CapabilityPlanner routing,
Nexus Workforce Admission, or Candidate lifecycle authority. An explicit current
Owner request is the authority source. No Nexus Task Card, lifecycle state, or
Workforce Admission is required solely for this lane.

Eligibility requires, at minimum:

- exactly one bounded implementation task;
- exact external control plane and worker identity;
- repository root / branch / HEAD / dirty baseline recorded before dispatch;
- exact profile/provider/model and material CLI/runtime version when observable;
- bounded mutation scope;
- unrelated dirty state preserved;
- the worker cannot approve, integrate, merge, push, clean unrelated state,
  release, or make production/public claims;
- the worker cannot act as its own required independent verifier;
- the primary coordinator independently inspects the physical changes and reruns
  the applicable verification; worker-reported PASS is implementation evidence
  only;
- `AUTO_CHAIN=false`;
- timeout/disconnect reconciles the same durable worker/session and
  filesystem/Git/provider state before retry; do not blindly launch a
  replacement worker.

Isolation: use the canonical checkout only when unrelated dirty state is
demonstrably non-overlapping; otherwise an approved DevSpace-managed isolated
worktree may be used. That is transport/workspace isolation only and is never a
Nexus Target or Candidate.

Fail closed with `DIRECT_DELEGATED_BLOCKED` -- without silently creating a Task
Card or switching to Nexus -- when the work materially requires:

- CapabilityPlanner / route authority changes;
- Nexus lifecycle authority changes;
- Workforce Admission / workforce policy changes;
- security-boundary weakening;
- unresolved product/business semantics;
- potentially executed historical migration rewrite;
- ambiguous production-data mutation/backfill;
- protected merge/push/ref operations;
- release or production/public claim authority;
- milestone/program-level `AUTO_CHAIN`;
- the worker acting as its own required independent verifier.

## Governed discovery and authority

1. Anchor at the canonical root and verify root, branch, status, and worktrees.
2. Read `AGENTS.md`, the campaign `INDEX.md`, and only the current frontier card.
3. Verify the lifecycle task id, card path, and card hash before editing.
4. Runtime `.nexus` state may record receipts and hashes but cannot replace or
   rewrite the card. `AUTO_CHAIN=false` unless the index explicitly enables it.

Every active card declares objective, authority/status, inputs, dependencies,
allowed files, forbidden scope, verification commands, required evidence, exit
criteria, residual-debt handling, and block classification. Its allowed and
forbidden paths, file-count ceiling, and commit policy are the operative scope.

The Task Card binds execution scope and evidence. It does not replace the
program or turn incomplete source behavior into completion merely because the
document is structurally complete.

When the Owner has granted standing coordinator authority and its durable grant
receipt is current, the primary Codex coordinator may create and commit a
missing Task Card/INDEX for an already Ready Issue after freezing the effective
Issue contract, current baseline, overlap, Workforce receipt, verification,
and claim ceiling. The canonical active machine-local receipt is read from the
single durable path `.local/state/nexus/authority/standing-grant.json` (the
`nexus.orchestrator.standing_grant_store` loader); there is no
environment-selected second authority root. A missing, malformed, tampered,
unsafe-permission, expired, or revoked receipt fails closed. Delegated workers cannot create or widen their own
authority; they begin only after the card is physically committed and its hash
is read back. The grant does not authorize local runtime/lifecycle actions,
direct protected-main push, force-push, ref deletion, successor work outside
the active Goal, release, or production/public claims.

Only the primary coordinator under the current grant may create and commit a
missing card once, then read back its hash. A delegated worker, reviewer, or
launcher must not create, widen, or recursively bootstrap the card that would
authorize its own work.

For a fresh coordinator/chat/agent session, load and validate the canonical
standing-grant receipt before evaluating an already-authorized GitHub action.
The receipt context `thread_id` is the Owner-issued durable coordination-scope
identifier; a replaceable chat, provider, or agent session identifier is
transport provenance and must not replace that authority identity. Rehydrate
the durable coordination scope from the validated receipt, then re-check Owner,
coordinator, repository, Goal, action, expiry/revocation, and receipt integrity.
A session change alone is not a new Owner authorization boundary.

## G12 Fast Start advisory-cache gate

Apply the root `AGENTS.md` #549 `ADVISORY_CACHE_ONLY` preflight before any implementation source/test body reads.

## GitHub collaboration and local lifecycle domains

- A GitHub PR Candidate is an Issue-branch commit governed by the Ready Issue,
  committed card when delegation requires it, focused checks, CI, independent
  acceptance, and expected-head/CAS merge authority.
- A local lifecycle Candidate is formal Target output governed by self-hosted
  submit, receipt, approval, and integration gates.
- Ready-Issue collaboration is worker-neutral. A claim contract may carry
  `claim_intent` (`AUTO_CLAIM_IF_READY`, `MANUAL_DISPATCH`, or
  `NOT_CLAIMABLE`), `claim_enforcement_state` (`REPO_ENFORCED`,
  `PROJECTION_ONLY`, or `UNKNOWN`), and effective `claim_mode` with the same
  values. These are distinct: intent is planning metadata, enforcement is a
  repository capability claim, and mode is the dispatch result.
- Autonomous mutation requires the exact Issue/attempt to pass all hard gates
  and a canonical atomic/fenced claim operation to succeed. Until that
  operation is physically proven, `PROJECTION_ONLY` and `UNKNOWN` resolve
  fail-closed to `MANUAL_DISPATCH`. GitHub UI metadata and branch names remain
  projections and do not provide exclusive ownership.
- A claim grants only the bounded implementation attempt. It never grants
  route selection, Workforce promotion, independent acceptance, approval,
  integration, merge, runtime activation, release, or production truth.

Ordinary GitHub Issue work does not enter local lifecycle merely because it is
delegated or produces a PR Candidate. Local lifecycle tools are mandatory only
after that domain is selected or the requested outcome is a local governed
Target/runtime/lifecycle result. GitHub merge never implies lifecycle approval
or integration, and lifecycle approval never implies GitHub merge authority.
`nexus_startup_contract_check.py` validates direct or local governed startup;
it is not the admission or merge gate for ordinary GitHub PR work. Likewise,
delivery preference `auto` may choose an isolated execution route but cannot
stand in for an explicit Owner lane selection.

## Mutation safety

- Preserve unrelated dirty state. Use a clean governed Target for isolation;
  never reset, stash, clean, overwrite, or absorb ambiguous changes.
- Do not hand-edit lifecycle JSON or protected control-plane state. Use formal
  API, CLI, or service surfaces and preserve receipts.
- A worker may never approve, integrate, merge, or delete refs for its own
  Candidate. A card may grant only a scoped issue-branch push and bounded
  non-destructive cleanup; it cannot grant self-approval or self-integration.

## Commit and Candidate gates

Implementation cards require a scoped commit unless explicitly read-only,
audit-only, or commit-forbidden. Before committing:

- verify only allowed files changed;
- run the card's exact verification commands and `git diff --check`;
- inspect tracked and staged deletions, both diff stats, and the full staged diff;
- create the commit with the exact card scope and report its SHA.

Candidate formation binds the verified commit SHA and task-card hash to the
receipt. Candidate, approval, integration, push, cleanup, and production/public
claims are separate lifecycle states. A failed required commit is a block, not
completion.

The primary coordinator may prepare `MERGE_INTENT` and continue through normal
GitHub workflow phases under a current standing grant whose exact repository,
Goal, coordinator, and action binding remains valid. Before protected merge it
must perform an independent exact-head review, terminal success for every
ruleset-required check, an up-to-date base, complete scope/deletion audits,
branch-protection verification, and expected-head/CAS. A normal phase
transition does not require redundant Owner reauthorization. A real authority
boundary (scope widening, expiry/revocation/invalid binding, security change,
new irreversible external effect, release/production, or genuine external
platform approval) fails closed and requires the corresponding new decision.
Any PR/head/base/main or evidence drift invalidates the current merge attempt
and must be revalidated before CAS.
`MERGE_INTENT` is evidence and standing authority is authorization only; neither
substitutes for the verification gates. This GitHub action does not approve or
integrate local Nexus lifecycle state.
When the live MCP surface exposes `github_complete_pull_request`, ordinary
protected-merge completion after independent acceptance uses that action rather
than reconstructing merge evidence by hand. The action binds
`run_github_completion_loop()` to server-configured `NEXUS_CANONICAL_SOURCE_ROOT`
and `NEXUS_PYTHON_BIN`; required checks still execute on the exact current
integration subject; physical merge remains expected-head/CAS. Absence of the
action is not a new Owner-approval boundary; fall back to the existing
coordinator CAS path. The action cannot mint standing-grant or merge authority.

## Blocks and residual debt

`RECOVERABLE_BLOCK` preserves the same card for retry after an external or
environmental condition. `HARD_BLOCK` stops mutation for authority, safety,
architecture, evidence-integrity, irreversible-risk, or specification conflict.
Neither block permits promotion, cleanup, or downstream activation. Supersede a
card only with an explicit `superseded_by` link and a new independently hashed
card.

`REVISE` means bounded correction of the same work within existing authority.
A reviewer block, card clarification, or missing card is not automatically a
terminal `REJECTED` Candidate. Only the authorized decision-maker may apply
`REJECTED` after stating why repair in place is unsuitable. These are review
and authority semantics; they do not expand a CLI's enumerated terminal
disposition surface.

## Post-completion Issue reconciliation

A governed GitHub Issue is terminal only after a fresh, revision-bound
completion snapshot is evaluated against the physical repository. A worker
report, green pre-merge run, merged PR, close keyword, terminal marker, or
historical receipt is an evidence input and is never sufficient by itself.

The snapshot binds the exact repository, Issue contract revision and latest
durable comment, Candidate and PR identity, Candidate head, merge commit,
current default-branch HEAD and tree, required post-merge verifier evidence,
hard prerequisites, downstream effects, and residual scope. A separately
captured fresh binding input supplies the expected repository, Issue, latest
comment, PR, Candidate head, merge commit, canonical main ref and head/tree,
exact required-evidence set, and exact predecessor receipts; snapshot fields
cannot self-attest those identities. The consumer resolves the binding's
canonical `nexus-new` collaboration remote URL and default-branch ref rather
than the invoking worktree's `HEAD` or an arbitrary remote.
Candidate, PR, and Issue identities must agree; the Candidate head must be
contained by the merge commit, and the merge commit must be contained by the
resolved default branch. Missing, stale, malformed, wrongly attributed, or
revision-mismatched evidence fails closed and cannot unlock downstream work.

The reconciliation selects exactly one disposition:

- `DONE_NO_FOLLOW_UP`: the original bounded contract is physically complete
  and no independently bounded survivor remains.
- `KEEP_OPEN`: the original contract or a hard prerequisite remains incomplete;
  same-scope work stays on the original Issue.
- `CONTRACT_DELTA`: fresh evidence requires a bounded correction or
  re-verification of the original contract without rewriting its history.
- `FOLLOW_UP_REQUIRED`: the original Issue is independently complete and a
  distinct bounded survivor remains after checking for an existing durable
  owner.
- `BLOCKED_EVIDENCE`: required identity or evidence is missing, stale,
  malformed, contradictory, or unavailable.

Only `DONE_NO_FOLLOW_UP` and `FOLLOW_UP_REQUIRED` are terminal. Downstream
readiness additionally requires every hard predecessor to have a terminal
disposition bound to the same current-main revision. The machine consumer is
`scripts/ops/agent_protocol_check.py --completion-snapshot
<snapshot.json> --completion-bindings <fresh-bindings.json> --main-ref
refs/remotes/nexus-new/main`; it validates this contract but does not fetch or
store Issue state, create follow-ups, approve Candidates, or create a second
completion authority.
