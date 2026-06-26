# F-03B1 MD5 Bandit Findings Remediation

**Status:** `F03B1_MD5_FINDINGS_REMEDIATED`

**Date:** 2026-06-26

## Summary

Remediated 3 high-severity MD5 Bandit findings (B324) in `nexus/core` by adding `usedforsecurity=False` parameter.

## Files Changed

| File | Line | Change |
|---|---|---|
| `nexus/core/campaign_general.py` | 225 | `hashlib.md5(..., usedforsecurity=False)` |
| `nexus/core/policy_drift.py` | 72 | `hashlib.md5(..., usedforsecurity=False)` |
| `nexus/core/xray_observer.py` | 64 | `hashlib.md5(..., usedforsecurity=False)` |

## Rationale

All three MD5 uses are non-security deterministic operations:
- **campaign_general.py**: Intent hash for DAG node count bucketing
- **policy_drift.py**: File path hash for replay artifact naming
- **xray_observer.py**: Card ID generation for findings memory store

None are used for password hashing, signature verification, or security-sensitive purposes.

## Commands Run

```bash
python3 -m py_compile nexus/core/campaign_general.py nexus/core/policy_drift.py nexus/core/xray_observer.py
uv run bandit nexus/core/campaign_general.py nexus/core/policy_drift.py nexus/core/xray_observer.py -ll -ii
uv run bandit -r nexus/core -ll -ii
```

## Results

- **Modified files:** 0 medium+ issues
- **nexus/core remaining:** 2 High (shell execution, F-03B2), 3 Medium (temp/urlopen, F-03B3)

## Remaining Bandit Finding Count (nexus/core)

| Severity | Count | Finding Types |
|---|---|---|
| High | 2 | B602 (shell=True), B605 (os.system) |
| Medium | 3 | B108 (/tmp hardcoded), B310 (urlopen) |
| Low | 85 | Various |

## Scope Statement

- Only MD5 findings addressed
- F-03 not complete — shell execution and temp/urlopen findings remain
- No other security findings modified
