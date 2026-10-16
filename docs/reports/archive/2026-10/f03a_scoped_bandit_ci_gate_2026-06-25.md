# F-03A: Scoped Bandit Observation — 2026-06-25

## Status

`F03A_SCOPED_BANDIT_OBSERVATION_WIRED` — Observation workflow in place. Command exits non-zero on current HEAD (8 findings). Not a blocking gate.

## Scope

- **Scan target**: `nexus/core` only (12,480 lines of code)
- **NOT full repo**: This does not cover `nexus/services/`, `scripts/`, `tests/`, or any other directory
- **Bandit only**: No `pip-audit`, no `CodeQL`, no dependency vulnerability scanning
- **NOT claiming security coverage**: This is static analysis of one narrow source area

## Files Changed

| File | Change |
|---|---|
| `.github/workflows/security.yml` | New observation workflow (continue-on-error) |
| `pyproject.toml` | Added `bandit>=1.7.0` to `[dependency-groups] dev` |
| `uv.lock` | Updated (dependency resolution) |
| `docs/reports/f03a_scoped_bandit_ci_gate_2026-06-25.md` | This report |

## Commands Run

```bash
uv run bandit -r nexus/core -ll -ii
# Exit code: 1
# Scan: 12,480 lines
# Issues: 5 high, 3 medium, 85 low (filtered by -ll)
```

## Findings (medium+ severity, medium+ confidence)

| Severity | CWE | File | Line | Issue |
|---|---|---|---|---|
| High | CWE-327 | `campaign_general.py` | 225 | MD5 hash usage (`hashlib.md5`) |
| High | CWE-78 | `drone_engine.py` | 86 | `subprocess.run(shell=True)` |
| High | CWE-78 | `notifier.py` | 42 | `os.system()` shell injection |
| High | CWE-327 | `policy_drift.py` | 72 | MD5 hash usage (`hashlib.md5`) |
| High | CWE-327 | `xray_observer.py` | 64 | MD5 hash usage (`hashlib.md5`) |
| Medium | CWE-377 | `gemini_handoff.py` | 55 | Hardcoded `/tmp/` path |
| Medium | CWE-377 | `gemini_handoff.py` | 68 | Hardcoded `/tmp/` path |
| Medium | CWE-22 | `vector_rag.py` | 73 | `urllib.request.urlopen` (file scheme risk) |

## CI Behavior

- **Observation-only**: `continue-on-error: true` — does NOT block push/PR
- **Deterministic**: `uv run bandit -r nexus/core -ll -ii` is the exact CI command (exit code: 1)
- **Visible**: Workflow shows in GitHub Actions as "Nexus Scoped Security Scan (observation)"
- **Not a gate**: 8 pre-existing findings cause non-zero exit; 升级 to blocking gate requires finding resolution

## What This Does NOT Do

- Does NOT scan outside `nexus/core`
- Does NOT run `pip-audit` for dependency vulnerabilities
- Does NOT run CodeQL or any SAST beyond Bandit
- Does NOT claim full security coverage
- Does NOT suppress findings without documentation

## Next Scope Candidates (F-03B)

1. `nexus/services/local_heal` — recent feature, review for shell/temp patterns
2. `scripts/ops` — utility scripts with potential subprocess usage
3. `nexus/services/` (all) — broader security audit
4. `pip-audit` — dependency vulnerability scanning (separate task)
