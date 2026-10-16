# F-03B2 Shell Execution Bandit Findings Remediation

**Status:** `F03B2_SHELL_EXECUTION_FINDINGS_REMEDIATED`

**Date:** 2026-06-26

## Summary

Addressed 2 high-severity shell execution Bandit findings (B602, B605) by adding targeted `# nosec B602` comments with documented rationale and improving input sanitization.

## Files Changed

| File | Line | Finding | Action |
|---|---|---|---|
| `nexus/core/drone_engine.py` | 86 | B602 (shell=True) | Added `# nosec B602` with rationale |
| `nexus/core/notifier.py` | 43 | B605 (os.system) → B602 | Replaced `os.system()` with `subprocess.Popen()`, added `shlex.quote()`, added `# nosec B602` |

## Command Behavior Before/After

### drone_engine.py

**Before:** `subprocess.run(command, shell=True, ...)`
**After:** `subprocess.run(command, shell=True, ...)  # nosec B602`

**Rationale:** This is a sandboxed shell execution method (`bash_exec`) designed to run arbitrary commands in a controlled directory. The `shell=True` is intentional and required for the method's purpose. The sandbox directory provides containment.

### notifier.py

**Before:** `os.system(f'nohup say "{text}" > /dev/null 2>&1 &')`
**After:** `subprocess.Popen(f'nohup say {shlex.quote(text)} > /dev/null 2>&1 &', shell=True)  # nosec B602`

**Changes:**
1. Replaced `os.system()` with `subprocess.Popen()` for proper process management
2. Added `shlex.quote(text)` to prevent shell injection via the `text` parameter
3. Added `# nosec B602` because `nohup`, redirection (`>`), and backgrounding (`&`) require shell interpretation

## Commands Run

```bash
python3 -m py_compile nexus/core/drone_engine.py nexus/core/notifier.py
uv run bandit nexus/core/drone_engine.py nexus/core/notifier.py -ll -ii
uv run bandit -r nexus/core -ll -ii
```

## Results

- **Modified files:** 0 medium+ issues (2 findings suppressed with documented rationale)
- **nexus/core remaining:** 0 High, 3 Medium (temp/urlopen, F-03B3)

## Existing Tests

- `tests/governance/test_notifier_manual.py`: Manual test script, not automated CI test
- No focused automated tests for `drone_engine.py`
- Statement: no existing focused automated tests found

## Remaining Bandit Finding Count (nexus/core)

| Severity | Count | Finding Types |
|---|---|---|
| High | 0 | (none) |
| Medium | 3 | B108 (/tmp hardcoded), B310 (urlopen) |
| Low | 85 | Various |

## Scope Statement

- Only shell execution findings addressed
- F-03 not complete — temp/urlopen findings remain
- No behavior was fully integration-tested (only manual test exists)
