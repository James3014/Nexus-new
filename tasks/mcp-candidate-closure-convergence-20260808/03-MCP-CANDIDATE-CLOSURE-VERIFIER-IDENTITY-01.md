# Task Card: MCP-CANDIDATE-CLOSURE-VERIFIER-IDENTITY-01

artifact_authority: current
task_id: `MCP-CANDIDATE-CLOSURE-VERIFIER-IDENTITY-01`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Repair the existing Candidate integration staging verifier without adding a
second integration authority. A live, independently accepted Candidate merged
cleanly with canonical HEAD and passed its full verifier with the admitted
`/opt/homebrew/bin/python3`, but `ControlledIntegrationManager` re-parsed the
contract string `python3 ...` through the LaunchAgent ambient `PATH`, resolved
`/usr/bin/python3`, and failed because that unverified interpreter does not
contain pytest.

Bind every staging verifier to the ordered executable identity, argv, and
executable SHA-256 already persisted in the Candidate's successful
`verified_receipt.verifier_evidence`. Reject missing, malformed, reordered,
non-absolute, non-executable, command-mismatched, argv-mismatched, or SHA-drifted
evidence before a staging verifier or Git apply. Execute with `shell=false`, a
bounded environment, and a timeout. Failure evidence may expose only bounded
status, exit code, and stdout/stderr SHA-256 digests, never raw output or
secrets. Do not fall back to ambient `PATH`.

Support recovery of the exact `INTEGRATION_FAILED_PRE_APPLY` state created by
this defect. A fresh one-shot `CANDIDATE_INTEGRATE` approval may rebind only
when no merge/apply occurred, no integration result SHA exists, the failure
stage is `PRE_APPLY`, and branch HEAD before/after are identical. Preserve the
old closure, grant, and integration failure in append-only history, then return
the state to `APPROVED`/rebind-ready without applying. Reuse of the failed
approval, any immutable identity drift, and every post-apply state fail closed.

## Physical reproduction

- canonical base: `b15a68275f5b58c0304dcf297720cf88d2f60aed`
- Candidate: `d7048e5af2562a9174a2fca74dbd2b3f56c87716`
- staging merge: conflict-free
- admitted verifier identity: `/opt/homebrew/bin/python3`
- admitted executable SHA-256:
  `b502cb4c5b46b8d4192ec6bcb600ce8922f1afc396fcf646e8765c6eba74a0bf`
- exact merged verifier with admitted executable: `190 passed`
- ambient `/usr/bin/python3`: `No module named pytest`
- durable result: `INTEGRATION_FAILED_PRE_APPLY`, `merge_performed=false`,
  `integration_result_sha=null`

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/governed_integration.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`
- `tests/nexus/orchestrator/test_governed_integration.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py` only when the
  recovery state transition requires service-level coverage

## Required controls

- contract verifier order and command text bind one-to-one to successful
  persisted verifier evidence;
- exact absolute executable path, argv, and executable SHA-256 are persisted in
  the closure hash and rechecked immediately before execution;
- an ambient `PATH` containing only `/usr/bin` cannot substitute the admitted
  executable;
- verifier execution is argv-only, shell-free, timeout-bounded, and produces
  bounded digest evidence;
- executable/path/SHA/argv/order/status/exit-code tamper fails before verifier
  execution and before Git apply;
- a clean `INTEGRATION_FAILED_PRE_APPLY` state can be rebound only with a fresh
  exact approval and preserves append-only closure and failure history;
- failed approval replay, immutable identity drift, dirty/head/branch drift,
  and any post-apply state fail with zero durable mutation;
- Gateway schema and dispatch remain unchanged;
- no integration, approval, reload, push, cleanup, or live durable mutation is
  performed by the worker.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_target_integration_authority_closure.py \
  tests/nexus/orchestrator/test_governed_integration.py \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Forbidden scope

Do not change Gateway schema or add a public tool. Do not touch
`mcp_gateway_durable.py`, OAuth, provider readiness/admission, `FINAL_BLOCK`
projection, CapabilityPlanner, HybridRouteDecision, workforce policy,
RepositoryContractGate, integration authorization schema, lifecycle JSON,
OpenWiki, or any managed Target owned by another task. Do not weaken verifier
identity checks, use raw shell commands, infer an executable from ambient PATH,
apply the Candidate, merge canonical, reload, push, or clean up.

## Exit criteria

One scoped implementation Candidate commit after RED-to-GREEN evidence, the
exact tests above green, no deletion or out-of-scope path, clean external
worktree, and independent primary-agent review. The worker stops without
approval, integration, reload, push, or durable-state mutation.

## Block classification

Any need to change the public Gateway schema, durable launcher/OAuth, route or
provider authority, IntegrationAuthorization contract, or another task's
managed Target is a HARD_BLOCK.
