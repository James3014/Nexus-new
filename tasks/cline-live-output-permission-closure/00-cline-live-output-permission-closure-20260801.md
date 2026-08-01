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

- scoped commits: `3eac7488c`, `14b49c305`, `14bcca1c6`, `c45a44ec8`,
  `cb9e42ae3`
- focused Gateway suite: `40 passed, 1 warning`
- real Cline binary: `3.0.48` (direct binary; wrapper path still crashes)
- real stdout fixture: `tests/fixtures/cline/glm_52_real_stdout.ndjson`
- fixture source: isolated direct Cline run with `--json --plan
  --auto-approve false --thinking none --model cline-pass/glm-5.2`; output was
  preserved as de-identified NDJSON and parser fails closed because the stream
  contains provider error events and no candidate patch
- permission mode: Gateway now uses Cline `--plan --auto-approve false`; the
  receipt explicitly records `allowlist_not_enforced`
- provider command now carries an explicit bounded `--timeout 60`; this limits
  non-interactive tool-call hangs but does not create physical tool policy
  enforcement
- timeout/cancel distinction: poll timeout remains non-destructive; explicit
  cancel retains SIGTERM/SIGKILL bounded cleanup and isolated workspace receipt
- cancel receipts now hash and size flushed stdout/stderr after bounded process
  termination (`stream_flush_status=FLUSHED`); the focused regression covers
  emitted partial streams plus workspace cleanup
- direct live binary probe: `PASS` (Cline 3.0.48, resolved model
  `cline-pass/glm-5.2`, exit 0, real NDJSON `run_start`/`agent_event`/`run_result`,
  exact model evidence, no canonical mutation)
- Gateway live candidate attempt: `RECOVERABLE_BLOCK`
- Gateway cancel acceptance: `PASS` for both bounded attempts; each recorded
  `CANCELLED`, `process_killed=true`, `process_cleanup=true`, isolated workspace
  removed, flushed stream hashes, and canonical HEAD/diff unchanged
- blocker: Gateway Cline path can still enter provider tool calls in a
  non-interactive session despite `--plan --auto-approve false`; no physical
  no-tool/allowlist enforcement is available, so the bounded candidate cannot
  be promoted to live-candidate PASS
- claim ceiling: `CLINE_EVENT_PARSER_IMPLEMENTED`,
  `CLINE_REAL_STDOUT_COMPATIBILITY_PASS` (direct binary probe),
  `CLINE_CANCEL_CLEANUP_PASS`, and safe command construction only; no
  `CLINE_LIVE_CANDIDATE_PASS`, GLM calibration, provider readiness, or
  tool-allowlist enforcement is claimed
- next gate: `CLINE_LIVE_CANDIDATE_OR_PHYSICAL_NO_TOOL_POLICY`

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
