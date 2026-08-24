# TASK-526-H-HERMETIC-ROLLBACK-OBSERVATION-TIME — Remove one live-clock test dependency

    task_id: TASK-526-H-HERMETIC-ROLLBACK-OBSERVATION-TIME
    issue: 526
    repository: James3014/Nexus-new
    status: ACTIVE
    auto_chain: false
    claim_mode: MANUAL_DISPATCH
    base_main: 95fd37d7f240a46348497efd5006a6ba5643f73b
    work_branch: codex/issue-526-hermetic-rollback-observation-time
    owner_approval_expires_at: 2026-08-25T22:50:00Z
    claim_ceiling: TEST_HERMETICITY_SOURCE_CANDIDATE_ONLY

## Problem and authority

After PR #544 merged, a fresh Issue #526 verification run produced 256 passes
and one failure. The rollback-unloaded test builds a fixed receipt expiring at
`2026-08-24T00:00:00Z`; its `collect_gateway_observation` call omits the fixed
observation time, so the production freshness gate reads the live clock and now
rejects before every physical observer. The same test's later dispatch already
passes `2026-08-23T00:00:00Z`.

An AST family sweep found exactly one authority-aware test call with this
omission. This Card authorizes only the hermetic test correction. It grants no
production-code, bundle, Gateway, DevSpace, service, host-effect, approval,
merge, activation, release, or production authority.

## Exact worker mutation scope

Modify only:

- tests/ops/test_mcp_gateway_durable.py

Create/delete none. The coordinator-authored Card and INDEX update are authority
setup, not worker implementation scope. Do not extend any receipt expiry, derive
fixture time from the wall clock, monkeypatch a global clock, or weaken a
freshness/revocation/effect gate.

## Required correction

In
`test_collect_dispatch_unloaded_rollback_skips_health_and_launch_effects`, pass
the existing fixed valid instant exactly as:

    observation_time="2026-08-23T00:00:00Z"

to the `collect_gateway_observation` call. Change no other production or test
behavior.

## Acceptance and negative controls

- the formerly red rollback-unloaded node passes after the clock boundary;
- the freshness/revocation pre-observer negative control remains green;
- the rollback stale-authority zero-effect negative control remains green;
- the contract future/stale bundle validity negative control remains green;
- the complete Gateway contract/manager suite passes all 257 nodes;
- no test is renamed, skipped, xfailed, deselected, or weakened;
- physical diff is limited to the coordinator Card/INDEX plus the one worker
  test file, with zero deletions.

## Verification

    uv run pytest -q tests/ops/test_mcp_gateway_durable.py::test_collect_dispatch_unloaded_rollback_skips_health_and_launch_effects
    uv run pytest -q tests/ops/test_mcp_gateway_durable.py::test_host_authority_freshness_and_revocation_fail_before_observer tests/ops/test_mcp_gateway_durable.py::test_rollback_missing_observer_and_stale_authority_have_zero_effects tests/contracts/test_gateway_deployment_contract.py::test_bundle_selection_rejects_future_or_stale_validity
    uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
    uv run ruff check tests/ops/test_mcp_gateway_durable.py
    git diff --check
    git diff --name-status 95fd37d7f240a46348497efd5006a6ba5643f73b...HEAD

Independent review must confirm the fixed observation instant, preserved stale
negative controls, exact scope, and claim ceiling before push or PR.

## Forbidden actions

- do not edit production source, bundle JSON, Host Card, or other tests;
- do not invoke plist, launchctl, Gateway, DevSpace, or another service;
- do not push, open/approve/merge a PR, or alter protected refs;
- do not self-approve or advance TASK-526-HOST-1;
- `AUTO_CHAIN=false`; stop after the committed Candidate report.
