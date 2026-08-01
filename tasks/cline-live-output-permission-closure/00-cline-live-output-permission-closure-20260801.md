# Task Card: cline-live-output-permission-closure-20260801

artifact_authority: current
task_id: `cline-live-output-permission-closure-20260801`
owner: James Chen
status: RECOVERABLE_BLOCK
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Prove real Cline GLM-5.2 stdout compatibility and bounded permission/cleanup behavior without canonical mutation.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/fixtures/cline/glm_52_real_stdout.ndjson`

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-cline-live-pycache .venv/bin/python -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Verification receipt

- scoped commit: `3eac7488c`
- focused Gateway suite: `39 passed, 1 warning`
- real Cline binary: `3.0.48` (direct binary; wrapper path still crashes)
- real stdout fixture: `tests/fixtures/cline/glm_52_real_stdout.ndjson`
- fixture source: isolated direct Cline run with `--json --plan
  --auto-approve false --thinking none --model cline-pass/glm-5.2`; output was
  preserved as de-identified NDJSON and parser fails closed because the stream
  contains provider error events and no candidate patch
- permission mode: Gateway now uses Cline `--plan --auto-approve false`; the
  receipt explicitly records `allowlist_not_enforced`
- timeout/cancel distinction: poll timeout remains non-destructive; explicit
  cancel retains SIGTERM/SIGKILL bounded cleanup and isolated workspace receipt
- live result: `RECOVERABLE_BLOCK`
- blocker: provider endpoint/auth failed before a candidate (`FailedToOpenSocket`,
  exit 1, no model tokens, no patch)
- claim ceiling: `CLINE_EVENT_PARSER_IMPLEMENTED`,
  `CLINE_REAL_STDOUT_ERROR_FIXTURE_PASS`, and safe command construction only;
  no live candidate, GLM calibration, provider readiness, or tool-allowlist
  enforcement is claimed
- next gate: `CLINE_PROVIDER_LIVENESS_AND_TIMEOUT_CLOSURE`

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
