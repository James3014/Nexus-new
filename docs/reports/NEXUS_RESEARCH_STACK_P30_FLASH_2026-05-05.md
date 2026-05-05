# Nexus Research Stack P30 + Flash Report

## Task
Complete the research integration plan through P30, skipping Pro validation, and prove the new route can select, invoke, evidence, gate, and audit the integrated research stack.

## Integrated Source Projects

| Source project | Nexus contract checkpoint | Route evidence |
| --- | --- | --- |
| `/Users/jameschen/Workspace/test/autoresearch` | `fixed_budget_metric_contract` | Research stack contract + research receipt |
| `/Users/jameschen/Workspace/test/codex-autoresearch` | `packet_session_ledger` | `research_preflight` + `research_session` ledger fields |
| `/Users/jameschen/Workspace/test/AutoResearchClaw` | `claim_citation_verification` | claim uncertainty + research gate evidence |
| `/Users/jameschen/Workspace/test/autoreason` | `candidate_tournament_receipt` | `autoreason` public-safe receipt with Borda winner/votes |

## Implementation Summary

- Added a Nexus research stack SSOT contract: `nexus/research/research_stack_contract.py`.
- Added route runtime evidence for `research_preflight`, `research_session`, four source projects, and required checkpoints.
- Fixed Autoreason receipt closure so `status=SUCCESS` is treated as invoked/evidenced/gated when the winner and claim verification exist.
- Added `research_stack_route_smoke.py` to block missing source-project/checkpoint evidence.
- Hardened `capability_route_smoke.py` direct CLI execution and switched benchmark spawning to `uv run python` so the smoke uses the project runtime.
- Filtered internal route markers out of activation details while preserving public/actionable capability rows.

## Verification Data

### Capability Route Smoke

Command:

```bash
python3 scripts/ops/capability_route_smoke.py
```

Result: `passed=true`.

Key output:

| Suite | Tasks | Public-safe capabilities | Route quality |
| --- | ---: | --- | --- |
| route_oracles | 8 | autoreason, ddtree, drone, lancedb, nightshift, research, swarm, ultra_review | selected->invoked 100.0%, invoked->evidence 102.1%, evidence->outcome 97.9%, unnecessary 0.0% |
| codeintel_hyper | 2 | codeintel, delivery_gate, hyper, memory | all route quality gates 100.0%, unnecessary 0.0% |
| core_governance_gates | 2 | artifact_gate, claim_gate, mempalace_gate | all route quality gates 100.0%, unnecessary 0.0% |
| belief_gate | 1 | belief | all route quality gates 100.0%, unnecessary 0.0% |

### Flash 12x2 Public Candidate

Command:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench_gemini3flash_value12x2_20260505_p30 \
  --max-tasks 12 --repeat-trials 2 --timeout-sec 420 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

Result:

| Metric | Bare Flash | Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Usable rows | 24/24 | 24/24 | n/a |
| Infra invalid rows | 0 | 0 | n/a |
| Solve rate | 58.3% | 100.0% | +41.7pp |
| Semantic verified | 58.3% | 100.0% | +41.7pp |
| Trust mismatch | 0.0% | 0.0% | 0.0pp |
| Token measured rate | 100.0% | 100.0% | 0.0pp |
| Model calls avg | 1.00 | 1.00 | 0.00 |
| Avg wall time | 30.34s | 70.70s | +40.36s |

Route/research evidence on Flash + Nexus JSONL:

| Evidence | Count |
| --- | ---: |
| research preflight present | 24/24 |
| research session logged | 24/24 |
| autoreason selected | 24/24 |
| autoreason public-safe | 24/24 |
| research stack source rows | 24/24 |
| required checkpoints seen | 4/4 |

Research-stack smoke on Flash JSONL:

```bash
python3 scripts/ops/research_stack_route_smoke.py \
  --jsonl .nexus/reports/bench_gemini3flash_value12x2_20260505_p30/with_nexus_1777962644.jsonl \
  --require-autoreason-invoked
```

Result: `passed=true`; `autoreason_invoked=24`, `research_public_safe=24`, `selected_to_invoked_rate=1.0`, `unnecessary_selected_rate=0.0`.

## Evidence Paths

- Flash markdown: `.nexus/reports/bench_gemini3flash_value12x2_20260505_p30/gemini_nexus_report_1777962644.md`
- Flash with Nexus: `.nexus/reports/bench_gemini3flash_value12x2_20260505_p30/with_nexus_1777962644.jsonl`
- Flash without Nexus: `.nexus/reports/bench_gemini3flash_value12x2_20260505_p30/without_nexus_1777962644.jsonl`
- Flash evidence bundle: `.nexus/reports/bench_gemini3flash_value12x2_20260505_p30/evidence_bundle.json`
- Route smoke summary: `.nexus/reports/capability_route_smoke_summary.json`

## Failure Lessons

| Failure | Lesson | Writeback location |
| --- | --- | --- |
| `research_preflight.requires_evidence` test expected true for a normal bug task | Distinguish `requires_evidence` from `blocked`; claim uncertainty should require evidence but not falsely mark successful rows as blocked. | This report |
| Direct CLI `python3 scripts/ops/*` could not import repo packages | Ops scripts must bootstrap repo root into `sys.path` when intended to run by path. | This report |
| `capability_route_smoke` used bare `sys.executable` for benchmark runner | Route smoke must run benchmark through `uv run python` to preserve project runtime parity. | This report |
| Sandbox blocked `uv` cache under user home | Full benchmark/smoke jobs that need `uv` cache or model CLI access require escalated execution; non-escalated smoke should be limited to print-only/unit tests. | This report |

## Deferred

- Pro validation intentionally skipped per instruction.
- Ultra Review remains selected-only in Flash rows when dry gate is feature-disabled; it is ignored for public gate/route-quality purposes but remains visible as selected-only capability detail.
