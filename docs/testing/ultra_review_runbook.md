# Ultra Review Runbook

## Scope

`nexus ultra-review` is a fail-closed review gate for high-risk changes. The
current implementation is still dry-run mode, but Logic Breaker and Ghost
Regression now execute deterministic checks inside a sandbox mirror and convert
failing checks into verified findings.

## Current Capabilities

- Captures `git diff --binary HEAD` and `git status --short`.
- Writes sandbox artifacts under `.nexus/reports/ultra_review/sandboxes`.
- Creates a sandbox mirror worktree for Logic Breaker and Ghost Regression execution.
- Writes `progress.jsonl` and a compact report `summary` for long-running diagnosis.
- Builds three review lanes:
  - `security_sentry`
  - `logic_breaker`
  - `ghost_regression`
- Scans added diff lines for secret literals, `shell=True`, and unsafe delete patterns.
- Writes and executes `ultra_security_repro_*.py` scripts for reproducible Security Sentry evidence.
- Maps changed source files to likely regression tests.
- Writes and executes `ultra_logic_repro.py` as a deterministic Logic Breaker repro.
- Executes existing Ghost Regression pytest candidates in `sandbox_mirror` mode
  with the active virtualenv.
- Enforces a 15-second Logic Breaker timeout.
- Enforces a 30-second Ghost Regression timeout.
- Marks reproduced Security Sentry findings and failed or timed-out Logic Breaker/Ghost Regression checks as `VERIFIED_FINDING`.
- `scripts/ops/ultra_gate.py` blocks failed Logic Breaker, failed Ghost Regression,
  and blocking verified findings.
- `scripts/ops/ci_gate.py --strict --changed-paths ...` runs Ultra Review for high-risk
  engine/CI gate paths.

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

1. Replace the sandbox mirror copy with a cheaper worktree/sparse checkout strategy.
2. Add background task tracking only after the execution contract is stable.
3. Expand high-risk path rules from static prefixes to selector risk metadata.
