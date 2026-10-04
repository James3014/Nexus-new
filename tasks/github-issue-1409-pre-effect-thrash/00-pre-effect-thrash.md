# Issue #1409: Bounded Pre-Effect Tool Thrash Watchdog

## Goal
Bound tool-active pre-effect thrash so that operations producing structured tool activity without ever creating a source effect terminate as `PRE_EFFECT_TOOL_THRASH` instead of consuming full timeout budget.

## Base Context and Scope Boundary
- The enclosing progress watchdog framework `if expect_coding_progress and not first_effect_seen.is_set():` (lines 1423+) and immediate boundary readback `direct_operation_journal.observed_changed_paths_since(...)` (lines 1450+) are part of base revision `4f4e52787621e31adb00cd4e9136362d72a144e7` (merged via PR #1407 for #1351).
- Issue #1409 operates within that established harness to introduce bounded pre-effect tool thrash detection and taxonomy.

## Key Changes
1. **Independent pre-effect budget**:
   - Captures `first_tool_monotonic` on the first observed structured tool event.
   - Evaluates `(now - first_tool_monotonic >= resolved_pre_effect_max_seconds or tool_event_count >= resolved_pre_effect_max_tool_events)`.
   - Fires `non_progress_failure = "PRE_EFFECT_TOOL_THRASH"` when threshold is exceeded before first source effect.
2. **Configurable bounds**:
   - `pre_effect_max_seconds` (default 90s, env `NEXUS_AGY_PRE_EFFECT_MAX_SECONDS` / `--pre-effect-max-seconds`)
   - `pre_effect_max_tool_events` (default 24, env `NEXUS_AGY_PRE_EFFECT_MAX_TOOL_EVENTS` / `--pre-effect-max-tool-events`)
3. **Non-rotation taxonomy**:
   - Added `AccountFailureKind.PRE_EFFECT_TOOL_THRASH`.
   - Verified non-rotation-eligible by dedicated unit test `test_pre_effect_tool_thrash_is_non_rotation_eligible`.
4. **Mode invariant enforcement**:
   - Strictly enforced at the entry of `run_agy`: `expect_coding_progress = bool(expect_coding_progress and mode == "accept-edits")`.
   - Unconditionally exempts read-only modes (plan, review) even if caller passes `expect_coding_progress=True`. Verified by `test_run_agy_plan_mode_exempt_from_pre_effect_budget_even_if_expect_coding_progress_passed`.
5. **False positive protection**:
   - Once a source effect is witnessed, `first_effect_seen` is permanently set, preventing watchdog termination.
   - Immediate boundary scan at lines 1450-1473 rechecks worktree state right before declaring failure; any effect that landed clears `non_progress_failure`.
