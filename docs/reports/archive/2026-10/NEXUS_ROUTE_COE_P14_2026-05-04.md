# Nexus Route COE (P14) - 2026-05-04

## Scope
- Branch/worktree: `ad59`
- Goal: stop drifting toward governance-only behavior and verify whether routing actually executes the intended capability composition.
- Dataset used for evidence: `gemini-3-flash-preview` merged `12x1` report at:
  - `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/bench_flash_public_12x1_merged_20260504/gemini_flash_nexus_public_report_2026-05-04.md`

## Blameless Findings
1. Public claim gate still failed because bare arm had infra-invalid rows (`run_eligibility_incomplete`), so this run cannot be final public proof.
2. Capability selection friction is high in treatment: many capabilities are selected but not invoked/evidenced.
3. Existing report focused on end metrics (solve/semantic/trust) but lacked route-funnel metrics, making route quality regressions hard to catch early.
4. Route smoke previously did not enforce strict nine-capability identity at summary level.

## Five Whys (System)
1. Why did uplift look small this round?
   Because bare eligible solve was already high (ceiling effect) and part of the run was eligibility-noisy.
2. Why was eligibility noisy?
   Because quota/infra invalid rows entered the comparison window for one arm.
3. Why did we not catch route over-selection early?
   Because report lacked selected->invoked->evidence->outcome funnel metrics.
4. Why did route smoke not block identity drift?
   Because no strict nine-capability union identity check existed in smoke summary.
5. Why did this slip into benchmark phase?
   Because benchmark cadence outpaced route-quality guardrails.

## Action Items Completed (This Pass)
1. Added route-funnel quality metrics in benchmark markdown generation:
   - `Selected -> Invoked`
   - `Invoked -> Evidence`
   - `Evidence -> Outcome`
   - `Unnecessary Selected`
2. Added strict nine-capability identity gate (union of `route_oracles + belief_gate`) in smoke summary flow.
3. Added/updated tests to lock these behaviors:
   - `tests/benchmark/test_gemini_nexus_report.py`
   - `tests/ops/test_capability_route_smoke.py`

## Verification
- `uv run pytest -q tests/ops/test_capability_route_smoke.py` -> pass
- `uv run pytest -q tests/benchmark/test_gemini_nexus_report.py` -> pass
- Regenerated report includes `## Route Quality` section.

## Remaining Risk
1. `run_eligibility_incomplete` still blocks final public claim for this specific merged Flash run.
2. Route quality is now measurable, but not yet used as hard promotion gate in CI.

## Next Gate (for final publication)
1. Re-run Flash same-model A/B until `public claim gate = PASS`.
2. Require minimum route-funnel thresholds before promotion:
   - selected->invoked >= 70%
   - invoked->evidence >= 95%
   - evidence->outcome >= 90%
   - unnecessary_selected <= 30%
3. Only then run Pro full lane and publish final bilingual report.
