# NEXUS P95 Refactor and Route Verification Report

Date: 2026-05-05
Branch: main
Scope: P87-P95, no Pro validation

## Executive Result

P95 completed the next hardening slice after P86: memory/provider seams, healing artifact persistence, belief shift telemetry, Secure Sync bounded request decoding, route smoke regression, research-stack invocation proof, and a small Gemini 3 Flash A/B regression.

## Completed Phases

| Phase | Result | Evidence |
| --- | --- | --- |
| P87 Provider seams | PASS | `MemoryService` accepts injected JSONL store; `MemPalace` accepts belief/config stores. |
| P88 Scoped memory access | PASS | File-backed JSONL and Lance belief/config adapters isolate persistence behind protocols. |
| P89 DDTree receipt hygiene | PASS | Non-actionable selected-only DDTree cases are marked `no_pruning_opportunity` / `feature_flag_disabled`. |
| P90 Belief telemetry | PASS | `BeliefEngine.process_audit_outcome()` now emits `belief.shift` event through `NexusTracer`. |
| P91 Secure Sync hardening | PASS | Incoming mTLS JSONL request decoding is size-bounded and rejects invalid/non-object payloads. |
| P92 Route smoke | PASS | Capability route smoke passed across route_oracles, codeintel_hyper, core gates, and belief gate. |
| P93 Healing artifact contract | PASS | `HealingArtifact` round-trip persistence added under `.nexus/artifacts/healing/`. |
| P94 Flash regression | PASS | Gemini 3 Flash 2x1 A/B completed with public gates PASS. |
| P95 Report/lesson closure | PASS | This report plus ADR-013 capture evidence and the uv-cache sandbox lesson. |

## Verification Evidence

### Unit / Contract Tests

Command:

```bash
uv run pytest -q tests/core/test_mem_palace.py tests/test_memory.py tests/core/test_healing_artifacts.py tests/infrastructure/test_storage_implementations.py tests/engine/test_capability_routing_contracts.py tests/core/test_belief_engine.py tests/security/test_secure_sync.py tests/telemetry/test_tracer.py
```

Result: `60 passed in 1.37s`.

### Capability Route Smoke

Command:

```bash
python3 scripts/ops/capability_route_smoke.py
```

Result: `passed=true`, summary path `.nexus/reports/capability_route_smoke_summary.json`.

Key route quality:

| Suite | Tasks | Selected -> Invoked | Invoked -> Evidence | Evidence -> Outcome | Unnecessary Selected |
| --- | ---: | ---: | ---: | ---: | ---: |
| route_oracles | 8 | 100.0% | 102.1% | 97.9% | 0.0% |
| codeintel_hyper | 2 | 95.5% | 100.0% | 100.0% | 4.5% |
| core_governance_gates | 2 | 100.0% | 100.0% | 100.0% | 0.0% |
| belief_gate | 1 | 100.0% | 100.0% | 100.0% | 0.0% |

Latest 8-oracle file: `.nexus/reports/bench_route_8oracle_smoke/with_nexus_1777983460.jsonl`.

### Research Stack Route Smoke

Command:

```bash
python3 scripts/ops/research_stack_route_smoke.py --jsonl .nexus/reports/bench_route_8oracle_smoke/with_nexus_1777983460.jsonl --require-autoreason-invoked
```

Result: `passed=true`.

Key metrics:

| Metric | Value |
| --- | ---: |
| rows | 8 |
| autoreason selected | 8 |
| autoreason invoked | 8 |
| autoreason A/B/AB factory ready | 8 |
| autoreason AB winner | 8 |
| research doctor pass | 8 |
| claim probe gate passed | 8 |
| source projects seen | autoreason, autoresearch, autoresearchclaw, codex-autoresearch |

Checkpoints seen:

- `candidate_tournament_receipt`
- `claim_citation_verification`
- `fixed_budget_metric_contract`
- `packet_session_ledger`

