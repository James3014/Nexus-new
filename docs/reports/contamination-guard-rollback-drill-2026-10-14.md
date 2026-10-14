# Contamination Guard Rollback Drill — P-CONTAM-01

**Date**: 2026-10-14 (drill run 15:06:19Z–15:06:34Z)
**Worktree HEAD**: `7448ec2b499c2dcc160001e42974a7bbed47671b` (PR #2197 head, scratch detached worktree)
**Guard commit under test**: `e3b0ba5eb1aac445e09b230a2b661c62160d6fc0` (`fix(research): restore field-level contamination detection`)
**Rollback target**: `e3b0ba5eb~1` = `ae5b8cd5065b73534049337ee412c4ba1b077e7a`
**Status**: **DRILL EXECUTED & VERIFIED — rollback is possible, detectable, and fully reversible**

---

## Scope

Rollback drill for the Python enforcement point of policy P-CONTAM-01:
1. `nexus/research/contamination_guard.py` (`evaluate_research_contamination`)

This replaces the 2026-06-15 Rust drill ([rust-kernel-rollback-drill-2026-06-15.md](rust-kernel-rollback-drill-2026-06-15.md)) for this policy. That drill covered `nexus-core-rs/src/contamination.rs`, not this guard.

Known gap (not covered by this drill, tracked in #2199): the guard's only production caller is the retired legacy engine (`nexus/engine/pipeline_stages.py`). The canonical research executor does not call it.

---

## Drill Scenario

**Trigger**: A guard change introduces a regression.
**Rollback Action**: Git revert of the guard file to its previous commit, then restore.

---

## Pre-Drill State

| Item | Value |
|------|-------|
| Guard last commit | `e3b0ba5eb1aac445e09b230a2b661c62160d6fc0` |
| Guard sha256 | `d859a968285ee43f644e6acf342dff423c2b39842b0c63aa7cf821324cbde7e8` |
| Tests covering the guard | `tests/research/test_research_isolation.py`, `tests/unit/test_research_isolation_slice.py`, `tests/integration/test_capability_existence_155.py` |
| Python | 3.14.7, pytest 9.0.3 (worktree `uv sync --frozen --all-extras` venv) |

---

## Rollback Steps

All commands ran in a scratch worktree with `PYTHONPATH=$PWD`, where
`T="tests/research/test_research_isolation.py tests/unit/test_research_isolation_slice.py tests/integration/test_capability_existence_155.py"`.

### Step 1: Baseline
```bash
python -m pytest -q -p no:cacheprovider $T
```
**Result**: ✅ PASS (`525 passed, 21 warnings in 1.12s`, exit 0)

### Step 2: Roll back the guard
```bash
git checkout e3b0ba5eb~1 -- nexus/research/contamination_guard.py
```
The rolled-back guard sha256 is `6d53e38a10e6bc29e0037770cb05ae4230c0069e2b977661276cca5f49e4dba7`. The diff against HEAD removes 4 lines: the `has_design_fields` import and the field-level check below.
```diff
-from nexus.research.research_facts import has_design_fields
...
-    if has_design_fields(payload):
-        detected.append("design_field")
-    detected = list(dict.fromkeys(detected))
```

### Step 3: Verify the rollback is detectable
```bash
python -m pytest -q -p no:cacheprovider -rf $T
```
**Result**: rollback detected (`2 failed, 523 passed`, exit 1).
- `test_contamination_guard_blocks_design_language_and_fields`: `assert 'design_field' in ('implement',)`. Only keyword detection remains.
- `test_contamination_guard_blocks_design_field_without_design_language`: `assert True is False`. A payload carrying design fields but no design language now passes the guard.

Behaviour change under rollback: **field-level detection is lost.** Keyword (design-language) detection still works.

### Step 4: Restore
```bash
git checkout HEAD -- nexus/research/contamination_guard.py
```
The restored sha256 is `d859a968285ee43f644e6acf342dff423c2b39842b0c63aa7cf821324cbde7e8`, identical to pre-drill, and `git status` is clean.

### Step 5: Verify restore
```bash
python -m pytest -q -p no:cacheprovider $T
```
**Result**: ✅ PASS (`525 passed, 21 warnings in 0.58s`, exit 0)

---

## Rollback Drill Result

| Criterion | Status | Note |
|-----------|--------|------|
| Rollback is possible | ✅ Yes | Single-file git checkout to `e3b0ba5eb~1` |
| Rollback is detectable | ✅ Yes | 2 guard unit tests fail and name the lost field-level detection |
| Rollback time | ~15 seconds | Whole drill: 15:06:19Z → 15:06:34Z |
| No data loss | ✅ Yes | Pure function, no state |
| Baseline behavior restored | ✅ Yes | Byte-identical sha256, 525 passed |

---

## Limits

- This drill shows that the guard can be rolled back and restored, and that its tests catch the rollback. It does not show production enforcement on the canonical path (#2199).
- The drill script and full log were kept locally by the drill operator. The results above are copied verbatim from that log.
