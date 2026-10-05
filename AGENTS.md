# Universal Agent Guidelines

Scope: all coding agents.

## RepoLearn activation

- RepoLearn: `ENABLED`; source `James3014/repo-learning`; mode `guided`.
- Contract: `g5-learning-control-loop-v3` / `8fa154f05bb3a5a1652d8a0b8388e718ce685257a2da26e2121c2ce52a9855ac`.
- If unavailable, continue normally without weakening authority.

## Authority bootstrap

- Repository authority: root `AGENTS.md`.
- Direct authority: an explicit current Owner request may authorize a bounded
  `DIRECT_CANONICAL` change that does not require a Task Card or lifecycle state.
- Direct delegated authority: an explicit current Owner request may authorize one
  bounded `DIRECT_DELEGATED` milestone through an approved non-Nexus control
  plane, without a Task Card or Nexus lifecycle state solely because a worker is
  delegated.
- Governed authority: the active Git-tracked Task Card under `tasks/<campaign-id>/`.
- `MUSE_PROTO.md` is response/domain overlay, never mutation authority.

For new work, read `docs/governance/current_operating_mode.yaml` before
choosing an execution lane. Within the file's declared scope, its default lane
selection applies unless the work crosses a listed governed-escalation boundary
or the Owner explicitly selects a different lane. Existing active work keeps its
current execution contract; no mid-task lane switch.
If the operating-mode file is missing, invalid, or ambiguous, fail closed to an
explicit current Owner lane decision rather than guessing.

The operating mode selects only the engineering execution lane. It cannot select
or override a `CapabilityPlanner` route/capability, worker/model eligibility,
verification, approval, integration, release, or production authority.

### Current self-hosting stabilization semantics

`mode: BOOTSTRAP` means self-hosting stabilization; G10 alone does not change the default
execution lane. Transports never choose or widen lane authority. Once one attempt has entered governed authority, missing, stale, expired,
unavailable, or failed authority or transport must never silently downgrade that attempt
to direct authority; block, rebind, reconcile, or start a separately
Owner-authorized recovery attempt with a new identity.
`NEXUS_GOVERNANCE_DEFAULT_READY` is an Owner-only transition decision. It is not
inferred from G10, tests, an agent, a Task Card, CI, or runtime state.

## Repository collaboration authority (GitHub)

