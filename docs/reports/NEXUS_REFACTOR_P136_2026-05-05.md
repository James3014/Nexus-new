# NEXUS P136 Brain Hub / Pipeline / Route Refactor Report

Date: 2026-05-05
Branch: main
Scope: P96-P136
Pro validation: skipped by policy; Flash only

## Executive Result

P96-P136 completed the remaining post-P95 refactor plan as three bounded slices:

1. Brain Hub and Hallucination Guard reality gates.
2. Pipeline composition seams, S-stage canonization, append-only journal, healing packet, and Secure Sync authZ.
3. Brain Hub guidance receipts in route rows, route/research smoke, and Flash regression.

The key behavioral outcome is that Brain Hub is no longer only documentation guidance: route benchmark rows now carry a `brain_hub_guidance` receipt, and route smoke summarizes whether Brain Hub guidance was present and audit-passed.

## Completed Phase Map

| Phase range | Status | Evidence |
| --- | --- | --- |
| P96-P97 | PASS | Route smoke now classifies uv/sandbox no-JSONL failures as infra-invalid; route quality gates remain hard gates. |
| P98-P100 | PASS | Hallucination Guard schema is fail-closed, runtime checks cover `logic_mismatch` and `verified_claim_without_evidence`, schema check drift is tested. |
| P101-P103 | PASS | `brain_hub_audit.py` creates HubMap guidance and a production-status reality gate. |
| P104-P110 | PASS | `PhaseExecutor` protocol, canonical `S/P/X/D/R/A/C` stage metadata, and append-only decision journal are in place. |
| P111-P113 | PARTIAL | Domain event bus and LearningSteward were already mostly landed before P96; this slice did not remove every remaining raw-event path. |
| P114-P118 | PASS/PARTIAL | HealingArtifact packet roundtrip and Secure Sync per-client action authZ are landed; full remote execution remains intentionally blocked. |
| P119-P120 | PARTIAL | Tiered forgetting and docs dashboard are represented in the Brain Hub audit/report layer, not yet as destructive-change runtime blocks. |
| P121-P124 | PASS | With-Nexus benchmark rows now include Brain Hub guidance receipt fields. |
| P125-P129 | PASS | Pipeline/route targeted tests, full route smoke, research stack smoke, and Flash 2x1 regression passed. |
| P130-P136 | PASS | P75 remains the public 12x2 evidence; P129 is a small regression. This report closes the phase and defines P137+. |

## Verification Evidence

### Targeted Test Shards

```bash
uv run pytest -q tests/ops/test_capability_route_smoke.py tests/core/test_hallucination_guard.py tests/ops/test_brain_hub_audit.py
```

Result: `28 passed in 0.71s`.

```bash
uv run pytest -q tests/engine/test_pipeline_stage_flow.py tests/engine/test_phase_plugin.py tests/security/test_secure_sync.py tests/core/test_healing_artifacts.py
```

Result: `16 passed in 1.08s`.

```bash
uv run pytest -q tests/ops/test_capability_route_smoke.py tests/benchmark/test_capability_ab_runner.py -k 'extract_record or route_quality or brain_hub or summarize_jsonl_requires'
```

Result: `8 passed, 120 deselected in 0.20s`.

### Brain Hub Audit

```bash
python3 scripts/ops/brain_hub_audit.py --path wiki/arch_diagnosis_brain_hub.md --path wiki/critique_brain_hub_alignment_gap.md --path wiki/critique_brain_hub_layer3_alignment.md --path wiki/NEXUS_EVOLUTION_MANIFESTO_v25.5.md --path wiki/NEXUS_GOVERNANCE_EXECUTION_PROTOCOL.md --path wiki/NEXUS_EVOLUTION_ONTOLOGY.md --path wiki/NEXUS_SWARM_EVOLUTION_PROTOCOL.md
```

Result: `passed=true`.

Guidance phases detected: `S`, `D`, `R`, `A`.

### Capability Route Smoke

```bash
python3 scripts/ops/capability_route_smoke.py
```

Result: `passed=true`.

Summary path: `.nexus/reports/capability_route_smoke_summary.json`.

Latest route oracle JSONL: `.nexus/reports/bench_route_8oracle_smoke/with_nexus_1777984635.jsonl`.

