# Universal Agent Guidelines

Scope: Antigravity, Gemini, OpenClaw, Codex, and Claude.

- Repository authority: this root `AGENTS.md`.
- Task execution authority: the active Git-tracked Task Card under
  `tasks/<campaign-id>/`.
- Response/domain overlay: `MUSE_PROTO.md`; it never grants mutation authority.

## Canonical workspace and authority

- Daily source of truth is `/Users/jameschen/Workspace/nexus`.
- Canonical branch is `nexus/integration/main`; query HEAD at task start.
- `/Users/jameschen/Workspace/nexus-worktrees` is retired evidence, not an entry
  point. Do not create checkouts there.
- Before every task, run:
  `git rev-parse --show-toplevel`, `git branch --show-current`,
  `git status --short --branch`, and `git worktree list --porcelain`.
- Read this file, the campaign `INDEX.md`, and only the current-frontier card;
  verify the lifecycle task id, card path, and card hash before editing.
- Runtime state, reports, chat, and old worktrees cannot replace the Git-tracked
  Task Card or silently rewrite it. `AUTO_CHAIN=false` unless the index says so.
- If not anchored at the canonical root, stop mutation and re-anchor first.

## Safety and completion

- Preserve unrelated dirty state. Never reset, stash, clean, overwrite, or
  absorb ambiguous changes; use a clean governed Target when isolation is
  required.
- Do not hand-edit lifecycle JSON. Use the formal lifecycle API, CLI, or
  service surface. Do not push, merge protected main, or delete refs without
  explicit authority.
- Completion requires behavioral evidence, structural conformance, and any
  card-defined receipt/verifier. A report or green subset is not solve truth.
- A local or delegated model produces a candidate only; it cannot approve,
  promote, integrate, push, claim production readiness, or clean up.
- Workers may commit only their scoped card changes. Approval, integration,
  push, cleanup, and production/public claims remain separate authorities.
- Blocks are explicit: `RECOVERABLE_BLOCK` preserves the card for retry;
  `HARD_BLOCK` stops mutation until owner/spec authority resolves it. A block
  never promotes a Candidate or activates downstream work.

## Task-card and artifact governance

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

- Mutating task: `docs/agents/TASK_EXECUTION_CONTRACT.md` plus the active card.
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

## Authority invariants

- `CapabilityPlanner` and `HybridRouteDecision` remain route authority;
  overlays and policy files cannot create a second router.
- Workforce admission constrains eligible workers and escalation. Exact model
  identity, adapter preflight, parser, verifier, and receipt gates remain
  fail-closed.
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
