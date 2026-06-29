# June-B Baseline Inventory (P12)

**Created Date**: 2026-06-29  
**Status**: COMPLETED  

This document evaluates the 5 baseline tasks from `full_rerun_task_set.json` against their replay eligibility requirements.

## 1. Baseline Task Count & Taxonomy

Total Tasks: **5**

| Task ID | June Group | Historical Status | Current Status | Original Classification |
| --- | --- | --- | --- | --- |
| `astropy__astropy-13236` | A_PASSED | pass | INFRA_BLOCKED | MOCK_ORACLE_REPLAY_FAIL |
| `sympy__sympy-13852` | B_UNSOLVED | fail | INFRA_BLOCKED | MOCK_ORACLE_REPLAY_FAIL |
| `astropy__astropy-12907` | A_PASSED | pass | INFRA_BLOCKED | MOCK_ORACLE_REPLAY_FAIL |
| `astropy__astropy-14182` | B_UNSOLVED | fail | INFRA_BLOCKED | MOCK_ORACLE_REPLAY_FAIL |
| `sympy__sympy-11618` | shadow_only | shadow_only | shadow_only | BASELINE_ONLY |

## 2. Replay Controls & Workspace Verification

To be `REAL_REPLAY_ELIGIBLE`, a task must have:
- `source_root` (workspace directory presence)
- `target_file` (defined control)
- `target_symbol` (defined control)
- `locked_search` (defined control)
- `verifier_command` (defined control)
- `evidence_refs` (defined control)

### Task-by-Task Audit:

1. **`astropy__astropy-13236`**
   - Source Workspace: `.nexus/workspaces/astropy` (Present)
   - Verifier Command: `cd .nexus/workspaces/astropy && python -m pytest astropy/tests/ -x -q` (Present)
   - Target File: `None` (Missing)
   - Target Symbol: `None` (Missing)
   - Locked Search: `None` (Missing)
   - Evidence Refs: `None` (Missing)
   - Replay Eligibility: **NOT_REPLAYABLE_MISSING_CONTROLS**

2. **`sympy__sympy-13852`**
   - Source Workspace: `.nexus/workspaces/sympy` (Present)
   - Verifier Command: `cd .nexus/workspaces/sympy && python -m pytest sympy/core/tests/ -x -q` (Present)
   - Target File: `None` (Missing)
   - Target Symbol: `None` (Missing)
   - Locked Search: `None` (Missing)
   - Evidence Refs: `None` (Missing)
   - Replay Eligibility: **NOT_REPLAYABLE_MISSING_CONTROLS**

3. **`astropy__astropy-12907`**
   - Source Workspace: `.nexus/workspaces/astropy` (Present)
   - Verifier Command: `cd .nexus/workspaces/astropy && python -m pytest astropy/tests/ -x -q` (Present)
   - Target File: `None` (Missing)
   - Target Symbol: `None` (Missing)
   - Locked Search: `None` (Missing)
   - Evidence Refs: `None` (Missing)
   - Replay Eligibility: **NOT_REPLAYABLE_MISSING_CONTROLS**

4. **`astropy__astropy-14182`**
   - Source Workspace: `.nexus/workspaces/astropy` (Present)
   - Verifier Command: `cd .nexus/workspaces/astropy && python -m pytest astropy/tests/ -x -q` (Present)
   - Target File: `None` (Missing)
   - Target Symbol: `None` (Missing)
   - Locked Search: `None` (Missing)
   - Evidence Refs: `None` (Missing)
   - Replay Eligibility: **NOT_REPLAYABLE_MISSING_CONTROLS**

5. **`sympy__sympy-11618`**
   - Source Workspace: `.nexus/workspaces/sympy` (Present)
   - Verifier Command: `cd .nexus/workspaces/sympy && python -m pytest sympy/core/tests/ -x -q` (Present)
   - Target File: `None` (Missing)
   - Target Symbol: `None` (Missing)
   - Locked Search: `None` (Missing)
   - Evidence Refs: `None` (Missing)
   - Replay Eligibility: **BASELINE_ONLY** (Excluded boundary case)

## 3. Taxonomy Summary

- **REAL_REPLAY_ELIGIBLE**: 0 tasks
- **NOT_REPLAYABLE_MISSING_WORKSPACE**: 0 tasks
- **NOT_REPLAYABLE_MISSING_CONTROLS**: 4 tasks
- **NOT_REPLAYABLE_PROVIDER_REQUIRED**: 0 tasks
- **BASELINE_ONLY**: 1 task
