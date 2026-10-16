# Nexus Model-Required Uplift Gate - 2026-05-13

## Final Goal

Make future weak-model wearing-Nexus benchmarks prove model participation, not deterministic local-preflight substitution. `Gemini 3 Flash + Nexus` / `Gemini 3.1 Pro + Nexus` may use Nexus routing, evidence, gates, and repair, but model-uplift claims require an actual model response and model-sourced final delivery.

## What Changed

- Added row-level `model_uplift_eligible` separate from ordinary `run_eligible` and `nexus_wearing_valid`.
- Added task-level `eligibility_class` with `deterministic_contract`, `model_required`, and `bare_model_only` values.
- Added a frozen `model_required` benchmark slice: `scripts/bench/public_benchmark_model_required_uplift_v1.json`.
- For `eligibility_class=model_required`, benchmark runner forces strict LLM baseline and disables local preflight / hidden-contract fast path.
- Kept deterministic local-preflight delivery valid for Nexus cost-closure, but blocked it from weak-model uplift claims.
- Added `NEXUS_CODEX_IGNORE_USER_CONFIG=1` support for Codex benchmark runs so GPT-5.5 bare can bypass a broken local `skillclaw` provider without mutating `~/.codex/config.toml`.

## Verification

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py -q
# 180 passed

uv run pytest tests/benchmark/test_capability_ab_runner.py tests/ops/test_codex_nexus_ab_smoke.py tests/ops/test_nexus_pre_flash_gate.py -q
# 219 passed

uv run pytest tests/benchmark/test_capability_ab_runner.py tests/research/test_sprint_service.py tests/app/test_research_flow_service.py tests/benchmark/test_gemini_nexus_report.py tests/ops/test_capability_route_smoke.py tests/ops/test_capability_invocation_matrix.py -q
# 373 passed

uv run python scripts/ops/capability_route_smoke.py --print-only
# passed=true; public_benchmark_claim_allowed=false as expected for nexus-only smoke

uv run python scripts/ops/capability_route_smoke.py
# passed=true
```

Manifest check:

```text
tasks 6
classes ['model_required']
shape_failures []
```

Provider calibration:

```text
codex exec -m gpt-5.5 with user config:
provider=skillclaw; FAIL; http://127.0.0.1:30000/v1/responses disconnected

codex exec --ignore-user-config -m gpt-5.5:
provider=openai; PASS; CODEX_DEFAULT_PROVIDER_OK; tokens used 15,301
```

Model-required one-task smoke:

| Arm | Report | Solve | Trust Mismatch | Model Calls | Tokens | Wall Sec | R/Hyper Sec | Model Uplift Eligible |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.5 bare | `.nexus/reports/p31_gpt55_bare_model_required_smoke` | 1.0 | 0.0 | 1 | 15,628 | 13.9 | 0.0 | 1.0 |
| Gemini 3 Flash bare | `.nexus/reports/p32_flash_model_required_smoke` | 1.0 | 0.0 | 1 | 61,886 | 44.7 | 0.0 | 1.0 |
| Gemini 3 Flash + Nexus | `.nexus/reports/p32_flash_model_required_smoke` | 1.0 | 0.0 | 2 | 59,278 | 179.6 | 34.8 | 1.0 |
| Gemini 3.1 Pro bare | `.nexus/reports/p33_pro_model_required_smoke` | 1.0 | 0.0 | 1 | 57,204 | 27.9 | 0.0 | 1.0 |
| Gemini 3.1 Pro + Nexus | `.nexus/reports/p33_pro_model_required_smoke` | 1.0 | 0.0 | 2 | 115,048 | 87.3 | 28.3 | 1.0 |

Route smoke summary:

| Suite | Tasks | Selected->Invoked | Invoked->Evidence | Evidence->Outcome | Unnecessary Selected | Failures |
|---|---:|---:|---:|---:|---:|---:|
| route_oracles | 8 | 0.9864864864864865 | 1.0 | 1.0 | 0.013513513513513514 | 0 |
| codeintel_hyper | 2 | 1.0 | 1.0 | 1.0 | 0.0 | 0 |
| core_governance_gates | 2 | 1.0 | 1.0 | 1.0 | 0.0 | 0 |
| belief_gate | 1 | 1.0 | 1.0 | 1.0 | 0.0 | 0 |
| runtime_receipt_oracles | 2 | 1.0 | 1.0 | 1.0 | 0.0 | 0 |
| harness_engineering_oracles | 2 | 1.0 | 1.0 | 1.0 | 0.0 | 0 |

## Current Boundary

This closes the infrastructure gap that caused P28 to look like the final goal while all tasks were solved by deterministic local preflight. It does not yet prove the final public claim. The next run must execute the model-required slice across:

- `GPT-5.5 bare`
- `Gemini 3 Flash bare`
- `Gemini 3 Flash + Nexus`
- `Gemini 3.1 Pro bare`
- `Gemini 3.1 Pro + Nexus`

A row can be used for weak-model uplift only when `model_uplift_eligible=true`.

The current evidence shows the gate is now honest: Flash/Pro wearing Nexus are model-required eligible and trust-safe on the smoke task, but wall time is still too high versus GPT-5.5 bare and same-model bare. The next closure target is therefore not more eligibility plumbing; it is R/hyper and runner-overhead wall-time reduction while preserving `model_uplift_eligible=true` and `trust_mismatch=0`.
