# F-03C Bandit nexus/core Blocking Gate Promotion

**Status:** `F03C_BANDIT_CORE_BLOCKING_GATE_PASS`

**Date:** 2026-06-26

## Summary

Promoted Bandit scan from observation-only to blocking gate for `nexus/core`.

## Files Changed

| File | Change |
|---|---|
| `.github/workflows/security.yml` | Removed `continue-on-error`, updated name and summary |

## Changes Detail

1. **Removed job-level `continue-on-error: true`** — workflow now fails if bandit exits non-zero
2. **Removed step-level `continue-on-error: true`** — step now fails on non-zero exit
3. **Updated workflow name** from "observation" to "nexus/core blocking"
4. **Updated job name** from "Bandit Observation" to "Bandit Scan (nexus/core blocking)"
5. **Updated step summary** from "observation-only" to "blocks CI if medium+ findings detected"

## Command Output Summary

```
uv run bandit -r nexus/core -ll -ii
→ Exit code: 0
→ 0 Medium, 0 High findings
→ 85 Low findings (below -ll threshold)
```

## Scope Statement

- Scope is `nexus/core` only — no broader repo coverage
- No dependency scanning (pip-audit) added
- No static analysis (CodeQL) added
- F-03 full repo not complete — only nexus/core is blocking

## Commands Run

```bash
uv run bandit -r nexus/core -ll -ii
git diff --cached --name-status
```

## Blocking Gate Criteria

| Criterion | Status |
|---|---|
| `uv run bandit -r nexus/core -ll -ii` exits 0 | ✅ Pass |
| Scope limited to nexus/core | ✅ Pass |
| No pip-audit | ✅ Confirmed absent |
| No CodeQL | ✅ Confirmed absent |
