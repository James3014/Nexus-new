---
type: report
status: current
---

# NEXUS Always-On Loop Status 2026-05-07

## Scope

- Models:
  - `gemini-3-flash-preview`
  - `gemini-3.1-pro-preview`
- Tasks:
  - `nexus-value-hidden-001`
  - `nexus-value-repair-002`
  - `nexus-value-gov-001`
- Benchmark contract:
  - same-model bare vs same-model Nexus
  - hidden verifier on
  - `--enable-autoreason-executor`
  - `--enable-ddtree-executor`
  - `--enable-ultra-review-dry-gate`
  - `--llm-candidate-cap 3`

## Loop 0

Status: `PROMOTE`

- `gemini-3-flash-preview` preflight: `PASS`
- `gemini-3.1-pro-preview` preflight: `PASS`
- model lock confirmed for both:
  - `env_model_name == direct_model_name`

## Loop 1

Status: `PROMOTE`

Cost truth for `gemini-3-flash-preview`:

- bare:
  - verified: `2/3`
  - trust mismatch: `0.0`
  - avg wall: `19.34s`
  - avg tokens: `43482`
- Nexus:
  - verified: `3/3`
  - trust mismatch: `0.0`
  - avg wall: `60.18s`
  - avg tokens: `45192.67`
  - avg phase wall total: `55.87s`
  - avg cli uninstrumented: `4.03s`

Cost truth for `gemini-3.1-pro-preview`:

- bare:
  - verified: `1/3`
  - trust mismatch: `0.0`
  - avg wall: `24.55s`
  - avg tokens: `41210`
- Nexus:
  - verified: `3/3`
  - trust mismatch: `0.0`
  - avg wall: `34.62s`
  - avg tokens: `41525`
  - avg phase wall total: `30.14s`
  - avg cli uninstrumented: `4.15s`

Readout:

- `Nexus` still provides real solve lift on `repair` and `governance`.
- `Flash` and `3.1 Pro` both pay most of their extra wall time inside `phase_wall_total`, not `runner_overhead`.
- token delta is small relative to wall delta.

## Loop 2

Status: `HOLD`

Observed route profile telemetry:

- hidden:
  - selected: `12`
  - high-cost selected: `research`
- repair:
  - selected: `17`
  - high-cost selected: `research`
- governance:
  - selected: `18`
  - high-cost selected: `research`, `ultra_review`, `sandbox`

Readout:

- lane split is real:
  - hidden is lighter than governance
  - governance legitimately triggers hardened capabilities
- but route slimming is not yet sufficient:
  - hidden still carries `research`
  - repair is not recognized as bounded repair in current benchmark contract path

Decision:

- keep current route evidence
- do not promote route loop as "cost fixed"

## Loop 3

Status: `PROMOTE`

Readout:

- current main wall driver is `phase_wall_total_sec`
- `runner_overhead_sec` is low in both models:
  - Flash Nexus avg `0.2772s`
  - Pro Nexus avg `0.3306s`

Decision:

- runtime shell/process cost is not the main blocker
- orchestration work inside phases is the main blocker

## Loop 4

Status: `HOLD`

Observed prompt/context telemetry:

- hidden:
  - prompt chars: `416`
  - payload chars: `2115`
- repair:
  - prompt chars: `416`
  - payload chars: `1804`
- governance:
  - prompt chars: `416`
  - payload chars: `2028`

Readout:

- payload is non-trivial but not yet proven to be the dominant token source.
- current blocker is still phase work plus over-opened high-cost route in hidden/repair.

Decision:

- keep prompt/context loop open
- do not promote until route and phase work are reduced together

## Loop 5

Status: `PROMOTE`

Lane decision:

- `hidden` -> `always_on_lite_candidate`
- `repair` -> `always_on_standard_candidate`
- `governance` -> `always_on_hardened_candidate`

Reason:

- hidden bare already solves, so Nexus must justify itself by lower always-on cost.
- repair bare fails on both weak models.
- governance bare fails on `3.1 Pro` and requires trust-safe guardrails.

## Loop 6

Status: `PROMOTE`

Cross-model result:

- same lane shape appears in both models:
  - hidden is the weakest Nexus value lane
  - repair and governance are the strongest Nexus value lanes

Decision:

- keep lane strategy as shared weak-model policy, not model-specific patching

## Loop 7

Status: `HOLD`

Readout:

- learning closure already records policy hits and route ROI inputs
- this round did not yet prove that recent-N learning lowered always-on cost on the next run

Decision:

- no promotion until the learned lane policy measurably reduces hidden/repair overhead

## Loop 8

Status: `HOLD`

Readout:

- model-training export path exists
- this round focused on runtime always-on viability, not retraining effect

Decision:

- keep export path active
- do not count it as cost closure yet

## Loop 9

Status: `HOLD`

Current closure verdict:

- `Nexus` is already justified as a task-typed weak-model enhancer.
- `Nexus` is not yet justified as a universally cheap always-on layer.

Current best statement:

1. `repair` and `governance` already show strong wearing value.
2. `hidden` is still overpaying for wearing.
3. The next cost target is not generic runner overhead.
4. The next cost target is:
   - hidden/repair route de-overopening
   - phase work reduction inside always-on Lite/Standard lanes

## Next Gate

Only one optimization loop should run next:

1. patch the runtime route seam that materializes `route["capability_plan"]`, not only the standalone planner seam
2. make hidden/repair stop auto-opening `research` under the public benchmark contract
3. preserve verified rate and trust mismatch
4. rerun the same `3x1` matrix for both Gemini models
5. only if hidden wall/tokens drop without verified regression, promote the always-on lane

## Loop 2 Retry

