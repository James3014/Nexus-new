# Universal Agent Guidelines

Scope: Antigravity, Gemini, OpenClaw, Codex, and Claude.

- Repository authority: this root `AGENTS.md`.
- Direct execution authority: an explicit current Owner request may authorize a
  bounded `DIRECT_CANONICAL` change without a Task Card or lifecycle state.
- Governed execution authority: the active Git-tracked Task Card under
  `tasks/<campaign-id>/`.
- Response/domain overlay: `MUSE_PROTO.md`; it never grants mutation authority.

## Repository collaboration authority (GitHub)

- The collaboration repository is `James3014/Nexus-new`; its default and
  collaboration branch is `main`.
- A GitHub Issue becomes an approved implementation unit only after the Owner
  marks it Ready with bounded scope, acceptance criteria, and explicit
  non-goals. Draft, triage, and unready Issues grant no mutation authority.
- Codex implements a Ready Issue on an issue-specific branch such as
  `codex/issue-<number>-<slug>`, pushes only that branch, and opens a pull
  request to `main`.
- Codex and other coding agents never direct-push, force-push, or delete
  `main`. Manual, legacy, and non-autonomy-enabled work remains Owner-reviewed
  and Owner-authorized for final merge. The bounded autonomy exception below
  applies only to this program's autonomy-enabled Goals.
- The local runtime repository and this sanitized collaboration repository have
  intentionally separate histories. Never treat SHA mismatch as missing work,
  or normal-merge, rebase, or cherry-pick local runtime history into GitHub
  `main` merely to align SHAs; synchronize by reviewed content or semantic
  delta and preserve GitHub-only governance without resurrecting secrets,
  runtime state, or generated artifacts.
- For manual, legacy, and non-autonomy-enabled work, final GitHub merge still
  requires explicit current Owner authorization. For an autonomy-enabled Goal,
  one bounded Owner Goal Grant may instead derive an exact action-bound machine
  authorization only after machine policy evaluation and independent
  acceptance; this is not unlimited autonomous merge authority and has no
  retroactive effect on older work.
- Every autonomous merge still requires fresh SHA-bound verification of the PR
  number, exact head, current base/main, complete diff, Goal Grant identity,
  independent acceptance, CI/check evidence, unresolved threads or blockers,
  and current authorization validity. A moved PR head fails closed.
- Under that exception, only the designated integration action may perform the
  exact-head merge after all listed gates pass; it may not direct-push `main`,
  broaden the Goal Grant, or merge manual/legacy work. This bounded exception
  is the specific, non-general authorization for an autonomy-enabled Goal.
- A Ready Issue defines GitHub collaboration scope only. It does not bypass
  Task Card or lifecycle requirements for delegated, isolated,
  lifecycle/security/schema, Candidate, approval, integration, release, or
  production work.

## Local Nexus runtime authority

- On the Owner's current machine, the local Nexus runtime entry point remains
  `/Users/jameschen/Workspace/nexus`. This is a machine-local runtime location,
  not a universal checkout requirement.
- Its local runtime/integration branch remains `nexus/integration/main`; query
  HEAD at task start. This bootstrap does not rename that branch or imply that
  its commit identity is synchronized with GitHub `main`.
- `/Users/jameschen/Workspace/nexus-worktrees` is retired local evidence, not an
  entry point. Do not create checkouts there.
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

- Implementation and commit, Candidate creation, verification, approval,
  integration, push, and release are distinct authorities and evidence stages.
- An agent may implement, test, commit, push an authorized issue branch, and
  open a PR. For manual/legacy work it cannot convert its own implementation
  or Candidate into approval, integration, merge, release, or production truth.
  For this program's autonomy-enabled Goals, a separate designated integration
  action may perform only the exact machine-authorized merge after independent
  acceptance and fresh merge-gate verification.
- GitHub review/merge does not silently perform Nexus lifecycle approval or
  runtime integration. Local Nexus runtime actions keep their existing formal
  authority and evidence requirements until a separate migration changes them.

## Safety and completion

- Preserve unrelated dirty state. Never reset, stash, clean, overwrite, or
  absorb ambiguous changes; use a clean governed Target when isolation is
  required.
- Do not hand-edit lifecycle JSON. Use the formal lifecycle API, CLI, or
  service surface. Do not push, merge protected main, or delete refs without
  explicit authority.
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
- Blocks are explicit: `RECOVERABLE_BLOCK` preserves the card for retry;
  `HARD_BLOCK` stops mutation until owner/spec authority resolves it. A block
  never promotes a Candidate or activates downstream work.

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
  task unless the Owner grants that exact authority. If eligibility is unclear,
  stop and report the specific escalation condition.
- A Ready GitHub Issue separately authorizes scoped commits and pushes on its
  issue-specific branch and opening a PR; it never authorizes direct `main`
  mutation or self-merge.

## Governed task-card and artifact governance

- Every active campaign has `tasks/<campaign-id>/INDEX.md` with authority,
  status, ordered cards, dependencies, frontier, and completed/blocked state.
- Each active card defines objective, inputs, dependencies, allowed files,
  forbidden scope, verification, evidence, exit criteria, and block class.
- The active card and machine baseline define allowed/forbidden files and any
  file-count ceiling; this root policy does not widen those limits.
- Implementation cards require a scoped commit unless explicitly read-only;
  stage only authorized files and inspect the complete staged diff.
- Before commit: run the card's exact checks, `git diff --check`, deletion
  audits, and staged/unstaged stats. Bind Candidate evidence to commit SHA and
  card hash; worker cannot approve or integrate its own Candidate.
- Persistent documents default to deny. Add one only when the user/card,
  runtime consumer, durable contract, dedicated audit, or cross-session handoff
  requires it. Mark admitted documents with purpose, authority, owner, status,
  and evidence/commit.
- Report evidence in the final response, commit, PR, or existing receipt;
  do not create recursive evidence reports.

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
- Broad repository orientation: when `openwiki/quickstart.md` exists, it may be used as a `derived_non_authoritative` navigation index to locate candidate subsystems, paths, symbols, entrypoints, workflows, and tests. Verify every operational, wiring, runtime, authority, or current-state claim against current source, tests, or bound runtime evidence before relying on it. OpenWiki absence, staleness, nondeterministic page layout, or disagreement never overrides current source and never blocks direct source inspection.

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

- Follow `MUSE_PROTO.md` for compressed response/domain tagging.
- Prefer direct tool invocation and concise evidence. Do not narrate tool calls.
- If output appears degenerate or repetitively looping, stop mutation, preserve
  the last verified state, and report `retry_required=true`.
