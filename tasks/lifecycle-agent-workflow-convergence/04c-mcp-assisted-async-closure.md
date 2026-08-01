# Task Card: MCP Assisted Provider Async Closure

artifact_authority: current
task_id: `lifecycle-workflow-mcp-assisted-async-closure`
owner: James Chen
status: COMPLETED_PENDING_OWNER_REVIEW
source_specification: `/Users/jameschen/.codex/attachments/d3c92354-8ddc-4ab7-b405-6cfef8369695/pasted-text.txt`
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Make the ChatGPT-visible MCP surface able to submit a bounded Cline/GLM-5.2
Assisted candidate without holding the MCP request open, then poll and retrieve
the same durable result after connector disconnect or request timeout.

## Scope

- Add a durable provider-job record and asynchronous submit/poll/result surface.
- Route Cline Assisted requests through that surface while preserving
  `ASSISTED_CANONICAL` and provider/model identity.
- Make proposal-only (`apply=false`) actions `mutation=false` with `VERIFY`.
- Keep the existing bounded synchronous adapters for non-Cline compatibility.
- Expose `nexus_task_reconcile`/result-compatible responses with tool names that
  exist in the public manifest.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tasks/lifecycle-agent-workflow-convergence/04c-mcp-assisted-async-closure.md`
- `tasks/lifecycle-agent-workflow-convergence/INDEX.md`

## Forbidden scope

- No broad shell/write tool, namespace migration, provider promotion, or model
  calibration claim.
- No automatic patch apply, commit, merge, push, Target cleanup, or Candidate
  approval from the async result surface.
- No edits under `nexus-worktrees` or any unrelated dirty file.

## Verification commands

```bash
uv run pytest tests/nexus/orchestrator/test_unified_mcp_gateway.py -q
git diff --check
```

## Evidence required

- Submit returns within the MCP request with `job_id`, `task_id`, `action_id`,
  provider/model, command hash, and durable artifact paths.
- Poll/result after the worker finishes returns the same job identity, exit
  code, latency, stdout/stderr hashes, and parsed candidate or fail-closed
  blocker.
- `apply=false` is `mutation=false`/`VERIFY` and no canonical file delta is
  introduced by submit, poll, or result.
- Public `recommended_tool` values are present in the Gateway manifest.

## Exit criteria

`nexus_assist_submit` returns without waiting for provider completion;
`nexus_task_wait` and `nexus_assist_result` retrieve the durable outcome; Cline
identity remains `ASSISTED_CANONICAL`; and focused tests pass.

## Residual debt

Provider preflight, isolated patch-only enforcement, Task Card creation, and
three-arm calibration remain later cards; this card does not claim them.

## Block classification

Provider binary/authentication failure is `RECOVERABLE_BLOCK`; missing or
invalid lifecycle identity is `HARD_BLOCK` and must not mutate the checkout.
