# Gemini 3 Flash + Nexus Public Claim Draft

Status: draft, not publication-ready

## Claim Boundary

The current evidence proves that Gemini can wear Nexus and produce measured, auditable benchmark rows.

It does not yet prove solve-rate lift, because the latest 6x2 hard smoke was solved by both arms.

## Current Measured Evidence

Run source:

- `.nexus/reports/bench_gemini3flash_nexus_smoke_6x2/with_nexus_1777237537.jsonl`
- `.nexus/reports/bench_gemini3flash_nexus_smoke_6x2/without_nexus_1777237537.jsonl`
- `.nexus/reports/bench_gemini3flash_nexus_smoke_6x2/gemini_nexus_report_1777237537.md`

Result:

| Metric | Gemini 3 Flash bare | Gemini 3 Flash + Nexus | Public interpretation |
| --- | ---: | ---: | --- |
| Semantic verified | 12/12 | 12/12 | no solve-rate lift claim |
| Solve rate | 100% | 100% | benchmark too easy |
| Avg wall time | 21.73s | 67.16s | Nexus costs +45.43s/task |
| Avg tokens | 25,088 | 53,418 | Nexus costs +28,330 tokens/task |
| Avg model calls | 1.00 | 1.83 | Nexus costs +0.83 calls/task |
| Token source | measured | measured | cost data is usable |
| Nexus wearing | n/a | 12/12 valid | treatment delivery verified |

## What Nexus Value Is Already Demonstrated

The evidence supports these internal claims:

- Gemini was actually invoked through Nexus in treatment rows.
- Nexus context was delivered.
- Five-pillar and six-phase evidence was present.
- Token telemetry came from Gemini CLI stats rather than only estimates.
- Bounded self-heal and rescue mechanisms are observable as separate report fields.
- Report trust is auditable row by row.

## What Cannot Be Publicly Claimed Yet

Do not claim:

- "Nexus improves Gemini 3 Flash solve rate by X%" from the current hard smoke.
- "Nexus is faster" from the current hard smoke.
- "Nexus uses fewer tokens" from the current hard smoke.

Those statements are contradicted or unsupported by the current data.

## Publication-Ready Claim Template

After running `scripts/bench/public_benchmark_nexus_value_v1.json`, fill this:

> On a frozen 12-task Nexus-value benchmark with 3 trials per task, Gemini 3 Flash + Nexus improved semantic verified rate from `<bare>%` to `<nexus>%` (`<delta>` percentage points), changed trust mismatch from `<bare>%` to `<nexus>%`, and achieved `<nexus_wearing>%` valid Nexus wearing evidence. The cost was `<wall_delta>` additional seconds, `<token_delta>` additional tokens, and `<call_delta>` additional model calls per task on average.

Required appendix:

- Nexus git commit
- model name
- task manifest SHA-256
- raw JSONL paths
- markdown report path
- excluded infra-invalid rows
- rerun command

## Next Required Run

Run the Nexus-value calibration first:

```bash
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --max-tasks 12 --difficulty hard --timeout-sec 180 --total-timeout-sec 2400 \
  --force-flow hyper_sprint --with-nexus-runner subprocess \
  --with-llm-mode all --without-mode gemini --force-learn-slo-ready \
  --neutralize-history --disable-learning-loop --repeat-trials 2 \
  --output-dir .nexus/reports/bench_gemini3flash_public_calibration_12x2 \
  --markdown-report auto --progress-log
```

If bare remains above 90%, the benchmark is still too easy. If bare falls below 30%, the benchmark is too adversarial for a balanced product claim.
