---
campaign_id: CAMPAIGN-NEXUS-401-SEMANTIC-AUTHORITY-DELTA-20260817
issue: 401
repository: James3014/Nexus-new
status: READY_FOR_EXECUTION
baseline_revision: 8c2584d6053dd1f04dc87333f807fbea1726545e
rebind_base_revision: 8c2584d6053dd1f04dc87333f807fbea1726545e
correction_start_revision: 63b9f75f6a446a06246fc2c2c6cfa7dcf2b395ab
rebind_lineage:
  original_candidate_implementer: Antigravity
  original_candidate_identity: antigravity@gemini.local
  rebind_worker: Luna
  rebind_worker_identity: codex_luna
  independent_reviewer: separate_current_reviewer
current_frontier: ISSUE-401-SEMANTIC-AUTHORITY-DELTA-01
AUTO_CHAIN: false
parallel_execution: true
claim_ceiling: SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY
---

# Issue #401 semantic authority delta campaign

## Goal

Add one fail-closed semantic contract that distinguishes an authority-preserving
evidence writeback from an authority-changing mutation. The safe result remains
inside the existing `DIRECT_CANONICAL` lane; every changed, missing, malformed,
contradictory, or unprovable authority dimension resolves to existing
`GOVERNED` handling.

## Frontier

| Task | Status | Outcome | Verification | Claim ceiling |
|---|---|---|---|---|
| `ISSUE-401-SEMANTIC-AUTHORITY-DELTA-01` | `ACTIVE` | pure semantic predicate, normative authority wording, positive/negative contract tests | focused pytest, bootstrap authority witnesses, path/deletion audit, `git diff --check`, independent review | `SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY` |

## Authority and parallelism

- Current Owner direction prioritizes Issue #401 and selects Luna as the
  bounded implementation worker.
- This campaign is governed because it changes repository execution-lane
  classification authority. It cannot use its own proposed rule to downgrade
  this historical execution.
- Implementation is isolated on
  `codex/issue-401-semantic-authority-delta`; `AUTO_CHAIN=false`.
- The original Candidate commits (`b5ef0755`, `078611cb`, `44ef467f`,
  `5ba9542b`, `bbef2abe`, `53190a32`) were authored by Antigravity
  (`antigravity@gemini.local`). This rebind and correction are performed by
  Luna (`codex_luna`); Git commit author metadata is not used to relabel that
  lineage. Independent review remains a separate current reviewer identity.
- PR #113 currently overlaps `AGENTS.md` but is stale/conflicting and is not an
  active mutation owner in this worktree. Candidate formation may proceed;
  acceptance/integration/merge remain blocked until that overlap is freshly
  resolved or explicitly retired. This campaign must not touch PR #113.
- Issue #400 and other non-overlapping work may proceed in parallel.

## Non-goals

No fourth execution lane; no CapabilityPlanner/router/workforce/lifecycle
selector change; no self-hosted lane integration; no historical MiMo lineage
rewrite; no protected merge, release, production, or public-claim authority.
