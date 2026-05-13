# Nexus Token ROI P82 Flash Hidden-Verifier Closure

Date: 2026-05-13

## Target

Keep the same-model Flash wearing-Nexus benchmark honest while reducing cost:

- preserve verified delivery and trust safety;
- expose token ROI and semantic prompt attribution;
- separate delivery claims from cost-safety and cost-efficiency claims;
- identify the next structural bottleneck without weakening Nexus gates.

## What changed

- Added prompt semantic attribution fields to benchmark rows:
  - `prompt_system_instruction_chars`
  - `prompt_task_constraint_chars`
  - `prompt_source_payload_chars`
  - `prompt_test_payload_chars`
  - `prompt_candidate_payload_chars`
  - `prompt_nexus_control_chars`
  - `prompt_governance_contract_chars`
- Added token ROI fields to evidence bundle checks and claim posture:
  - `verified_lift_rate`
  - `verified_lift_per_1k_with_tokens`
  - `marginal_token_utility`
  - `token_roi_status`
- Added Token ROI output to the markdown public report.

## Verification

Command:

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_gemini_nexus_report.py -q
```

Result:

```text
233 passed in 6.44s
```

Benchmark smoke:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-repair-001,model-required-feature-001,model-required-docs-001 \
  --output-dir .nexus/reports/p82_flash_model_required_token_roi_hidden_3task_1trial \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 1 \
  --timeout-sec 240 \
  --total-timeout-sec 900 \
  --stop-loss-sec 900 \
  --per-task-stop-loss-sec 300 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Key result:

- delivery gate: `PASS`
- with Nexus semantic verified: `1.0`
- bare semantic verified: `0.3333`
- trust mismatch: `0.0`
- token ratio with/bare: `0.6969`
- wall ratio with/bare: `1.9261`
- token ROI status: `EFFICIENT`
- prompt purity max: `1.0`
- cost safety: `FAIL`
- cost efficiency: `REGRESSED`

## Context+ Diagnosis

The new attribution shows this slice is no longer primarily a prompt-contract problem:

- average `prompt_nexus_control_chars_with`: `0.0`
- average `prompt_governance_contract_chars_with`: `0.0`
- hidden retry share: `0.0`
- R/hyper phase wall: `0.0`

The remaining blockers are:

- provider token measured rate for with-Nexus rows is only `0.6667`;
- wall ratio is still high despite token ratio improving.

## Acceptance Gate Verdict

Evidence-first verdict:

- delivery claim: `PASS`
- cost-safety claim: `RETURN`
- cost-efficiency claim: `RETURN`

Reason:

The run proves wearing-Nexus delivery lift under hidden verifier, but it does not yet support a public cost claim because token measurement completeness and wall efficiency are not both passing.

## Why the previous P81 stop was invalid

P81 ran without `NEXUS_VALUE_HIDDEN_VERIFIER=1`, so it produced useful diagnostics but could not satisfy the public delivery contract. That is now written back to learning closure.

## Next action

Fix provider token measurement reliability for supervised-bare / feature-reflex rows, then isolate the remaining wall gap with attempt-level model call timing and gateway latency attribution.