Status: `HOLD`

Retry result:

- attempted seam:
  - `nexus/engine/policy_evaluator.py`
- local planner verification:
  - hidden synthetic replay dropped to the `L0_micro_patch` gate-only stack
  - repair synthetic replay removed `research`
- benchmark result:
  - runtime `with_nexus` still emitted:
    - hidden selected `12` with `research`
    - repair selected `17` with `research`

## Phase A Update

Status:

- `Flash`: `PROMOTE`
- `3.1 Pro`: `HOLD`

What changed:

- route pre-classification now strips the appended benchmark contract suffix
- hidden / bounded repair route rules now normalize `public_*` task types
- benchmark hidden / bounded repair fast paths cap risk before routing tier escalation

Local route replay after patch:

- `public_bugfix` hidden:
  - `should_research=false`
  - selected no longer includes `research`
  - high-cost selected: none
- `public_test_repair` repair:
  - `should_research=false`
  - selected no longer includes `research`
  - high-cost selected: none
- `public_refactor` governance:
  - retains `research`, `ultra_review`, `sandbox`

Flash `3x1` rerun:

- previous with_nexus:
  - avg wall: `73.12s`
  - avg tokens: `49441.67`
- patched with_nexus:
  - avg wall: `46.25s`
  - avg tokens: `44450.67`
- patched rows:
  - hidden selected: `autoreason`, `judge_panel`, `delivery_gate`, `mempalace_gate`, `artifact_gate`, `claim_gate`
  - repair selected: `codeintel`, `hyper`, `autoreason`, `judge_panel`, `ddtree`, `memory`, `asi_constraint_extractor`, `belief`, `repair_loop`, `research_route`, `delivery_gate`, `mempalace_gate`, `artifact_gate`, `claim_gate`
  - governance remains hardened

`3.1 Pro` `3x1` rerun:

- with_nexus:
  - solve: `3/3`
  - avg wall: `66.52s`
  - avg tokens: `42003`
- route rows match the same lane shape as Flash:
  - hidden/repair no longer select `research`
  - governance remains hardened

Readout:

- the route-fix is real across both Gemini models
- Flash gets real cost improvement from the route closure
- `3.1 Pro` keeps the route improvement, but wall time did not improve enough yet
- next bottleneck for `3.1 Pro` is phase work / prompt payload, not route misclassification

Decision:

- promote the route-fix for Flash
- keep Pro on `HOLD`
- next optimization loop should target:
  - `phase_wall_total_sec`
  - lane-specific prompt/context reduction
  - runtime tactical sequence still contained:
    - hidden: `baseline -> memory -> research -> ...`
    - repair: `hyper_sprint -> pregate -> memory -> research -> ...`

Decision:

- do not promote the planner-seam patch
- the live runtime still uses another upstream route seam when populating `route["capability_plan"]`
- next loop must target runtime route materialization, not planner policy alone

## Phase C Contract Correction

Status:

- `always-on benchmark contract`: `PROMOTE`

What changed:

- `always-on` evaluation is now treated as a separate contract from `forced-hyper` evaluation
- `scripts/bench/capability_ab_runner.py` rejects `--always-on-eval` when combined with:
  - `--force-flow != auto`
  - `--skip-llm-baseline`
  - `--llm-safe-probe`

Why:

- first-pass `Phase C` diagnosis showed `R` phase dominance
- row inspection then showed the benchmark contract itself was forcing:
  - `strategy_path=hyper_direct_forced`
- without closing that contract leak, wall/token analysis for hidden/repair would remain polluted

Next gate:

- rerun `Flash` and `Gemini 3.1 Pro` with:
  - `--always-on-eval`
  - `--force-flow auto`
- only then continue `Phase C/D` phase-work and prompt/context slimming

## Phase C Auto-Contract Rerun

Status:

- `Flash`: `HOLD`
- `3.1 Pro`: `REVERT`

Flash `3x1` under valid always-on contract:

- with_nexus:
  - solve: `3/3`
  - avg wall: `58.59s`
  - avg phase wall: `49.72s`
  - avg tokens: `47445.67`
- bare:
  - solve: `2/3`
  - avg wall: `26.46s`
  - avg tokens: `44333.67`
- row readout:
  - hidden:
    - `strategy_path=baseline_only`
    - `R=57.29s`
    - `tokens=50436`
  - repair:
    - `strategy_path=hyper_direct_hard_skip_probe`
    - `R=46.45s`
  - governance:
    - `strategy_path=hyper_direct_hard_skip_probe`
    - `R=24.12s`

Readout:

- valid always-on contract preserved Flash solve lift
- but it did **not** reduce cost versus the previous route-fixed run
- the dominant hidden cost moved into `baseline_only` execution inside `R`

`3.1 Pro` `3x1` under valid always-on contract:

- with_nexus:
  - solve: `2/3`
  - trust mismatch: `1/3`
  - avg wall: `85.08s`
  - avg phase wall: `76.19s`
  - avg tokens: `41629`
- bare:
  - eligible solve: `1/2`
  - one bare row infra-invalid: `quota_exhausted`
- row readout:
  - hidden:
    - `strategy_path=baseline_only`
    - `R=35.25s`
  - repair:
    - `strategy_path=hyper_direct_hard_skip_probe`
    - `R=147.66s`
  - governance:
    - `FAILED`
    - `trust_mismatch=True`
    - `R=28.11s`

Decision:

- keep the always-on benchmark contract fix
- do not promote auto-lane cost closure yet
- next loop must target:
  - `Flash hidden baseline_only` R-path slimming
  - `3.1 Pro repair` R-path slimming
  - `3.1 Pro governance` trust regression triage before any further cost work
