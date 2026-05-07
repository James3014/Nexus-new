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
  - runtime tactical sequence still contained:
    - hidden: `baseline -> memory -> research -> ...`
    - repair: `hyper_sprint -> pregate -> memory -> research -> ...`

Decision:

- do not promote the planner-seam patch
- the live runtime still uses another upstream route seam when populating `route["capability_plan"]`
- next loop must target runtime route materialization, not planner policy alone
