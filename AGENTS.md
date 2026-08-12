# Universal Agent Guidelines

Scope: all coding agents.

- Repository authority: root `AGENTS.md`.
- Direct authority: an explicit current Owner request may authorize a
  bounded `DIRECT_CANONICAL` change without a Task Card or lifecycle state.
- Governed authority: the active Git-tracked Task Card under
  `tasks/<campaign-id>/`.
- `MUSE_PROTO.md` is response/domain overlay, never mutation authority.

The Owner chooses the execution lane; defaults/skills cannot relabel it, and
`auto` is not direct authority. Lane governs authorization, not correctness:
source behavior, tests, and required verifiers remain authoritative.

## Repository collaboration authority (GitHub)

- The collaboration repository is `James3014/Nexus-new`; its default and
  collaboration branch is `main`.
- A Ready GitHub Issue authorizes bounded collaboration only; it does not select
  local lifecycle. Draft, triage, and unready Issues grant no mutation.
- Codex implements a Ready Issue on an issue-specific branch such as
  `codex/issue-<number>-<slug>`, pushes only that branch, and opens a pull
  request to `main`.
- No agent direct-pushes, force-pushes, or deletes `main`; delegated workers
  never approve or merge their Candidate. Only the primary coordinator may use
  protected PR merge under exact Owner approval or the standing grant below.
- Never merge runtime history into GitHub `main` to align SHAs; synchronize only
  reviewed deltas without secrets or generated/runtime state.
- The Owner may give the primary coordinator a non-transferable standing grant
  for bounded Ready Issues in one thread, eliminating repeated Task Card,
  branch, push, PR, and merge approvals. Its active Task Card receipt binds
  grant/Goal ids, parties, repository/thread, scope/actions, eligibility,
  issuance, expiry, and revocation. It ends when revoked, narrowed, or the Goal
  is verified terminal and grants no delegated-worker authority.
- Under that standing grant, the primary coordinator may create and commit a
  missing Task Card/INDEX only when the effective Issue contract is already
  Ready, exact allowed/forbidden paths and the claim ceiling are frozen,
  overlap and Workforce gates are satisfied, and `AUTO_CHAIN=false`. Workers
  may consume the committed card but cannot create, widen, or self-authorize
  it.
- Every coordinator merge still requires a fresh SHA-bound PR/head/base/diff,
  Issue/card, independent acceptance, resolved blockers, valid authorization,
  current `main`, terminal-success required checks, and expected-head/CAS.
  Drift, conflict, unexpected deletion, or unknown/failed checks fail closed.
- The coordinator handles ordinary implementation, rebind, retry, and evidence
  autonomously. It asks again only for contract widening/change, weaker
  security, a new irreversible external effect, or release/production claims.
- After merge, read back `main`, record merge/head/check evidence, reconcile the
  Issue/card, then start downstream work. This never implies local lifecycle,
  runtime, release, or production truth.
- Delegated GitHub work consumes its card; it uses local lifecycle only when
  Owner-selected or producing a local Target/runtime/lifecycle outcome.

## Local Nexus runtime authority

- The Owner's local runtime root is `/Users/jameschen/Workspace/nexus`; it is not
  a universal checkout requirement.
- Its local runtime/integration branch remains `nexus/integration/main`; query
  HEAD at task start. This bootstrap does not rename that branch or imply that
  its commit identity is synchronized with GitHub `main`.
- Do not use retired `/Users/jameschen/Workspace/nexus-worktrees`.
- Before every task, run:
  `git rev-parse --show-toplevel`, `git branch --show-current`,
  `git status --short --branch`, and `git worktree list --porcelain`.
- Classify the execution lane before mutation. For an eligible
  `DIRECT_CANONICAL` change, read this file and the nearest relevant nested
  authority, then freeze the request-derived file scope. For governed work,
  read the campaign `INDEX.md` and only the current-frontier card, then verify
  the lifecycle task id, card path, and card hash before editing.
- Runtime state, reports, chat, and old worktrees cannot replace the Git-tracked
  Task Card for governed work or silently rewrite it. `AUTO_CHAIN=false` unless
  the index says so.
- For local runtime work, stop mutation and re-anchor at the local runtime root
  first. For GitHub collaboration work, use the current clone root and the
  Ready Issue's branch; do not require the machine-local absolute path.

## Governance boundary

- Implementation, commit, Candidate, verification, approval, integration, push,
  and release are distinct stages.
- A GitHub PR Candidate is an Issue-branch commit; a local lifecycle Candidate
  is receipt-bound Target output. Neither supplies authority to the other.
- An agent may implement, test, commit, push an authorized issue branch, and
  open a PR. For manual/legacy work it cannot convert its own implementation
  or Candidate into approval, integration, merge, release, or production truth.
  For this program's autonomy-enabled Goals, a separate designated integration
  action may perform only the exact machine-authorized merge after independent
  acceptance and fresh merge-gate verification. The primary coordinator acting
  under a valid standing grant is that separate integration action; a delegated
  implementer or reviewer is not.
- GitHub review/merge does not silently perform Nexus lifecycle approval or
  runtime integration. Local Nexus runtime actions keep their existing formal
  authority and evidence requirements until a separate migration changes them.

## Safety and completion

- Preserve unrelated dirty state. Never reset, stash, clean, overwrite, or
  absorb ambiguous changes; use a clean governed Target when isolation is
  required.
