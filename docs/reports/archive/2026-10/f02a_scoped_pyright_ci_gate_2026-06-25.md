# F-02A: Scoped Pyright Observation — 2026-06-25

## Status

`F02A_SCOPED_PYRIGHT_OBSERVATION_WIRED` — Observation workflow in place. Command exits non-zero on current HEAD. Not a blocking gate.

## Scope

- **Typecheck target**: `nexus/core` only
- **NOT full repo**: This does not cover `nexus/services/`, `nexus/verifiers/`, `scripts/`, `tests/`, or any other directory
- **NOT replacing Pyre**: Existing `.pyre_configuration` is unchanged
- **NOT claiming type safety**: 197 pre-existing errors exist; this gate surfaces them, not fixes them

## Files Changed

| File | Change |
|---|---|
| `.github/workflows/typecheck.yml` | New observation workflow (continue-on-error) |
| `pyproject.toml` | Added `pyright>=1.1.370` to `[dependency-groups] dev` |
| `uv.lock` | Updated (dependency resolution) |
| `docs/reports/f02a_scoped_pyright_ci_gate_2026-06-25.md` | This report |

## Commands Run

```bash
uv run pyright nexus/core
# Exit code: 1
# Result: 197 errors, 0 warnings, 0 informations
```

## Pre-existing Error Summary

| Error Category | Count | Example |
|---|---|---|
| `reportOptionalMemberAccess` | ~30 | Accessing attributes on possibly-None values |
| `reportArgumentType` | ~40 | Type mismatches (Path vs str, None vs required) |
| `reportGeneralTypeIssues` | ~50 | TypedDict key assignment violations |
| `reportAttributeAccessIssue` | ~40 | Unknown attributes on classes |
| `reportMissingImports` | ~5 | arweave, opentelemetry.sdk imports |
| `reportUndefinedVariable` | ~3 | `os`, `json`, `time` not imported |
| Other | ~29 | Various type issues |

## CI Behavior

- **Observation-only**: `continue-on-error: true` — does NOT block push/PR
- **Deterministic**: `uv run pyright nexus/core` is the exact CI command (exit code: 1)
- **Visible**: Workflow shows in GitHub Actions as "Nexus Scoped Typecheck (observation)"
- **Not a gate**: Pre-existing 197 errors cause non-zero exit;升级 to blocking gate requires error remediation

## What This Does NOT Do

- Does NOT check `nexus/services/`, `nexus/verifiers/`, `scripts/ops/`, or any code outside `nexus/core`
- Does NOT fix any type errors
- Does NOT replace Pyre configuration
- Does NOT claim full type safety for the repository

## Next Scope Candidates (F-02B)

1. `nexus/services/local_heal` — recent feature, likely cleaner
2. `scripts/ops` — utility scripts, lower risk
3. `nexus/services/` (all) — broader, needs more error remediation
