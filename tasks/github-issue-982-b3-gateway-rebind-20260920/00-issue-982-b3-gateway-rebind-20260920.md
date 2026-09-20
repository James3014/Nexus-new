# Task Card: issue-982-b3-gateway-rebind-20260920

artifact_authority: current
task_id: `issue-982-b3-gateway-rebind-20260920`
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

Converge the live ChatGPT-facing Nexus Gateway from its currently loaded c6e2609f lineage to exact GitHub main 45cca97712b8801c3c0bf543bec8984ea5cf3104 / tree 0b40ad95b433a15f2ab140ec64fe312a53c7d66a, which contains the merged #1032 MiMo route and valid #982 B3 R1-B contract. Reuse only the existing #526 durable recovery manager and previously accepted manager/runtime lineage. Authorize only a fresh tracked recovery-authority receipt at the existing fixed path. No production/runtime source code change, no new manager/process authority, no manual launchctl/plist/PID manipulation, no provider canary, no G4. The host effect may start only after the exact authority receipt is independently verified, merged, materialized byte-identically, and the typed DevSpace recovery preflight returns effectStarted=false with TARGET_READY and ROLLBACK_READY. AUTO_CHAIN=false.

## Allowed files

- `tasks/github-issue-526-g20-r1-source-contract-delta-20260903/02-r1-complete-deployment-recovery-authority-receipt.json`

## Verification commands

```bash
python -m pytest tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
