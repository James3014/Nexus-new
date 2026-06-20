# T4.1 Historical Clean Candidate Policy

**Date**: 2026-06-18

---

## 1. Definitions

### Active Replayable
Candidate with source_fresh status, verified evidence, and eligible for T4.2 clean-room replay.

### Historical Clean But Stale Source
Candidate that was successfully verified in a prior run, but current workspace source no longer contains the buggy line. The success is real historical evidence but cannot be replayed without source snapshot restoration.

### Source Already Patched
The bug fix has already been applied to the current workspace source. The buggy line no longer exists.

### Source Revision Unknown
Source state cannot be determined. Cannot enter replay manifest.

## 2. Why Historical Clean ≠ Current Replay Success

- Historical clean means: "this candidate was verified at time T"
- Current replay success means: "this candidate can be verified again now"
- Source staleness breaks the bridge between historical and current
- Without source snapshot restoration, replay is impossible

## 3. Why Stale Source ≠ Model Failure

- Model produced correct output at time T
- Source changed after time T (by someone else, or by prior fix)
- The model's success is preserved as historical evidence
- Stale source is a source management issue, not a model capability issue

## 4. How to Handle in T4.2 Clean-Room Replay

- If source snapshot is available: restore snapshot, then replay
- If source snapshot is NOT available: mark as historical_clean, do NOT replay
- Do NOT force replay on stale source
- Do NOT count stale replay failure as model failure

## 5. Examples

| Candidate | Status | Action |
|-----------|--------|--------|
| sympy-12419 | source_already_patched | Historical clean, no replay |
| sympy-13647 | source_already_patched | Historical clean, no replay |
| astropy-14365 | source_already_patched | Historical clean, no replay |
| astropy-13236 | source_fresh | Active replayable, can enter T4.2 |

## 6. Recovery Path

If source snapshot becomes available later:
1. Restore exact source snapshot
2. Verify source hash matches
3. Re-run source revision check
4. If buggy_line found: promote to active_replayable
5. If still not found: remain historical_clean
