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

---

## Addendum: canonical-path enforcement point drill (#2199)

**Date**: 2026-10-14 (drill run 15:59:16Z–15:59:32Z)
**Worktree HEAD**: `1f0e0cb5ebc401bc857d603406a3b8a7774be066` (#2199 branch commit before rebase/push)
**Enforcement point under test**: `nexus/core/capability_executor_registry.py` (`_research_contamination_block`, called from `_exec_research`)
**Rollback target**: `HEAD~1` = `7b4f680ce94d453deba9f9bb69d7f24c5cd1dd70` (main without the enforcement point)

#2199 moved P-CONTAM-01 enforcement onto the canonical research executor. That is new code, so this drill covers it separately from the guard drill above.

`T="tests/research/test_research_contamination_canonical_path.py tests/research/test_research_isolation.py tests/services/test_capability_wiring_fixes_batch1.py"`, run with the worktree's own `uv sync --frozen --all-extras` venv and `PYTHONPATH=$PWD`.

| Step | Command | Result |
|------|---------|--------|
| 1 Baseline | `python -m pytest -q -p no:cacheprovider $T` | `65 passed`, exit 0. File sha256 `0aee13506ada83ced3cde7c8fc97415b801d43aa2620928333f1cce2018dcae2` |
| 2 Roll back | `git checkout HEAD~1 -- nexus/core/capability_executor_registry.py` | sha256 `8b25293cd2d93038ac26cf4be6b8e1eda1ee4802737cc4468d20a0318e23d667`, 60 lines removed (the whole enforcement point) |
| 3 Detect | `python -m pytest -q -p no:cacheprovider -rf $T` | `4 failed, 61 passed`, exit 1: `test_canonical_research_blocks_design_language`, `test_canonical_research_blocks_design_field`, `test_canonical_research_blocks_nested_design_field`, `test_canonical_research_guard_error_fails_closed` (each `assert result["gate_passed"] is False`) |
| 4 Restore | `git checkout HEAD -- nexus/core/capability_executor_registry.py` | sha256 `0aee1350…dcae2`, identical to pre-drill; `git status` clean for the file |
| 5 Verify | `python -m pytest -q -p no:cacheprovider $T` | `65 passed`, exit 0 |

Behaviour under rollback: the canonical executor again returns PASS for contaminated research output and for a broken guard. The clean-output test keeps passing, so the rollback leaves clean research unchanged. Rollback time was about 16 seconds, with no state or data involved.

Limits: the line numbers in the PR may differ after rebase, but the drilled function is unchanged. The drill script and log were kept locally by the drill operator; the results above are copied from that log.

---

## Addendum 2: phrase-level check, auto-flow wiring and guard `terms` parameter (#2216, Owner option A)

**Date**: 2026-10-14 (drill run 23:20:24Z–23:22:16Z)
**Worktree HEAD**: `36240678fe99dd3c0358c59c111d6d60b3debdb7` (#2216 branch)
**Rolled back**: `nexus/core/capability_executor_registry.py`, `nexus/app/research_flow_service.py`, `nexus/research/contamination_guard.py`
**Rollback target**: the branch's merge-base with main, `0d03612850e86a57ea05af42b211949572d984ff` (no enforcement anywhere)

Addendum 1 drilled the first version of the enforcement point (`1f0e0cb5e`). That version has since been replaced. The wiring now calls `nexus/research/contamination_enforcement.py` from both the canonical executor and the research auto-flow, and the guard has a new `terms` parameter, so the drill was repeated. The enforcement module stays in place during the drill, but nothing calls it after the rollback.

`T="tests/research/test_research_contamination_canonical_path.py tests/research/test_research_isolation.py tests/services/test_capability_wiring_fixes_batch1.py"`, run with the worktree's own `uv sync --frozen --all-extras` venv and `PYTHONPATH=$PWD`.

| Step | Command | Result |
|------|---------|--------|
| 1 Baseline | `python -m pytest -q -p no:cacheprovider $T` | `79 passed`, exit 0 |
| 2 Roll back | `git checkout 0d0361285 -- <3 files>` | 3 files changed, 4 insertions, 71 deletions. The sha256 prefixes are `8b25293cd2d93038` (registry), `7c6f254af7b99c9c` (flow service) and `d859a968285ee43f` (guard), matching the main versions |
| 3 Detect | `python -m pytest -q -p no:cacheprovider -rf $T` | `14 failed, 65 passed`, exit 1. Failures: all 10 canonical-executor BLOCK tests (design language, design field, nested field, guard error, echo plus contamination, blocked_assumptions ×2, summary, raw.answer, non-schema key), `test_guard_terms_parameter_keeps_legacy_default`, and all 3 auto-flow BLOCK tests |
| 4 Restore | `git checkout HEAD -- <3 files>` | sha256 prefixes are identical to pre-drill (`e2b260600ce69262`, `a0e30e3775feeb44`, `ebda28d136869c54`), and `git status` is clean |
| 5 Verify | `python -m pytest -q -p no:cacheprovider $T` | `79 passed`, exit 0 |

Under rollback, the canonical executor and the auto-flow again accept contaminated research. The clean-output, echo and normal-software-text tests keep passing, so rolling back changes only the blocking. Rollback took about 2 minutes, including three test runs, and involves no state.

Limits: the drill script and its log were kept locally by the drill operator, and the results above are copied from that log. Commit SHAs refer to the PR branch before squash-merge.
