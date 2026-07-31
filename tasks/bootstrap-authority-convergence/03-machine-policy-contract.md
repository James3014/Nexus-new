# Task Card 03: Machine Policy Contract

## Identity

- task_id: `machine-policy-contract`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `bootstrap-path-convergence` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Replace the protocol checker's permissive missing-contract fallback with one checked-in machine policy contract and make strict checks compose that repository baseline with an explicit active Task Card overlay. A missing, malformed, or contradictory baseline must fail closed; a card overlay may narrow scope but may not widen repository-forbidden paths or the file-count ceiling.

## Allowed files

- `scripts/ops/agent_protocol_contract.json`
- `scripts/ops/agent_protocol_check.py`
- `tests/ops/test_agent_protocol_check.py`
- `tests/ops/test_agent_protocol_check_staged.py`

## Machine policy overlay

```json
{
  "allowed_paths": [
    "scripts/ops/agent_protocol_contract.json",
    "scripts/ops/agent_protocol_check.py",
    "tests/ops/test_agent_protocol_check.py",
    "tests/ops/test_agent_protocol_check_staged.py"
  ],
  "forbidden_paths": [],
  "max_files_touched": 4
}
```

## Forbidden scope

No bootstrap-file edits; no runtime router/workforce/startup changes; no changes to canonical root; no weakening of lifecycle authority; no silent fallback to an unrestricted contract; no deletion of receipts/reports.

## Required behavior

1. The checked-in JSON contract is the repository baseline and includes required AGENTS terms, allowed paths, forbidden paths, and `max_files_touched`.
2. Missing or invalid JSON returns a deterministic failure; the checker must not silently substitute `allowed_paths: ["."]` and an empty forbidden list.
3. `--task-card <path>` loads a bounded overlay with `allowed_paths`, `forbidden_paths`, and `max_files_touched`; the effective policy is the intersection of allowed paths, the union of forbidden paths, and the lower file-count ceiling.
4. Strict staged checks use the effective policy and report which layer caused a failure.
5. Existing direct-contract tests remain compatible, and new tests cover missing/malformed baseline, overlay narrowing, forbidden-path union, and ceiling enforcement.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_agent_protocol_check.py tests/ops/test_agent_protocol_check_staged.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/agent_protocol_check.py --strict-boundary --check-files scripts/ops/agent_protocol_check.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Evidence required

- Contract JSON is valid and tracked.
- Strict checks fail closed when the baseline is absent or malformed.
- Overlay behavior is proven by focused tests and a clean scoped commit.
- No files outside the four allowed paths are changed.

## Exit criteria

The protocol checker consumes a real baseline contract, supports a non-widening active Task Card overlay, passes all focused tests, and produces a scoped commit. P0-D startup freshness integration remains separate.

## Residual debt

Startup still does not bind worktree/HEAD/index/card/policy freshness into one ACK gate. Workforce and briefing surfaces remain downstream.

## Block classification

- `RECOVERABLE_BLOCK`: local test or JSON parsing/tooling failure with changes preserved.
- `HARD_BLOCK`: requested overlay semantics would widen authority or require an untracked parallel policy source.
