# Universal Agent Guidelines

Scope: all coding agents.

## Authority bootstrap

- Repository authority: root `AGENTS.md`.
- Direct authority: an explicit current Owner request may authorize a bounded
  `DIRECT_CANONICAL` change that does not require a Task Card or lifecycle state.
- Direct delegated authority: an explicit current Owner request may authorize one
  bounded `DIRECT_DELEGATED` milestone through an approved non-Nexus control
  plane, without a Task Card or Nexus lifecycle state solely because a worker is
  delegated.
- Governed authority: the active Git-tracked Task Card under
  `tasks/<campaign-id>/`.
- `MUSE_PROTO.md` is response/domain overlay, never mutation authority.

The Owner chooses the execution lane; defaults/skills cannot relabel it, and
`auto` is not direct authority. Lane governs authorization, not correctness:
source behavior, tests, and required verifiers remain authoritative.

## Repository collaboration authority (GitHub)

- The collaboration repository is `James3014/Nexus-new`; default and
  collaboration branch is `main`.
- A Ready GitHub Issue is a worker-neutral bounded collaboration contract; it
  does not select local lifecycle. Draft, triage, and unready Issues grant no
  mutation. An eligible governed worker implements on an issue-specific branch
  such as `codex/issue-<number>-<slug>`, pushes only that branch, and opens a PR
  to `main`. Provider/model names are not normative ownership identities.
- Issue claim metadata is explicit and fail-closed: `claim_intent`,
  `claim_enforcement_state`, and `claim_mode`; `PROJECTION_ONLY` or `UNKNOWN`
  enforcement resolves to `MANUAL_DISPATCH`. assignees, labels, comments, Project fields, branch names, and worker prose are projections and cannot
  authorize autonomous mutation.
- No agent direct-pushes, force-pushes, or deletes `main`; delegated workers
  never approve or merge their Candidate. Only the primary coordinator may use
  protected PR merge after the current Owner standing grant is validated for
  the exact repository, Goal, coordinator, and normal GitHub action. A valid
  covered standing grant remains valid across normal workflow phase
  transitions; a fresh Owner decision is required only at a real authority
  boundary such as scope, validity, security, irreversible external effect,
  release, production, or external-platform approval. The primary coordinator may use protected PR merge only when the separate physical standing-grant receipt explicitly includes `GITHUB_MERGE` and all exact verification, CAS, acceptance, checks, review, scope, deletion, and branch-protection gates pass.
- Never merge runtime history into GitHub `main` to align SHAs; synchronize only
  reviewed deltas without secrets or generated/runtime state.
- The Owner may give the primary coordinator a non-transferable standing grant
  for bounded Ready Issues in one thread. Its active Task Card receipt binds the
  grant/Goal, parties, repository/thread, scope/actions, eligibility, issuance,
  expiry, and revocation. It grants no delegated-worker merge authority.
- Under that standing grant, the primary coordinator may create/commit a missing
  Task Card/INDEX only when the Issue is Ready, paths and claim ceiling are
  frozen, gates pass, and `AUTO_CHAIN=false`; workers cannot create, widen, or
  self-authorize cards.
- Every coordinator merge requires a fresh SHA-bound PR/head/base/diff,
  Issue/card, independent acceptance, resolved blockers, current `main`,
  terminal-success required checks, branch protection, scope/deletion checks,
  and expected-head/CAS, all bound to the exact repository, PR, head, and base.
  `MERGE_INTENT` is evidence, not a substitute for
  these verification gates; a normal phase transition does not require a
  redundant Owner merge-slot request.
  Drift, conflict, unexpected deletion, or unknown/failed checks fail closed.
- The coordinator handles ordinary implementation, rebind, retry, and evidence
  autonomously. It asks again only for contract widening/change, weaker
  security, a new irreversible external effect, or release/production claims.
- After merge, read back `main`, record merge/head/check evidence, reconcile the
  Issue/card, then start downstream work. This never implies local lifecycle,
  runtime, release, or production truth.
