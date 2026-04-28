# Gemini + Nexus Public Evaluation Protocol

Version: 2026-04-27

## Goal

Produce externally explainable evidence for the difference between `Gemini 3 Flash` running bare and the same model wearing Nexus as a battlesuit. The comparison must answer what improved, how much it improved, and what it cost in wall time, model calls, and tokens.

## Arms

| Arm | Meaning | Requirement |
| --- | --- | --- |
| Bare | Gemini CLI edits the task target directly without Nexus orchestration | `model_calls > 0`, model name recorded, token capture recorded |
| Nexus | Gemini CLI is invoked through Nexus research/battlesuit flow | `gemini_uses_nexus=true`, `nexus_context_delivered=true`, five pillars active, six phases present |

Nexus is not the agent under test. Gemini is the agent. Nexus is the operating layer Gemini wears.

## Model Lock

Every public report must record model name, runner command, Nexus git commit, task manifest path, task manifest SHA-256, run timestamp, timeout settings, prompt transport, and token source.

Rows without model access because of quota, auth, binary, or timeout-before-model-call are infra-invalid rows. They must be reported separately and excluded from solve-rate claims.

## Task Sets

| Stage | Manifest | Purpose |
| --- | --- | --- |
| Smoke | `scripts/bench/capability_tasks_v1.json` | Confirm runner health and measured token capture |
| Hard neutral | `scripts/bench/public_benchmark_hard_neutral_v2.json` | Compare same-model coding performance on harder neutral fixtures |
| Nexus-value | `scripts/bench/public_benchmark_nexus_value_v1.json` | Measure governance, evidence, repair, context, and trust benefits |

The Nexus-value set is the primary publication candidate. The older hard set is useful for calibration but may be too easy for Gemini 3 Flash.

## Required Metrics

Public tables must include solve rate, semantic verified rate, first-pass rate, trust mismatch rate, patch success rate, mutation success rate, average wall time, average model calls, average total tokens, token measured rate, gateway stats source rate, Gemini uses Nexus rate, Nexus context delivered rate, phase completion rate, claim verified rate, Nexus rescue rate, local rescue rate, guard fallback rate, verification rescue rate, and LLM self-heal rate.

Do not collapse rescue types. Guard fallback, verification rescue, local rescue, and LLM self-heal have different meanings and costs.

## Publication Gates

A report is public-safe only if both arms use the same recorded model, both arms have at least 80% measured token rows, Nexus treatment validity is at least 95%, trust mismatch is reported, infra-invalid rows are listed separately, every claimed percentage is derived from raw JSONL rows, and the exact command plus manifest hash are included.

If bare and Nexus both score 100%, do not claim solve-rate lift. In that case the report may only claim observability, governance, rescue evidence, and measured overhead.

## Pre-Benchmark Gate: P1-P13

What：P1-P13 是正式 Run Ladder 前的非模型檢查層，涵蓋 local readiness、model lock、manifest hash、hidden verifier、timeout、evidence bundle、markdown report、public claim gate、CodeIntel、RLM、JIT、MSA 與 token-source policy。

Why：Public report 只接受同模型、可追溯、可重放、eligible 分母清楚的 benchmark。Quota、auth、CLI、timeout-before-model-call、Nexus wearing invalid、evidence missing 都必須先被框住，不能混入 solve-rate claim。

How：先跑 Nexus benchmark preflight，再用同一組 manifest/timeout/trial 參數跑 runner dry validation：

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
uv run python scripts/ops/nexus_benchmark_preflight.py --output-json
```

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --max-tasks 12 --difficulty hard --timeout-sec 180 --total-timeout-sec 3600 \
  --stop-loss-sec 3600 --per-task-stop-loss-sec 600 \
  --force-flow hyper_sprint --with-nexus-runner subprocess \
  --with-llm-mode all --without-mode gemini --force-learn-slo-ready \
  --neutralize-history --disable-learning-loop --repeat-trials 3 \
  --output-dir .nexus/reports/bench_gemini3flash_public_candidate_12x3 \
  --evidence-bundle --markdown-report auto --progress-log --preflight-only
```

`nexus_benchmark_preflight.py` must return `ready_for_benchmark=true` and the runner preflight must return `PASS` before the smoke or publication candidate run starts.

## Run Ladder

Smoke:

```bash
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --max-tasks 3 --difficulty hard --timeout-sec 180 --total-timeout-sec 900 \
  --force-flow hyper_sprint --with-nexus-runner subprocess \
  --with-llm-mode all --without-mode gemini --force-learn-slo-ready \
  --neutralize-history --disable-learning-loop --repeat-trials 1 \
  --output-dir .nexus/reports/bench_gemini3flash_public_smoke_3x1 \
  --markdown-report auto --progress-log
```

Calibration:

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

Publication candidate:

```bash
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --max-tasks 12 --difficulty hard --timeout-sec 180 --total-timeout-sec 3600 \
  --force-flow hyper_sprint --with-nexus-runner subprocess \
  --with-llm-mode all --without-mode gemini --force-learn-slo-ready \
  --neutralize-history --disable-learning-loop --repeat-trials 3 \
  --output-dir .nexus/reports/bench_gemini3flash_public_candidate_12x3 \
  --markdown-report auto --progress-log
```

## Interpretation Rules

Use absolute percentage-point lift as the primary public metric: `Nexus rate - Bare rate`.

Use relative lift only as secondary context: `(Nexus rate - Bare rate) / Bare rate`.

Cost must be stated next to benefit: additional wall seconds per task, additional model calls per task, and additional tokens per task.

## Current Evidence Status

Existing 2026-04-27 Gemini 3 Flash smoke evidence shows that Nexus wearing and token measurement work, but the hard smoke set was too easy:

- bare: 12/12 semantic verified
- Nexus: 12/12 semantic verified
- token capture: measured in both arms
- Nexus wearing: valid in all treatment rows
- conclusion: no solve-rate lift can be claimed from that set

The next public-safe claim requires running the Nexus-value manifest.
