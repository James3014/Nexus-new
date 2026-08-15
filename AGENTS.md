# Universal Agent Guidelines

Scope: all coding agents.

## Authority bootstrap

- Repository authority: root `AGENTS.md`.
- Direct execution authority: an explicit current Owner request may authorize a
  bounded `DIRECT_CANONICAL` change without a Task Card or lifecycle state.
- Direct delegated execution authority: an explicit current Owner request may
  authorize a `DIRECT_DELEGATED` bounded delegation through an approved non-Nexus
  control plane, without Task Card or Nexus lifecycle authority.
- Governed execution authority: the active Git-tracked Task Card under
  `tasks/<campaign-id>/`.
- `MUSE_PROTO.md` is response/domain overlay, never mutation authority.

The Owner chooses the execution lane; defaults/skills cannot relabel it, and
`auto` is not direct authority. Lane governs authorization, not correctness:
source behavior, tests, and required verifiers remain authoritative.

## GitHub collaboration summary

- Collaboration repository `James3014/Nexus-new`; default and collaboration
  branch `main`.
- A Ready GitHub Issue is a worker-neutral bounded collaboration contract; it
  does not select local lifecycle. Draft, triage, and unready Issues grant no
  mutation. An eligible governed worker implements on an issue-specific branch
  such as `codex/issue-<number>-<slug>`, pushes only that branch, and opens a PR
  to `main`. Provider/model names are not normative ownership identities.
- Issue claim metadata is explicit and fail-closed: `claim_intent`,
  `claim_enforcement_state`, and `claim_mode`; `PROJECTION_ONLY` or `UNKNOWN`
  enforcement resolves to `MANUAL_DISPATCH`. assignees, labels, comments, Project fields, branch names, and
  worker prose are projections and cannot authorize autonomous mutation.
- No agent direct-pushes, force-pushes, or deletes `main`; delegated workers
  never approve or merge their Candidate. Only the primary coordinator may use
  protected PR merge under current Owner integration authority. A standing grant
  alone is not merge authority. Never merge runtime history into GitHub `main`
  to align SHAs.
- A non-transferable standing grant for bounded Ready Issues in one thread, bound
  by its active Task Card receipt, may let the coordinator create/commit a
  missing Task Card/INDEX when the Issue is Ready, paths and claim ceiling are
  frozen, gates pass, and `AUTO_CHAIN=false`; workers cannot create, widen, or
  self-authorize cards.
- A current explicit Owner instruction to complete/finish/integrate the bounded
  GitHub change is the coordinator's non-transferable integration authority for
  that approved goal/scope. Merge stays strict: independent acceptance, fresh
  PR/head/base/diff, current `main`/base compatibility, resolved blockers,
  terminal-success required checks, and expected-head/CAS. Drift, conflict, or
  unknown/failed checks fail closed.
- Integration authority survives ordinary in-scope repair commits (format,
  lint, test, or in-risk-bound semantic repair); a head SHA change alone is not
  reauthorization. Ask the Owner again only on material drift: goal/scope
  widening, destructive deletion, weaker security, branch-protection/check
  bypass, migration/schema/production-data authority, force-push/history
  rewrite, release/production/public claim, or a conflict requiring a new
  product/authority decision.
- Detailed standing-grant, claim, PR/merge, and reconciliation procedure:
  `docs/agents/TASK_EXECUTION_CONTRACT.md`.

## Repository baseline

- Before any mutation, record root, branch, HEAD, dirty state, and worktree
  topology: `git rev-parse --show-toplevel`, `git branch --show-current`,
  `git status --short --branch`, and `git worktree list --porcelain`.
- Preserve unrelated dirty state. Never reset, stash, clean, overwrite, or
  absorb ambiguous changes; use a clean governed Target or approved
  DevSpace-managed worktree when isolation is required.
- Local runtime root `/Users/jameschen/Workspace/nexus`; runtime/integration
  branch `nexus/integration/main`; query HEAD at task start. Retired
  `/Users/jameschen/Workspace/nexus-worktrees` is not an entry point. For local
  runtime work, re-anchor at the runtime root first; for GitHub collaboration,
  use the clone root and the Ready Issue's branch.

## Authority conservation and safety

- Implementation, commit, Candidate, verification, approval, integration, push,
  and release are distinct stages. A GitHub PR Candidate is an Issue-branch
  commit; a local lifecycle Candidate is receipt-bound Target output. Neither
  supplies authority to the other.
- An agent may implement, test, commit, push an authorized issue branch, and
  open a PR, but cannot convert its own implementation or Candidate into
  approval, integration, merge, release, or production truth. A separate
  designated integration action may perform only the Owner integration-authorized
  merge after independent acceptance and fresh merge-gate verification; only the
  primary coordinator under current Owner integration authority is that
  separate action, never a delegated implementer or reviewer.