- Delegated GitHub work consumes its card; it uses local lifecycle only when
  Owner-selected or producing a local Target/runtime/lifecycle outcome.

## Repository baseline

- Before mutation record root, branch, HEAD, dirty state, and worktree topology:
  `git rev-parse --show-toplevel`, `git branch --show-current`,
  `git status --short --branch`, and `git worktree list --porcelain`.
- Preserve unrelated dirty state. Never reset, stash, clean, overwrite, or
  absorb ambiguous changes; use an authorized isolated worktree/Target when
  isolation is required.
- Local runtime root `/Users/jameschen/Workspace/nexus`; runtime/integration
  branch `nexus/integration/main`; query HEAD at task start. Retired
  `/Users/jameschen/Workspace/nexus-worktrees` is not an entry point. GitHub
  collaboration uses the current clone and Ready-Issue branch.

## Governance boundary

- Implementation, commit, Candidate, verification, approval, integration, push,
  and release are distinct stages. A GitHub PR Candidate is an Issue-branch
  commit; a local lifecycle Candidate is receipt-bound Target output. Neither
  supplies authority to the other.
- An agent may implement, test, commit, push an authorized issue branch, and open
  a PR, but cannot convert its own implementation or Candidate into approval,
  integration, merge, release, or production truth. For autonomy-enabled Goals,
  a separate designated integration action may perform only the exact
  standing-grant-authorized merge after independent acceptance and fresh
  merge-gate verification. The primary coordinator acting under a valid, exact
  standing grant is that separate integration action; a delegated
  implementer or reviewer is not.
- GitHub review/merge does not silently perform Nexus lifecycle approval or
  runtime integration. Local Nexus runtime actions keep their existing formal
  authority and evidence requirements until a separate migration changes them.

## Safety and completion

- Do not hand-edit lifecycle JSON or protected control-plane state. Use formal
  APIs/CLI/service surfaces. Protected PR merge requires a valid current
  covered Owner standing grant plus exact verification and never permits
  bypassing required checks. Standing coordinator authority remains bounded by
  its explicit repository, Goal, coordinator, action, and validity scope.
- Completion requires behavioral evidence, structural conformance, and the
  applicable request- or card-defined verifier. A report or green subset is not
  solve truth.
- A local or delegated model produces implementation/candidate evidence only; it
  cannot approve, promote, integrate, merge, claim production readiness, or
  clean unrelated state.
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

## Execution lanes

### DIRECT_CANONICAL

Owner -> primary agent -> one bounded direct change in the canonical checkout.
Eligible direct work does not require a Task Card, campaign, lifecycle state,
Target, Candidate, approval, or promotion receipt and does not delegate
implementation. Record the baseline, keep the diff scoped, run relevant checks
plus `git diff --check`, and report changed files/evidence.

Direct work becomes governed before mutation when it changes
route/lifecycle/workforce authority, weakens security, changes migration/schema
authority, performs cleanup requiring governed authority, requires protected
branch/ref operations, creates a governed Candidate, makes a production/public
claim, or otherwise exceeds `DIRECT_CANONICAL` or `DIRECT_DELEGATED`. Delegated
implementation alone does not force governed execution when all
`DIRECT_DELEGATED` conditions are satisfied.

`AUTHORITY_PRESERVING_EVIDENCE_WRITEBACK` is a fail-closed eligibility
classification inside the existing `DIRECT_CANONICAL` lane, not a fourth lane
or a policy bypass. Merely touching an authority filename/path, or satisfying a
small line-count threshold, neither proves nor disproves an authority change. A future bounded
writeback may use this classification only when current Owner authorization,
bounded scope, additive evidence/provenance identity, exact changed-file and
deletion audits, focused contract tests, and `git diff --check` are present,
and a semantic authority-delta comparison proves every effective authority
invariant unchanged. Those invariants include autonomy; roles/capabilities;
worker/provider/model admission; default route and authority-transferring
lineage; parser, verifier, independent-review, forbidden-action, and claim
ceilings; CapabilityPlanner, lifecycle, Candidate, approval, integration,
merge, release, security, migration/schema, production-data, production, and
public-claim authority. It must not redesign a loader/schema merely to fit the
classification or bundle a protected push, merge, release, or other authority
action. Any changed, missing, malformed, contradictory, unknown, or otherwise
unprovable dimension resolves to existing `GOVERNED` handling. This rule is
future-only: it never rewrites or retroactively authorizes historical work.
A historical or separately required `MERGE_SLOT_GRANTED` decision remains
evidence of its own authority boundary; it is not a redundant requirement for
a normal phase transition covered by a valid standing grant.

