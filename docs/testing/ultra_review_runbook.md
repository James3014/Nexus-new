# Ultra Review Runbook

## Scope

`nexus ultra-review` is a fail-closed review gate for high-risk changes. The
current implementation is still dry-run mode, but Ghost Regression now executes
candidate pytest targets and converts failing candidates into verified findings.

## Current Capabilities

- Captures `git diff --binary HEAD` and `git status --short`.
- Writes sandbox artifacts under `.nexus/reports/ultra_review/sandboxes`.
- Builds three review lanes:
  - `security_sentry`
  - `logic_breaker`
  - `ghost_regression`
- Scans added diff lines for secret literals, `shell=True`, and unsafe delete patterns.
- Maps changed source files to likely regression tests.
- Executes existing Ghost Regression pytest candidates.
- Marks failed Ghost Regression candidates as `VERIFIED_FINDING`.
- `scripts/ops/ultra_gate.py` blocks failed Ghost Regression and blocking verified findings.

## Commands

```bash
uv run python scripts/engine/nexus_cli.py nexus ultra-review --output-json
uv run python scripts/ops/ultra_gate.py --report .nexus/reports/ultra_review_report.json --check-artifacts --json
```

Focused tests:

```bash
uv run pytest -q tests/engine/test_ultra_review_service.py tests/ops/test_ultra_gate.py
```

## Future Work

1. Add true isolated worktree execution.
2. Add Logic Breaker reproduction scripts.
3. Add Security Sentry repro commands for verified security findings.
4. Wire ultra gate into `ci_gate.py` strict/high-risk lanes.
5. Add background progress tracking only after the execution contract is stable.