| Suite | Tasks | Selected -> Invoked | Invoked -> Evidence | Evidence -> Outcome | Unnecessary Selected | Brain Hub present | Brain Hub audit passed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| route_oracles | 8 | 100.0% | 102.1% | 97.9% | 0.0% | 8/8 | 8/8 |
| codeintel_hyper | 2 | 95.5% | 100.0% | 100.0% | 4.5% | 2/2 | 2/2 |
| core_governance_gates | 2 | 100.0% | 100.0% | 100.0% | 0.0% | 2/2 | 2/2 |
| belief_gate | 1 | 100.0% | 100.0% | 100.0% | 0.0% | 1/1 | 1/1 |

### Research Stack Route Smoke

```bash
python3 scripts/ops/research_stack_route_smoke.py --jsonl .nexus/reports/bench_route_8oracle_smoke/with_nexus_1777984635.jsonl --require-autoreason-invoked
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
| checkpoints seen | candidate_tournament_receipt, claim_citation_verification, fixed_budget_metric_contract, packet_session_ledger |

### Flash P129 Regression

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin NEXUS_GATEWAY_COMPACT_PROMPT=1 NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 uv run python scripts/bench/capability_ab_runner.py --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json --output-dir .nexus/reports/bench_gemini3flash_value2x1_20260505_p129 --max-tasks 2 --repeat-trials 1 --timeout-sec 420 --total-timeout-sec 1800 --stop-loss-sec 900 --per-task-stop-loss-sec 600 --difficulty all --repo-kind-filter all --force-flow hyper_sprint --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini --force-learn-slo-ready --neutralize-history --disable-learning-loop --materialize-missing --isolation-mode preserve_target --evidence-bundle --markdown-report auto --progress-log
```

Report: `.nexus/reports/bench_gemini3flash_value2x1_20260505_p129/gemini_nexus_report_1777984832.md`.

| Metric | Bare Flash | Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Solve rate | 100.0% | 100.0% | 0.0% |
| Semantic verified | 100.0% | 100.0% | 0.0% |
| Trust mismatch | 0.0% | 0.0% | 0.0% |
| Avg wall time | 15.53s | 41.36s | +25.83s |
| Avg model calls | 1.00 | 1.00 | 0.00 |
| Public claim gate | PASS | PASS | n/a |
| Performance claim gate | PASS | PASS | n/a |
| Wearing claim gate | PASS | PASS | n/a |
| Capability-specific claim gate | PASS | PASS | n/a |
| Cost claim gate | PASS | PASS | n/a |
| Per-capability public gate | PASS | PASS | n/a |
| Brain Hub guidance | n/a | 2/2 | n/a |
| Brain Hub audit passed | n/a | 2/2 | n/a |

Interpretation: P129 is a small regression run. Public headline evidence remains P75 12x2, where Flash + Nexus achieved 24/24 vs bare 14/24 with all public gates PASS.

## Residual Debt

- Full Mixin removal is not complete; P104-P110 created the safe composition seam and S-stage canon first.
- LearningSteward/raw event cleanup remains partial; domain event bus should be expanded in P137-P145.
- Tiered forgetting and Quiet Moment are not yet hard runtime blocks for every destructive or long-latency path.
- Pro validation remains intentionally skipped.
- P129 Flash regression is 2x1; do not use it as the headline public claim.
- Existing unrelated dirty/untracked S2T/wiki/.nexus files remain outside this slice.

## P137-P150 Next Plan

| Phase | Task | Gate |
| --- | --- | --- |
| P137 | Add Brain Hub guidance metrics to Gemini markdown report | Report has a Brain Hub section, not only raw rows. |
| P138 | Make Brain Hub guidance a route-quality hard gate for with_nexus rows | Missing guidance fails route smoke. |
| P139 | Extract PlanPhase executor from legacy mixin | P phase can run via composition-only adapter. |
| P140 | Extract ResearchPhase executor | X phase can be tested without full NexusPipeline inheritance. |
| P141 | Extract Diagnose/Repair executor boundary | D/R loop has explicit input/output contract. |
| P142 | Domain Event Bus expansion | `emit_audit_failure`, `emit_learning_decision`, `emit_evidence_accepted` used by core paths. |
| P143 | Tiered forgetting runtime gate | L3 destructive changes hard-block without approval. |
| P144 | Quiet Moment runtime event | Long sync/migration emits user-visible latency event. |
| P145 | Secure Sync authZ integration smoke | unauthorized remote action denied through socket path. |
| P146 | HealingArtifact report readback | report cites persisted artifact IDs. |
| P147 | Flash 4x1 regression | Public gates stay PASS with larger sample. |
| P148 | Flash 12x2 candidate rerun | Only if P147 stable. |
| P149 | Pro decision gate | Decide if Pro cost is justified. |
| P150 | Final public Chinese report refresh | Summarize ability, governance, and cost-efficiency evidence. |