- Do not hand-edit lifecycle JSON. Use the formal lifecycle API, CLI, or
  service surface. Do not direct-push protected main or delete refs. Protected
  PR merge requires exact Owner authority or the standing coordinator grant
  above and never permits bypassing required checks.
- Completion requires behavioral evidence, structural conformance, and the
  applicable request- or card-defined verifier. A report or green subset is not
  solve truth.
- A local or delegated model produces a candidate only; it cannot approve,
  promote, integrate, push, claim production readiness, or clean up.
- If the self-hosting/controller identity contract is itself under repair and
  cannot bind a clean trustworthy execution identity, stop that path and use
  the bounded external bootstrap procedure in
  `docs/governance/rollback_runbook.md`; it creates no second authority and
  never implies approval, integration, push, reload, or activation.
- Governed workers may commit only their scoped card changes. Approval,
  integration, push, cleanup, and production/public claims remain separate
  authorities.
- `REVISE` permits bounded correction; `RECOVERABLE_BLOCK` preserves retry;
  `HARD_BLOCK` pauses affected mutation. Reviewer block/card omission is not
  terminal `REJECTED`; only an authorized decision-maker may reject.

## Direct canonical execution

- An explicit current Owner instruction to modify the repository authorizes
  `DIRECT_CANONICAL` when the primary agent performs one bounded change in the
  canonical checkout with a clear file scope and no overlap with unrelated
  dirty state.
- Eligible direct work does not require a Task Card, campaign, lifecycle state,
  Target, Candidate, approval, or promotion receipt. Record the baseline, keep
  the diff scoped, run relevant checks plus `git diff --check`, and report the
  changed files and evidence in the final response.
- Direct work becomes governed before mutation if it delegates implementation,
  needs an isolated Target, crosses subsystems, changes route/lifecycle/workforce
  authority, weakens security, changes a migration or schema, performs cleanup
  or protected-branch/ref operations, creates a Candidate, or makes a
  production/public claim.
- Direct work does not commit, push, merge, delete, or continue into a successor
  task unless the Owner grants that exact direct authority. The standing
  coordinator grant does not expand `DIRECT_CANONICAL`; it applies only to
  governed GitHub Ready-Issue card creation, issue-branch work, and protected
  PR merge. If eligibility is unclear, stop and report the specific escalation
  condition.
- A Ready GitHub Issue separately authorizes scoped commits and pushes on its
  issue-specific branch and opening a PR; it never authorizes direct `main`
  mutation or self-merge.

## Governed task-card and artifact governance

- Each campaign `INDEX.md` records authority, status, cards, dependencies,
  frontier, and terminal state. Its active card records objective, inputs,
  verification/evidence, exit, and block class. That card plus machine baseline
  bind allowed/forbidden files and file-count ceiling; policy/workers cannot
  widen them.
- A Task Card binds scope/evidence; it never substitutes for program correctness.
- Implementation needs a scoped commit unless read-only. Stage only authorized
  files; run exact checks, `git diff --check`, deletion and staged/unstaged
  audits; bind Candidate commit/tree to card hash. Workers never self-approve.
- Persistent documents default-deny unless required by user/card, runtime
  consumer, durable contract/audit, or cross-session handoff. Mark purpose,
  authority, owner, status, and evidence. Report evidence in the final response,
  commit, PR, or existing receipt; never create recursive evidence reports.

## Conditional load map

Load the smallest authoritative surface that matches the task:

- Owner-authorized bounded direct mutation: this file plus the nearest relevant
  nested authority; no Task Card or lifecycle state is required.
- Governed mutation: `docs/agents/TASK_EXECUTION_CONTRACT.md` plus the active
  card.
- Model/provider selection, delegation, or routing: compact machine Workforce
  Admission receipt first; load the full policy/YAML only for policy changes,
  provider/model onboarding or calibration, promotion/demotion, admission
  audit, or an authority dispute. See
  `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.
- Claim, release, benchmark, audit, or verifier work:
  `docs/agents/CLAIM_AND_RECEIPT_OVERLAY.md`.
- Novel, repeatable failure with a prevention rule:
  `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`.
- LocalHeal or another nested subsystem: read its nearest nested `AGENTS.md`.
- Ordinary repository reads use targeted retrieval from the relevant lesson,
  ADR, report, or test; never full-corpus scanning by default.
- OpenWiki is `derived_non_authoritative` navigation only. Source, tests, or
  bound runtime evidence verify claims; OpenWiki never blocks source inspection.

## Authority invariants

- `CapabilityPlanner` is the sole route and capability-selection authority.
  `HybridRouteDecision` is a Planner-derived decision contract/projection, not
  a second selector, router, or planner; overlays and policy files cannot
  create another one.
- Workforce admission only constrains worker eligibility. Exact model
  identity, adapter preflight, parser, verifier, and receipt gates remain
  fail-closed; admission does not select a route or capability.
- Optional telemetry may be zero for structural gates, but model calls require
  real execution metrics. Missing verifier artifact/status or source hash
  fails claim gates closed.
- A novel lesson belongs in the existing Learning Closure Matrix or ledger;
  routine failures do not create new reports. Durable architectural choices
  use an ADR.

## Response and tool discipline

- Follow `MUSE_PROTO.md` for response/domain tags.
- Prefer direct tools and concise evidence; do not narrate calls.
- On degenerate/repetitive output, stop mutation, preserve the last verified
  state, and report `retry_required=true`.
