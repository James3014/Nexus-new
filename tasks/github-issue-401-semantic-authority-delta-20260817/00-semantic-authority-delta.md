---
task_id: ISSUE-401-SEMANTIC-AUTHORITY-DELTA-01
issue: 401
repository: James3014/Nexus-new
status: ACTIVE
baseline_revision: 0de07f518538d8f5ec9049f3f2ab04ebb3f92168
rebind_base_revision: 0de07f518538d8f5ec9049f3f2ab04ebb3f92168
historical_candidate_head: f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1
execution_lane: GOVERNED_GITHUB_ISSUE_BRANCH
worker_role: primary_coordinator_current_main_rebind
worker_identity: current_owner_authorized_primary_coordinator
historical_rebind_worker_identity: codex_luna
independent_reviewer_role: separate_current_reviewer
claim_intent: MANUAL_DISPATCH
claim_enforcement_state: PROJECTION_ONLY
claim_mode: MANUAL_DISPATCH
AUTO_CHAIN: false
max_files: 7
max_implementation_files: 5
allowed_files:
  - AGENTS.md
  - docs/agents/TASK_EXECUTION_CONTRACT.md
  - nexus/contracts/semantic_authority_delta.py
  - tests/contracts/test_semantic_authority_delta.py
  - tests/ops/test_bootstrap_authority_files.py
  - tasks/github-issue-401-semantic-authority-delta-20260817/INDEX.md
  - tasks/github-issue-401-semantic-authority-delta-20260817/00-semantic-authority-delta.md
authorized_deletions: []
worker_may_approve: false
worker_may_integrate: false
worker_may_merge: false
claim_ceiling: SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY
---

# Issue #401 — semantic authority delta contract, current-main rebind

## Goal

Rebuild the already-reviewed Issue #401 semantic-authority-delta Candidate on the exact current main without merging or blessing stale PR #402. The new Candidate adds one pure fail-closed predicate plus normative authority wording and executable contract tests.

A bounded evidence/provenance writeback may remain in the existing `DIRECT_CANONICAL` lane only when every effective authority invariant is explicitly proven unchanged. Any ambiguity resolves to `GOVERNED_REQUIRED`.

## Current source and lineage binding

- Owner direction in the current session prioritizes #401 first and requires current-main rebind rather than direct merge of stale PR #402.
- Current source is `main@0de07f518538d8f5ec9049f3f2ab04ebb3f92168`, tree `5bdf2cd1261a62e2177cc719a8f4d10351cd30b7`.
- Historical design/Candidate evidence remains PR #402 head `f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1`; its old acceptance is evidence lineage only, not current acceptance.
- This campaign remains governed because it changes repository execution-lane classification semantics. It cannot use the proposed predicate to downgrade its own execution.
- Current active open-PR overlap scan found no overlap with the seven allowed paths among the recently active open PR frontier checked before mutation.
- The live Nexus Gateway is upstream-stale and is not used to mint or substitute authority for this rebind.
- The mutation is bound in DevSpace to Core session `cms_a0308ade00164cbea07ff6faaaa76808` and current source identity.

## Required predicate

Create `nexus.contracts.semantic_authority_delta` with:

```text
classify_semantic_authority_delta(envelope)
  -> DIRECT_CANONICAL | GOVERNED_REQUIRED
```

The classifier must ignore filenames, line counts, model quality, and historical prose as authority selectors. `DIRECT_CANONICAL` is allowed only when Owner authorization, evidence/provenance identity, append-only semantics, no deletion/rewrite/mutation/authority transition, every enumerated authority dimension, bounded verification, changed-file audit, no-deletion audit, and diff-check obligations are all explicitly safe. Missing, false, unknown, malformed, contradictory, or unprovable input fails closed.

`AUTHORITY_PRESERVING_EVIDENCE_WRITEBACK` is a semantic classification only. It is not a fourth execution lane, never produces `DIRECT_DELEGATED`, and does not approve, integrate, merge, release, deploy, or make production/public claims.

## Authority dimensions

At minimum the predicate must bind unchanged state for autonomy; roles/capabilities; Workforce admission; provider/model/worker authority; default route; semantic authority lineage; parser/verifier; independent review; forbidden/protected-ref actions; claim ceilings; CapabilityPlanner; lifecycle; Candidate; approval; integration; merge; release; security; migration/schema; production-data; production; public claim.

## Future-only boundary

This rule is future-only after independent acceptance and integration. It does not retroactively relabel PR #402, the motivating MiMo history, or any prior writeback.

## Implementation constraints

1. Preserve the current three-lane model and current BOOTSTRAP operating-mode semantics.
2. Do not integrate the predicate into a runtime selector in this Candidate.
3. Do not change Workforce policy/YAML, planner, lifecycle code, CI workflows, break-glass semantics, or files outside the allowlist.
4. Zero deletions.
5. Candidate, independent acceptance, approval, integration, merge, release, runtime and production remain separate.

## Machine policy overlay

```json
{
  "allowed_paths": [
    "AGENTS.md",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "nexus/contracts/semantic_authority_delta.py",
    "tests/contracts/test_semantic_authority_delta.py",
    "tests/ops/test_bootstrap_authority_files.py",
    "tasks/github-issue-401-semantic-authority-delta-20260817/INDEX.md",
    "tasks/github-issue-401-semantic-authority-delta-20260817/00-semantic-authority-delta.md"
  ],
  "forbidden_paths": [],
  "max_files_touched": 7
}
```

## TDD evidence

- RED on exact current base: `uv run --frozen pytest -q tests/contracts/test_semantic_authority_delta.py tests/ops/test_bootstrap_authority_files.py` reached collection and failed with `ModuleNotFoundError: nexus.contracts.semantic_authority_delta` before the implementation module was added.
- The earlier system-Python `No module named pytest` result is toolchain evidence only and is not counted as the RED witness.

## Mandatory verification

```text
python3 -m pytest -q tests/contracts/test_semantic_authority_delta.py tests/ops/test_bootstrap_authority_files.py
python3 -m compileall -q nexus/contracts/semantic_authority_delta.py tests/contracts/test_semantic_authority_delta.py
python3 scripts/ops/agent_protocol_check.py --task-card tasks/github-issue-401-semantic-authority-delta-20260817/00-semantic-authority-delta.md --strict-boundary --check-files AGENTS.md,docs/agents/TASK_EXECUTION_CONTRACT.md,nexus/contracts/semantic_authority_delta.py,tests/contracts/test_semantic_authority_delta.py,tests/ops/test_bootstrap_authority_files.py
git diff --check
git diff --name-status 0de07f518538d8f5ec9049f3f2ab04ebb3f92168 HEAD
```

## Exit conditions

Candidate-ready requires exact allowlist, zero deletions, focused semantic/authority tests, bootstrap witnesses, strict-boundary protocol check, clean diff check, physical changed-file audit, and an independent exact-head review. Maximum pre-acceptance claim is `SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY`. `AUTO_CHAIN=false`.