- Repository `James3014/Nexus-new`; collaboration branch `main`. Never merge runtime history into `main` to align SHAs.
- G12 Fast Start advisory-cache gate: before any GitHub Issue implementation source/test body reads, consult #549 as `ADVISORY_CACHE_ONLY`. `BLOCKED`, `HOST_REBIND_REQUIRED`, `NEEDS_DECISION`, `EVIDENCE_BLOCKED` need fresh metadata-only rebind and must not read diff, patch, or implementation bodies; if still non-ready, stop. `READY_CANDIDATE` is not authority; fresh Issue/dependencies/main/host and normal gates remain required. Missing, stale, malformed, or contradictory cache fails closed to normal authoritative discovery. Fast Start consumers are read-only for #549/product Issues; see `docs/agents/TASK_EXECUTION_CONTRACT.md`. Cache/metadata never replaces source/test evidence or canonical authority.
- **Project-entry invariant (#842):** on the first explicit Nexus/project-bound
  action for a repository + Issue, the primary coordinator MUST call
  `nexus_project_entry` before any Nexus-governed effectful action, regardless of
  phrasing (`continue ... #N`, `處理 #N`, `幫我修 #N`). Result is pre-execution evidence only.
- If Project Entry is not `READY_TO_EXECUTE`, surface its single canonical
  blocker and STOP governed effects. Do not jump directly
  to `nexus_task_card_create` or worker/Candidate mutation; recovery stays with #806 or #526.
- A Project Entry `READY_TO_EXECUTE` result is pre-execution evidence, not proof
  the next action exists on the bound surface. Before the first `GOVERNED` effect,
  prove it is present; `nexus_owner_standing_grant_issue` must be present
  before `nexus_task_card_create` is attempted. If absent, classify a host/action-surface binding gap and STOP before the
  effect (no `OWNER_AUTHORITY_REQUIRED:RECEIPT_MISSING` retries). Surface convergence is a transport precondition and grants no authority.
- Switching repository or Issue invalidates the prior Project Entry binding for
  governed effects and requires a fresh `nexus_project_entry` call. Direct lanes
  remain governed by their existing lane rules.
- A Ready GitHub Issue is a worker-neutral bounded collaboration contract; it
  does not select local lifecycle. An eligible governed worker implements on an
  issue branch, pushes only it, and opens a PR to `main`. Provider/model names
  are not ownership identities.
- Claim metadata: `claim_intent`, `claim_enforcement_state`,
  `claim_mode`; `PROJECTION_ONLY` or `UNKNOWN` resolves to `MANUAL_DISPATCH`. assignees, labels, comments, Project fields, branch names, and worker prose cannot authorize mutation.
- No agent direct-pushes, force-pushes, or deletes `main`; delegated workers
  never approve or merge their Candidate; only the primary coordinator merges. Merge follows lane, not repository.
  DIRECT uses `git_merge_pull_request` after current Owner confirmation and all
  exact gates; no Task Card, third-party approval, acceptance receipt/hash,
  standing grant, or completion loop is required. GOVERNED retains independent
  acceptance, machine provenance, `GITHUB_MERGE` grant, and completion loop.
- A non-transferable Owner standing grant for bounded Ready Issues in one durable scope grants no delegated-worker merge authority;
  it may create a missing Task Card only for a Ready Issue with frozen paths and `AUTO_CHAIN=false`.
- Every coordinator merge requires fresh SHA-bound PR/head/base/diff, current
  `main`, successful checks, branch protection, current Owner confirmation, and
  expected-head/CAS; drift fails closed. Governed merge also requires
  independent acceptance, machine provenance, and current grant;
  `MERGE_INTENT` is evidence, not authority.
- **Main-movement decision invariant:** exact-base movement invalidates the current
  merge attempt by default; it does **not** by itself invalidate the Candidate,
  PR, or verified evidence. Before rebasing or recreating a PR solely because
  `main` moved, the coordinator MUST apply #441 requalification to exact changed-main paths.
  If every dimension is `REUSE_UNAFFECTED`, keep the same Candidate and PR head.
  `RECHECK_AFFECTED` reruns only affected dimensions; a new integration head needs
  semantic overlap, authority drift, or `IMPACT_UNKNOWN`.
  `base != current main` alone is never sufficient evidence. Without
  requalification evidence, stop with a transport/evidence capability gap.
- From PR #1061, protected-merge PRs carry `nexus.merge_lane_binding.v1`;
  a `GOVERNED` card needs `nexus.owner_execution_lane_rebind.v1` to reach the
  direct sink. `Trusted verifier (default branch)` runs
  `scripts/ops/trusted_merge_lane_gate.py`.
- `github_complete_pull_request` mints no authority; it is not a second merge controller.
- The coordinator asks the Owner again only for contract widening, weaker
  security, a new irreversible external effect, or release/production claims.

## Repository baseline

- Before mutation record root, branch, HEAD, dirty state, and worktree topology
  (`git rev-parse --show-toplevel`, `git worktree list --porcelain`). Preserve unrelated dirty state.

## Governance boundary

- Implementation, commit, Candidate, verification, approval, integration, push,
  and release are distinct stages. A GitHub PR Candidate is an Issue-branch
  commit; a local lifecycle Candidate is receipt-bound Target output. Neither
  supplies authority to the other.

## Safety and completion

- Do not hand-edit lifecycle JSON or protected control-plane state.
- Completion requires behavioral evidence and applicable verifier; report changed files/evidence; green subset is not solve truth.
- Models give candidate evidence only; cannot approve, merge, certify production.
- If the self-hosting/controller identity contract is itself under repair, stop
  that path and use the bounded external bootstrap procedure in
  `docs/governance/rollback_runbook.md`; it creates no second authority and
  never implies approval, integration, push, reload, or activation.
- `REVISE` permits bounded correction; `RECOVERABLE_BLOCK` preserves retry;
  `HARD_BLOCK` pauses affected mutation. Reviewer block/card omission is not
  `REJECTED`; only an authorized decision-maker may reject.

## Execution lanes

### DIRECT_CANONICAL

Owner -> primary agent -> one bounded direct change in the canonical checkout.
Eligible direct work needs no Task Card, lifecycle state, or Candidate.
Keep the diff scoped; run checks plus `git diff --check`.

`AUTHORITY_PRESERVING_EVIDENCE_WRITEBACK` is a semantic authority classification
inside `DIRECT_CANONICAL`, not a fourth execution lane. A future additive
evidence writeback stays direct only if Owner authorization and append-only
semantics are proven and autonomy, provider/model/worker authority, default
route, `CapabilityPlanner`, parser/verifier, claim, security,
migration/schema, and production-data authority are unchanged. Filename or
line-count never establish that. Any changed, missing, malformed, contradictory,
unknown, or unprovable dimension fails closed to `GOVERNED_REQUIRED`. It never
returns `DIRECT_DELEGATED`, approves nothing, and applies only to future
classifications after integration into `main`, with no retroactive effect.

Direct work becomes governed when it crosses an `escalate_to_governed_when`
boundary in `current_operating_mode.yaml` (route, Workforce, lifecycle,
security, schema, production, release, irreversible external effect,
break-glass, non-PR protected ref, or explicit Owner `GOVERNED`). delegation alone does not
escalate an otherwise eligible `DIRECT_DELEGATED` task.

### DIRECT_DELEGATED

Owner -> primary coordinator -> approved non-Nexus control plane -> one
bounded external worker -> independent verification -> optional exact
Owner-confirmed protected PR merge -> STOP.

No Nexus Task Card, Nexus lifecycle, CapabilityPlanner routing, Nexus Workforce
Admission, or Candidate lifecycle is required solely for this lane. The worker
cannot approve, merge, push protected refs, or verify itself.
`AUTO_CHAIN=false`. The primary coordinator independently inspects the
physical diff and reruns the applicable verifier; worker PASS is implementation
evidence only. Fail closed with `DIRECT_DELEGATED_BLOCKED` beyond these boundaries. Details: `docs/agents/TASK_EXECUTION_CONTRACT.md`,
`docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.

### GOVERNED

Use when work requires Nexus lifecycle/Candidate authority, crosses a high-risk
boundary above, or the Owner selects `GOVERNED`. An exact
Owner-confirmed protected PR merge is not by itself a governed escalation. Load
`docs/agents/TASK_EXECUTION_CONTRACT.md` plus the active card; a Task Card never
replaces program correctness.

## Conditional load map

- Nexus model/provider selection, delegation, or routing: compact Workforce
  Admission receipt first; full policy/YAML only for policy changes,
  onboarding, audit, or an authority dispute. See `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`.
- Claim/release/benchmark/audit/verifier work: `docs/agents/CLAIM_AND_RECEIPT_OVERLAY.md`.
- Novel repeatable failure with a prevention rule: `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`.

## Authority invariants

- `CapabilityPlanner` is the sole route and capability-selection authority;
  `HybridRouteDecision` is a derived projection, not a router.
- Workforce admission constrains worker eligibility only; it selects no
  route/capability and authorizes no self-approval.
- Missing verifier artifact/status or source hash fails claim gates closed.
- Follow `MUSE_PROTO.md` for response tags. On degenerate output, stop
  mutation and report `retry_required=true`.


## Nexus Core issue-bound completion evidence

- This repository is enrolled in the standalone `nexus-certify` Golden Path through `.nexus-core/config.toml`.
- For mutation work tracked by a repository-local GitHub Issue, run `nexus-certify issue-init --issue <N>` before relying on Issue-bound completion evidence, and run `nexus-certify issue-check --issue <N>` before claiming engineering completion.
- This binding is Evidence Trust + Completion only. It does not select the execution lane, route, worker/model, Candidate acceptance, merge, release, deployment, or production authority.
- DIRECT work remains transport-neutral. A Core mutation session is not required solely because repository files are being changed.
