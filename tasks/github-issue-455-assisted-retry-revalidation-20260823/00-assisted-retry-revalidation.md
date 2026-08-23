# Task Card — Issue #455: Assisted Retry Revalidation

```yaml
task_id: ISSUE_455_ASSISTED_RETRY_REVALIDATION
issue: 455
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 67521fe91e990f4e140642984c743dd50a408e84
base_tree: f6d6c2bf0912ff4a63d3c10a089910f95eab3c12
work_branch: codex/issue-455-assisted-retry-revalidation
claim_ceiling: ASSISTED_RETRY_REVALIDATION_CLOSED_AT_SOURCE_TEST_CANDIDATE
```

## Objective

Make assisted retry revalidate the original bounded action authority and mint
fresh retry identity before any workspace creation, durable write, or provider
process launch.

## Authority and workforce binding

Issue #455, GitHub comment `5381859742`, and this committed card authorize
implementation/Candidate evidence on the named issue branch only.
`AUTO_CHAIN=false`. No approval, merge, runtime activation, release,
production, or public claim is authorized.

Fresh compact Workforce receipt:

- worker: `agy_flash_medium`
- provider/model: `agy / gemini-3.6-flash-medium`
- state/availability/autonomy: `REGISTERED_CONDITIONAL / AVAILABLE / L1`
- roles: `bounded_candidate_generation, fast_bounded_implementation, focused_verification`
- policy hash: `a1917b29d890c553fcf9fad1ea1eb3d0fdf7a88e917dad3d478fe2e1bb5e35c2`

Exact runtime admission and physical adapter/model preflight must return
`ALLOW` before implementation dispatch.

## Exact mutation scope

Maximum two files:

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

Zero deletions. No second validator. `#143` remains untouched.

## Requirements

1. Before `mkdtemp`, `_assist_write`, or `Popen`, validate the persisted
   `TASK_RUN` action and its bound request using existing canonical request
   verification and `pre_action_guard`.
2. Revalidate current tool manifest, task/card/contract identity, allowed
   scope, and current HEAD.
3. Reconstruct the provider command from the validated bound request; never
   relaunch caller- or storage-substituted command bytes.
4. Mint a fresh `TASK_RETRY` envelope with fresh attempt, action, and
   idempotency identities while preserving the same semantic task.
5. Preserve candidate-only, bounded authority and existing retry history.

## Required controls

Each negative case must fail before any workspace/write/process side effect:

- stale or tampered envelope/request hash;
- tool-manifest drift;
- task/card/contract drift;
- command substitution;
- HEAD drift;
- allowed-scope drift.

A valid same-task retry must pass with fresh transport identity and the
recomputed canonical command.

## Verification commands

```bash
uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k retry
git diff --check
git diff --name-status
```

## Commit and block policy

Worker may commit only the two scoped files. No push, merge, approval, cleanup
of unrelated state, or `main` mutation.

- `HARD_BLOCK`: source/base/scope drift, need for another source path,
  inability to reuse canonical validation, side effect before rejection,
  deletion, or required verifier failure.
- `RECOVERABLE_BLOCK`: transient infrastructure failure with unchanged
  source and reconciled evidence.
- `REVISE`: bounded correction within the frozen scope.

Maximum claim:
`ASSISTED_RETRY_REVALIDATION_CLOSED_AT_SOURCE_TEST_CANDIDATE`.
