# Task Card 09: Context Budget and Conditional Overlay Gates

## Identity

- task_id: `context-budget-and-overlay-gates`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- depends_on: `orphan-workspace-reconciliation` read-only evidence
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Implement the supplied MG/Nexus required-content optimization before lifecycle
P2. Keep `AGENTS.md` as compact L0 repository governance, move task execution,
workforce, claim/receipt, and learning details into conditional overlays, and
prove that normal tasks use machine admission/receipts instead of full policy
manifest reading.

## Required deliverables

1. Preserve canonical root, authority precedence, Task Card discovery, dirty-tree
   safety, candidate/approval separation, evidence-backed completion, default
   deny for persistent artifacts, targeted retrieval, and block semantics in L0.
2. Add `docs/agents/TASK_EXECUTION_CONTRACT.md` for task-card/lifecycle/commit
   details and conditional workforce/claim/learning overlays with explicit
   authority metadata.
3. Make the load map explicit: mutating task -> task contract; model/provider
   selection -> compact machine admission first; LocalHeal -> nested overlay;
   claim/release -> claim overlay; novel failure -> learning overlay.
4. Remove fixed global `allowed_paths`, `forbidden_paths`, and `max_files_touched`
   values from root governance; the active Task Card and machine baseline own
   scope limits.
5. Add semantic/context-budget regression tests, not a line-count-only claim:
   authority invariants, no fixed worktree/legacy sync paths, conditional full
   policy loading, and compact-vs-legacy briefing behavior.

## Allowed files

- `AGENTS.md`
- `MUSE_PROTO.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`
- `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`
- `docs/agents/CLAIM_AND_RECEIPT_OVERLAY.md`
- `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`
- `tests/ops/test_bootstrap_context_budget.py`
- `tests/ops/test_nexus_enforced_briefing.py`
- `tasks/bootstrap-authority-convergence/INDEX.md`

## Forbidden scope

- Do not modify CapabilityPlanner, UnifiedRuntime routing, WorkerRegistry,
  Gateway provider behavior, lifecycle P2 runtime, claim semantics, or model
  authority.
- Do not remove safety, receipt, verifier, approval, integration, push, or
  cleanup gates; overlays may narrow context but never widen authority.
- Do not create a second workforce/policy router or duplicate the existing
  `workforce-compact-surface` card.
- Do not use a line-count reduction as proof without semantic invariant tests.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_bootstrap_context_budget.py tests/ops/test_bootstrap_authority_files.py tests/ops/test_nexus_enforced_briefing.py
bash -n scripts/ops/_nexus_enforced_briefing.sh
git diff --check
```

## Exit criteria

The L0/L1/L2 split is physically present, normal-task bootstrap no longer
requires full workforce YAML/policy loading, all authority invariants remain
machine-tested, and the scoped commit is owner-reviewable. Lifecycle P2 stays
blocked until this card is integrated.

## Evidence

- `15 passed` from the exact bootstrap/context/briefing pytest command.
- `bash -n scripts/ops/_nexus_enforced_briefing.sh` passed.
- `git diff --check` passed.
- L0 `AGENTS.md` is 5,294 bytes; four L2 overlays total 6,101 bytes.
- Existing briefing test now derives the current frontier from the campaign
  index instead of pinning a completed card id.

## Block classification

- `RECOVERABLE_BLOCK`: test or local tooling failure with all changes preserved.
- `HARD_BLOCK`: slimming would remove an authority/evidence gate or create a
  second runtime policy authority.
