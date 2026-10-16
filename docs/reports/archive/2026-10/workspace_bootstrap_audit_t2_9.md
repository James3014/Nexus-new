# T2.9 Workspace Bootstrap Audit Report

**Audit Date**: 2026-06-18
**Baseline**: T2_9_20_TASK_RECOVERY_BASELINE
**Source Run**: T2_8_ATTRIBUTION_SAFE_20_TASK_DIAGNOSTIC

## Summary

| Project | Workspace Exists | Python Exec | Import OK | .venv Committed | Status |
|---------|-----------------|-------------|-----------|-----------------|--------|
| astropy | Yes | .venv_astropy/bin/python | Yes | No | PASS |
| sympy | Yes | .nexus/workspaces/sympy/.venv39/bin/python | Yes (via sys.path) | No | PASS |
| django | Yes | /usr/local/bin/python3 | Yes (via sys.path) | No | PASS |

## Project: astropy

**Workspace path**: `.nexus/workspaces/astropy/`
**Python exec**: `.venv_astropy/bin/python` (Python 3.10)

### Dependencies verified
- `import astropy` — OK
- `import bs4` (beautifulsoup4==4.15.0) — OK
- `import lxml` (lxml==6.1.1) — OK

### Bootstrap checks
- setup.py exists: YES
- requirements.txt: NOT PRESENT (uses setup.py install)
- .venv committed: NO
- import_project_success: YES
- reproduce_script_found: YES (per-task repro scripts in t2_8 script)
- bug_reproduced_before_patch: varies per task

## Project: sympy

**Workspace path**: `.nexus/workspaces/sympy/`
**Python exec**: `.nexus/workspaces/sympy/.venv39/bin/python` (Python 3.9.24)

### Dependencies verified
- `import sympy` — OK (via sys.path.insert, DeprecationWarning for collections.Mapping — expected for sympy 1.0.1.dev)
- `import mpmath` — OK

### Python 3.9 requirement note
sympy 1.0.1.dev uses `from collections import Mapping` which is deprecated since Python 3.3 and removed in Python 3.10+. Python 3.9 is required for this version. The .venv39 provides Python 3.9.24.

### Bootstrap checks
- setup.py exists: YES
- requirements.txt: NOT PRESENT
- .venv committed: NO
- import_project_success: YES (with deprecation warnings)
- reproduce_script_found: YES
- bug_reproduced_before_patch: varies per task

## Project: django

**Workspace path**: `.nexus/workspaces/django/`
**Python exec**: `/usr/local/bin/python3` (Python 3.12.8)

### Dependencies verified
- `import django` — OK (via sys.path.insert)

### Bootstrap checks
- setup.py exists: YES
- requirements.txt: NOT PRESENT
- .venv committed: NO
- import_project_success: YES (via sys.path.insert to workspace)
- reproduce_script_found: YES
- bug_reproduced_before_patch: varies per task

## Audit Result

**PASS** — All 3 projects have working workspace bootstrap. No .venv directories committed. All imports verified. No dependency failures blocking clean replay.

Known limitations:
- sympy produces DeprecationWarning for collections.Mapping (expected, not blocking)
- django relies on sys.path.insert rather than pip install (functional but not hermetic)
- No requirements.txt files (setup.py based projects)
