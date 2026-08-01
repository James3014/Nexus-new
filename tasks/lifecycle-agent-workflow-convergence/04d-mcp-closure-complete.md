# Task Card: MCP Closure Completion

artifact_authority: current
task_id: `lifecycle-workflow-mcp-closure-complete`
owner: James Chen
status: ACTIVE
source_specification: `/Users/jameschen/.codex/attachments/b0b05b05-16f9-4547-8c9c-24ce84a19139/pasted-text.txt`
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Finish the remaining ChatGPT-visible Nexus MCP closure after the async Cline
slice: bounded provider preflight, narrow Task Card bootstrap, generic model
probe receipts, Cline matrix admission, and fail-closed safety/telemetry.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `scripts/ops/nexus_mcp_gateway_http.py`
- `nexus/config/model_three_arm_matrix.yaml`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`
- `tasks/lifecycle-agent-workflow-convergence/04d-mcp-closure-complete.md`
- `tasks/lifecycle-agent-workflow-convergence/INDEX.md`

## Forbidden scope

- No broad shell, unrestricted write, namespace alias migration, provider
  promotion, automatic commit/merge/push, or Candidate approval.
- No lifecycle JSON hand edits, `nexus-worktrees` checkout, or unrelated dirty
  file cleanup.
- Matrix entry is candidate admission only; it cannot claim semantic promotion.

## Verification commands

```bash
python3 -m pytest tests/nexus/orchestrator/test_unified_mcp_gateway.py -q
python3 -m pytest tests/nexus/orchestrator/test_unified_mcp_gateway_http.py -q
git diff --check
```

## Required evidence and exit criteria

- `nexus_provider_preflight` returns binary/version/hash/auth/model evidence
  or an explicit fail-closed blocker.
- `nexus_task_card_create` only creates a new campaign index plus one card
  after owner confirmation, never overwrites, and returns card hash/diff.
- `nexus_model_probe` records raw/parsed output, schema, latency, exit code,
  filesystem delta, and process cleanup without canonical mutation.
- `cline_glm_52` is present in the three-arm matrix as a candidate only.
- Cline probe jobs run in an isolated directory with a before/after snapshot;
  the public action manifest contains every recommended recovery tool.
- Focused tests and live Gateway reload prove the new tools are exposed.

## Residual debt

Real account authentication/quota may remain a recoverable provider block; it
must be represented in the preflight/probe receipt, not mistaken for a model
failure or promotion.

## Block classification

Missing owner confirmation, invalid task-card path, canonical mutation, or
unverifiable filesystem/process evidence is a HARD_BLOCK. Provider binary,
auth, quota, or timeout is a RECOVERABLE_BLOCK.