### Gemini 3 Flash P94 Regression

Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin NEXUS_GATEWAY_COMPACT_PROMPT=1 NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 uv run python scripts/bench/capability_ab_runner.py --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json --output-dir .nexus/reports/bench_gemini3flash_value2x1_20260505_p94 --max-tasks 2 --repeat-trials 1 --timeout-sec 420 --total-timeout-sec 1800 --stop-loss-sec 900 --per-task-stop-loss-sec 600 --difficulty all --repo-kind-filter all --force-flow hyper_sprint --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini --force-learn-slo-ready --neutralize-history --disable-learning-loop --materialize-missing --isolation-mode preserve_target --evidence-bundle --markdown-report auto --progress-log
```

Report: `.nexus/reports/bench_gemini3flash_value2x1_20260505_p94/gemini_nexus_report_1777983678.md`.

Key result:

| Metric | Bare Flash | Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Usable rows | 2/2 | 2/2 | n/a |
| Solve rate | 100.0% | 100.0% | 0.0% |
| Semantic verified | 100.0% | 100.0% | 0.0% |
| Trust mismatch | 0.0% | 0.0% | 0.0% |
| Avg wall time | 33.53s | 42.65s | +9.12s |
| Avg model calls | 1.00 | 1.00 | 0.00 |
| Public claim gate | PASS | PASS | n/a |
| Route Quality Selected -> Invoked | 0.0% | 100.0% | +100.0% |
| Route Quality Unnecessary Selected | 0.0% | 0.0% | 0.0% |

Interpretation: the P94 run is a regression/sanity A/B, not the public headline run. The stronger Flash headline remains the P75 12x2 run: Flash + Nexus 24/24 vs bare 14/24, +41.7pp solve-rate delta, all public gates PASS.

## Failure-to-Lesson Writeback

Failure: first sandboxed route smoke produced empty suite summaries because `uv` could not read `/Users/jameschen/.cache/uv/sdists-v9/.git`.

Lesson: route smoke summaries with `tasks=0` after subprocess permission errors must be treated as infrastructure invalid, not route-quality failure. The corrected action is to rerun with unrestricted command approval and record the generated JSONL path before interpreting funnel metrics.

Writeback: `docs/arch/ADR-013-P95-Route-Smoke-Evidence.md`.

## Residual Debt

- Pro validation intentionally skipped per instruction until later than P95.
- P94 Flash A/B is only 2x1; use P75 12x2 as the stronger current public evidence.
- Existing unrelated dirty files remain outside this slice and were not staged.
- Secure Sync now validates request framing; deeper authZ policy per action/client remains a later hardening item.

## Next Plan P96-P105

| Phase | Task | Gate |
| --- | --- | --- |
| P96 | Add route-smoke infra-invalid classifier for uv/cache permission failures | Empty suite cannot masquerade as route failure. |
| P97 | Promote route-quality thresholds into CI gate for selected->invoked / evidence / outcome / unnecessary-selected | Gate fails below agreed thresholds. |
| P98 | Add Secure Sync client authorization matrix by action and node identity | Unauthorized action returns explicit deny. |
| P99 | Wire healing artifact readback into recovery/report path | Recovery reports cite persisted artifact IDs. |
| P100 | Expand Flash regression to 4x1 or 6x1 after P96/P97 gates | Public gates remain PASS with larger sample. |
| P101 | Add provider-seam integration test for MemPalace + MemoryService together | No fallback import needed when deps injected. |
| P102 | Harden route receipt reason taxonomy for all selected-only non-actionable capabilities | `unnecessary_selected` remains below threshold. |
| P103 | Add docs index pointer for P75/P95 reports | Future agents can find latest evidence quickly. |
| P104 | Run full focused CI shard across core/infrastructure/security/route tests | No local regression. |
| P105 | Decide whether Pro validation is now worth cost | Only run if Flash + gates stay stable. |
