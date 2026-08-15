---
task_id: github-issue-291-memory-route-authority-isolation-20260815
issue: 291
repository: James3014/Nexus-new
baseline_revision: cdf2570ede5ae218f36f886b696c8da45458043a
status: COMPLETE
terminal_state: TERMINAL_RECONCILIATION
reconciled_main: ccd23defe9aa5905d26f34a865746c1eff7d039f
readiness_marker: LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED
AUTO_CHAIN: false
claim_ceiling: LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED_PROVEN_ONLY
implementation_files:
  - nexus/core/capability_selector.py
  - tests/core/test_capability_selector_route_authority.py
governance_files:
  - tasks/github-issue-291-memory-route-authority-20260815/INDEX.md
  - tasks/github-issue-291-memory-route-authority-20260815/github-issue-291-memory-route-authority-isolation-20260815.md
allowed_files:
  - nexus/core/capability_selector.py
  - tests/core/test_capability_selector_route_authority.py
max_files: 2
authorized_deletions: []
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
worker_may_merge: false
candidate_lane:
  worker: opencode_deepseek_v4_flash
  model: opencode/deepseek-v4-flash-free
  role: bounded_candidate_generation
  mutation_intent: false
  autonomy: L1
  external_verification_required: true
  admission_policy_hash: 8bc154848ac95b2478045c0d4568fcbb208263d4f46232d8b671a88b4a13bdca
  admission_binding_hash: b1f2ecb41facc1a4af95f3d044828289ec124b99372a50f9f45fb5ad30d415b8
  admission_aggregate_hash: 4f3e923f2a2499ebc3916ad95c2bd44140b5a93b722044b328d0e48517f3e094
---

# Issue #291 — isolate legacy memory route authority

## Objective

Generate one bounded Candidate that prevents the legacy dynamic-learning
policy from adding or removing runtime capabilities inside
`CapabilitySelector`. `CapabilityPlanner` remains the sole canonical route and
capability-selection authority.

## Frozen source finding

On baseline main, `OutcomeMemoryManager` writes promoted/penalized capability
metadata. The Planner-owned loader applies only bounded advisory budget input,
but `nexus/core/capability_selector.py` separately consumes the artifact and
directly appends promoted registry capabilities or removes penalized
capabilities. That selector step is classified `REMOVE_FROM_ROUTE_AUTHORITY`.

Writer persistence, the canonical loader, Planner policy application, and
Planner signal snapshots are compatibility/advisory surfaces and are outside
this slice.

## Required behavior

- A promoted capability in the legacy policy cannot append itself to the
  canonical runtime capability set outside `CapabilityPlanner`.
- A penalized capability cannot remove an otherwise-selected capability
  outside `CapabilityPlanner`.
- Missing, malformed, foreign-schema, non-PASS, or tampered dynamic policy
  leaves the selector plan unchanged.
- Existing skip/forbidden/ethical/lite-route behavior remains unchanged.
- No second Planner, Router, promotion authority, learned scheduler, or route
  policy is introduced.

## Forbidden

- Changes to `nexus/core/router.py`, `nexus/engine/**`, `nexus/learning/**`, or
  `nexus/config/**`.
- New store, Planner, Router, selector, promotion, provider, model, Workforce,
  approval, integration, merge, runtime, release, or production authority.
- File deletion or scope widening.

## Verification

```text
uv run pytest -q tests/core/test_capability_selector_route_authority.py tests/research/test_capability_selector.py
git diff --check
```

Audit the exact two implementation/test files and zero deletions. Independent
verification must confirm that `CapabilityPlanner` remains the sole route
authority.

## Exit

A bounded, isolated Candidate diff in exactly the two allowed files with
focused tests passing. The DeepSeek worker cannot commit, push, approve,
integrate, merge, or claim runtime/release/production truth. Publication and
acceptance are separate coordinator gates.

`AUTO_CHAIN=false`. Claim ceiling:
`memory_route_authority_candidate_pr_only`.

## Terminal receipt

The preceding Exit text is the preserved historical Candidate boundary. PR294
head `27229058093ea7f20e4ed9a1c1afff505e397ec1` was independently accepted and
merged as `c57c183f4f1c3701ccc1e3731ea498d60b2297d4`; this reconciliation is bound
to current main `ccd23defe9aa5905d26f34a865746c1eff7d039f`. The merged change contained
exactly four files and zero deletions. All six required exact-head workflows
completed successfully, and the clean exact-main focused suite passed 18
tests.

Legacy dynamic-learning-policy add/remove authority is isolated from
`CapabilitySelector`; `CapabilityPlanner` remains the sole route and
capability-selection authority. Terminal marker:
`LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED`. Claim ceiling:
`LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED_PROVEN_ONLY`, limited to
repository-contained source and tests. `AUTO_CHAIN=false`; no runtime,
Workforce, provider, release, or production truth is claimed.
