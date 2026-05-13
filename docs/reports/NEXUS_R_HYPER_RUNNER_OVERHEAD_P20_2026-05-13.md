# Nexus R/Hyper Runner Overhead P20 Closure - 2026-05-13

## Goal

Reduce the long-standing Flash+Nexus wall-time distortion where model-required benchmark rows looked expensive because failed baseline/rescue/local fallback work was flattened into R/hyper or runner overhead, while preserving:

- `model_uplift_eligible=1.0` on model-required rows.
- `trust_mismatch_rate=0.0`.
- Clean model/token evidence.
- Nexus capability receipts and delivery gates.

## Root Cause

1. `expand_task_trials()` dropped `eligibility_class`, so `model_required` manifests became ambiguous after trial expansion.
2. Model-required execution policy forced `skip_llm_baseline=False`, which blocked route-cost policy from sending feature/evidence lanes directly to Nexus-selected Hyper.
3. Bounded rescue telemetry flattened first attempt and rescue timing into one row, so failed strict baseline time could be misread as runner overhead.
4. Model calls with no token evidence were classified too late and could appear as Nexus delivery failures rather than provider/token evidence failures.

## Changes

- Preserved `eligibility_class` through trial expansion.
- Added `ModelRequiredExecutionPolicy` so model-required tasks do not imply strict baseline by default.
- Allowed route-cost `skip_llm_baseline` to apply to model-required direct-route lanes unless strict baseline is explicitly requested.
- Added `HyperAdmissionDecision` so unrecoverable model attempts, including model-call-without-token rows, do not blindly enter bounded Hyper rescue.
- Added `runner_overhead_class`, `model_attempts[]`, and composed-rescue timing fields.
- Moved model-required baseline no-token rows to `model_call_without_tokens` before generic Nexus delivery invalidation.

## Evidence

### Unit / Regression

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py -q
184 passed in 4.88s

uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_gemini_nexus_report.py tests/ops/test_codex_nexus_ab_smoke.py tests/ops/test_nexus_pre_flash_gate.py -q
250 passed in 76.73s
```

### Flash Same-Model A/B

Single repair smoke:

```text
.nexus/reports/p34_flash_model_required_policy_smoke
Flash+Nexus: solve=1.0, model_uplift_eligible=1.0, trust_mismatch=0.0
Wall: 54.70s vs bare 49.74s
Runner overhead: 0.53s, polluted_n=0
Tokens: 61,192 vs bare 63,141
```

Feature direct-route confirmation:

```text
.nexus/reports/p36_flash_model_required_feature_direct_route_smoke
Flash+Nexus: solve=1.0, model_uplift_eligible=1.0, trust_mismatch=0.0
Wall: 61.07s vs bare 170.86s
Runner overhead: 0.52s, polluted_n=0
Tokens: 63,414; clean_model_cost_evidence=1.0
```

Three-task model-required smoke:

```text
.nexus/reports/p37_flash_model_required_3task_direct_route_smoke
Flash+Nexus: solve=1.0, semantic_verified=1.0, model_uplift_eligible=1.0
Trust mismatch: 0.0
Runner overhead polluted: 0
Clean model cost evidence: 1.0
Avg wall: 83.87s vs bare 82.30s
Avg tokens: 64,685 vs bare 83,642
```

## Interpretation

P20 closes the first-cost bug: the worst 179s Flash+Nexus row was not a necessary Nexus tax. It was caused by strict baseline plus rescue/local fallback timing being flattened into the wrong metric. After preserving the model-required contract and allowing policy-directed direct routes, Flash+Nexus is cost-comparable to bare on the 3-task model-required smoke while preserving Nexus evidence.

The remaining wall is mostly real R/hyper model-call time, not runner overhead. That should be optimized next through prompt payload, gateway latency, and candidate policy, not by removing governance gates.

## Residual Debt

- `phase_wall_r_sec` remains high because R/hyper contains the primary model call; this is now a clean target rather than polluted telemetry.
- The 3-task smoke is not publication-grade; it is a closure smoke for the runner/R-hyper distortion.
- Full 6-task Flash and Pro reruns remain required before any public claim.