- Worker output is implementation/candidate evidence only; it cannot self-approve
  or self-verify. No agent direct-pushes or deletes `main`. Do not hand-edit
  lifecycle JSON or protected control-plane state. Protected PR merge requires
  current Owner integration authority and never permits bypassing required
  checks. Standing coordinator authority covers pre-merge work only.
- Completion requires behavioral evidence, structural conformance, and the
  applicable request- or card-defined verifier. A report or green subset is not
  solve truth. Report evidence in the final response.
- If the self-hosting/controller identity contract is itself under repair and
  cannot bind a clean trustworthy execution identity, stop that path and use
  the bounded external bootstrap procedure in
  `docs/governance/rollback_runbook.md`; it creates no second authority and
  never implies approval, integration, push, reload, or activation.
- `REVISE` permits bounded correction; `RECOVERABLE_BLOCK` preserves retry;
  `HARD_BLOCK` pauses affected mutation. Reviewer block/card omission is not
  terminal `REJECTED`; only an authorized decision-maker may reject.

## Execution lanes

### DIRECT_CANONICAL

Owner -> primary agent -> one bounded direct change in the canonical checkout.
Eligible direct work does not require a Task Card, campaign, lifecycle state,
Target, Candidate, approval, or promotion receipt; it does not delegate
implementation. Record the baseline, keep the diff scoped, run relevant checks
plus `git diff --check`, and report changed files and evidence. Direct work
becomes governed before mutation when it changes route/lifecycle/workforce
authority, weakens security, changes migration or schema authority, requires
protected branch/ref operations, or makes production/public claims, or otherwise
exceeds the `DIRECT_CANONICAL` or `DIRECT_DELEGATED` boundary. Delegated
implementation alone does not force governed execution when all `DIRECT_DELEGATED`
conditions are satisfied.

### DIRECT_DELEGATED

Owner -> primary coordinator -> approved non-Nexus control plane (such as
DevSpace) -> exactly one bounded external worker -> independent coordinator
verification -> STOP.

No Nexus Task Card, Nexus lifecycle, CapabilityPlanner routing, Nexus Workforce
Admission, or Candidate lifecycle is required solely for this lane. The worker
cannot approve, integrate, merge, push, clean unrelated state, release, make
production/public claims, or act as its own required independent verifier.
`AUTO_CHAIN=false`. The primary coordinator independently inspects the physical
diff and reruns the applicable verifier; worker PASS is implementation evidence
only. Timeout/disconnect reconciles the same durable worker/session and
filesystem/Git/provider state before retry. Fail closed with
`DIRECT_DELEGATED_BLOCKED` when work exceeds these boundaries; do not silently
create a Task Card or switch to Nexus.

Eligibility, baseline binding, dirty-state/isolation, retry, and escalation
detail: `docs/agents/TASK_EXECUTION_CONTRACT.md`. Nexus Workforce Admission vs
non-Nexus external identity binding: `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.

### GOVERNED

Use when work requires Nexus lifecycle/Candidate authority,
route/lifecycle/workforce authority changes, protected integration,
security-boundary changes, migration/schema authority, production-data
mutation, or production/public claim authority. Load
`docs/agents/TASK_EXECUTION_CONTRACT.md` plus the active card. A Task Card binds
scope/evidence; it never substitutes for program correctness.

## Conditional load map

Load the smallest authoritative surface that matches the task:

- Owner-authorized bounded primary direct mutation: this file plus the nearest
  relevant nested authority; no Task Card or lifecycle state is required.
- `DIRECT_DELEGATED` delegation: this file plus
  `docs/agents/TASK_EXECUTION_CONTRACT.md`;
  `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md` for the worker/execution identity
  boundary.
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
- OpenWiki is `derived_non_authoritative` navigation only; source, tests, or
  bound runtime evidence verify claims.

## Authority invariants

- `CapabilityPlanner` is the sole route and capability-selection authority.
  `HybridRouteDecision` is a Planner-derived decision contract/projection, not a
  second selector, router, or planner; overlays and policy files cannot create
  another one.
- Workforce admission only constrains worker eligibility; it does not select a
  route or capability and does not authorize self-approval.
- Missing verifier artifact/status or source hash fails claim gates closed.

## Response and tool discipline

- Follow `MUSE_PROTO.md` for response/domain tags.
- Prefer direct tools and concise evidence; do not narrate calls.
- On degenerate/repetitive output, stop mutation, preserve the last verified
  state, and report `retry_required=true`.