### DIRECT_DELEGATED

Owner -> primary coordinator -> approved non-Nexus control plane (such as
DevSpace) -> exactly one bounded external worker -> independent coordinator
verification -> STOP.

No Nexus Task Card, Nexus lifecycle, CapabilityPlanner routing, Nexus Workforce
Admission, or Candidate lifecycle is required solely for this lane. The worker
cannot approve, integrate, merge, push protected refs, clean unrelated state,
release, make production/public claims, or act as its own required independent
verifier. `AUTO_CHAIN=false`. The primary coordinator independently inspects the
physical diff and reruns the applicable verifier; worker PASS is implementation
evidence only. Timeout/disconnect reconciles the same durable worker/session and
filesystem/Git/provider state before retry. Fail closed with
`DIRECT_DELEGATED_BLOCKED` when work exceeds these boundaries; do not silently
create a Task Card or switch to Nexus.

Eligibility, identity binding, isolation, retry, and escalation are defined in
`docs/agents/TASK_EXECUTION_CONTRACT.md`. Nexus Workforce Admission versus
non-Nexus external identity binding is defined in
`docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.

### GOVERNED

Use when work requires Nexus lifecycle/Candidate authority, changes
route/lifecycle/workforce authority, weakens security, changes migration/schema
or production-data authority, requires protected integration, or makes a
production/public claim. Load `docs/agents/TASK_EXECUTION_CONTRACT.md` plus the
active card. A Task Card binds scope/evidence; it never substitutes for program correctness.

## Conditional load map

Load the smallest authoritative surface that matches the task:

- Owner-authorized bounded `DIRECT_CANONICAL`: this file plus nearest nested
  authority; no Task Card/lifecycle state required.
- `DIRECT_DELEGATED`: this file plus
  `docs/agents/TASK_EXECUTION_CONTRACT.md` and, for worker/execution identity,
  `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.
- Governed mutation: `docs/agents/TASK_EXECUTION_CONTRACT.md` plus active card.
- Nexus model/provider selection, delegation, or routing: compact machine Workforce
  Admission receipt first; load the full policy/YAML only for policy changes,
  onboarding/calibration, promotion/demotion, admission audit, or an authority
  dispute. See `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.
- Claim/release/benchmark/audit/verifier work:
  `docs/agents/CLAIM_AND_RECEIPT_OVERLAY.md`.
- Novel repeatable failure with a prevention rule:
  `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`.
- LocalHeal or another nested subsystem: read its nearest nested `AGENTS.md`.
- OpenWiki is `derived_non_authoritative` navigation only; source, tests, or
  bound runtime evidence verify claims.

## Authority invariants

- `CapabilityPlanner` is the sole route and capability-selection authority.
  `HybridRouteDecision` is a Planner-derived decision contract/projection, not a
  second selector/router/planner; overlays and policy files cannot create one.
- Workforce admission constrains worker eligibility only; it does not select a
  route/capability or authorize self-approval.
- Missing verifier artifact/status or source hash fails claim gates closed.

## Response and tool discipline

- Follow `MUSE_PROTO.md` for response/domain tags.
- Prefer direct tools and concise evidence; do not narrate calls.
- On degenerate/repetitive output, stop mutation, preserve last verified state,
  and report `retry_required=true`.
