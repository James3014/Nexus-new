# Task Card: 01-map-model-workforce-policy.md

- issue: #121
- task_id: github-issue-121-model-workforce-impact-map
- status: ACTIVE
- base_sha: c7e60f4c6798554e51cbc322ebfaf89e2c5cc346
- authority_watermarks: 5252569113, 5252926064
- worker: codex_luna
- provider: codex
- model: gpt-5.6-luna
- role: main_engineering
- autonomy: L3_HISTORICAL
- context: nexus_bounded
- AUTO_CHAIN: false
- worker_may_commit: true
- worker_may_push: true
- worker_may_approve: false
- worker_may_integrate: false

## Admission Receipt

- decision: ALLOW
- policy_hash: 1ed56a4cd4d7ba43ce7dc7c0fbeab470f078b39d6561e580a03fd92826890b77
- binding_hash: 91ca4f0f843e4614415af273a656e3c72fffe5fd6ef17d4cebd46f455c2ca630
- aggregate_binding_hash: 06a1f75a735e6be31547718a8b8f03ae45990aa0bd031de0d80919405142cd8c
- missing_controls: []

## Bound Inputs

- `docs/testing/test_impact_map.md` blob: `37864efc71349dbef33391d2279aa5f1835fe969`
- `tests/ops/test_select_tests.py` blob: `1b6991069d9155debf042ef867f060c462799ff2`
- `scripts/ops/select_tests.py` read-only blob: `26496f9e7d3be7ab5d55b70e7bd76fe2f42768b7`
- `nexus/config/model_workforce.yaml` blob: `5ab744046cf638820cc35071b5c796582c7d716d`

## Objective

Add one authoritative impact-map row for `nexus/config/model_workforce.yaml` and a selector regression test proving exact, non-fallback selection of the two workforce contract suites.

## Allowed Files (Max 2 implementation/test files)

1. `docs/testing/test_impact_map.md`
2. `tests/ops/test_select_tests.py`

Task Card artifacts under this campaign directory do not count toward the two-file ceiling.

## Exact Mapping

`| nexus/config/model_workforce.yaml | tests/contracts/test_model_workforce_policy.py, tests/services/test_model_workforce_policy_loader.py | active | medium | workforce_policy_contract |`

Risk must remain `medium`. `high` would add the generic policy gate and violate the exact-two-target contract.

## Forbidden Scope

- `scripts/ops/select_tests.py`
- `scripts/ops/pr_impact_gate.py`
- `nexus/config/model_workforce.yaml`
- workforce runtime, loader, policy, route, provider, model, or admission semantics
- classifier truth, thresholds, fallback, Tier2, or exact-base comparison semantics
- PR #110 role semantics or path-specific bypasses
- `.nexus` index, statistics, history, or generated artifacts
- approval, merge, integration, release, or production claims

## RED / GREEN Contract

RED before the map row: the workforce YAML is unmatched and uses fallback. The new regression must require exactly the two workforce tests, `fallback_used=false`, `unmatched_paths=[]`, and no high-risk escalation.

GREEN after the map row: the selector returns exactly the two ordered workforce test targets; an unrelated control such as `docs/testing/unknown.md` remains unmatched and uses fallback; the real selector probe matches the unit-test result.

## Mandatory Verification Commands

1. `uv run pytest -q tests/ops/test_select_tests.py`
2. `uv run ruff check tests/ops/test_select_tests.py`
3. `uv run ruff format --check --preview tests/ops/test_select_tests.py`
4. `uv run python -m compileall -q tests/ops/test_select_tests.py`
5. `uv run python scripts/ops/select_tests.py --json nexus/config/model_workforce.yaml`
6. `git diff --check`
7. Exact changed-file and deletion audit against the bound base

## Exit Criteria

- The exact mapping and regression test are committed on `codex/issue-121-model-workforce-impact-map`.
- All mandatory verification commands pass.
- The complete diff contains only the two allowed implementation/test files and these Task Card artifacts.
- A PR is opened to `main`; the worker does not approve or merge it.

## Block Class

`RECOVERABLE_BLOCK` for environmental or CI failures. `HARD_BLOCK` for any required scope, risk, target, fallback, or authority change.

## Maximum Supportable Claim

`ISSUE_121_SELECTOR_MAPPING_CANDIDATE_ONLY`: the current model workforce policy path selects its exact two executable contract suites without fallback. This does not make PR #110 mergeable or suppress any architecture baseline failure.
