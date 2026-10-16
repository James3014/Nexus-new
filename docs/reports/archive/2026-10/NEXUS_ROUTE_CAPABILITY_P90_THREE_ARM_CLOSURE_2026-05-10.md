# Nexus Route Capability P90 Three-Arm Closure

## Goal

Confirm the new route can invoke the required capabilities through three execution views:

- Codex wearing Nexus deterministic route smoke.
- Gemini 3 Flash wearing Nexus on a live route-oracle benchmark.
- Gemini 3.1 Pro wearing Nexus on the same live route-oracle benchmark.

This report only claims route/capability invocation completeness. It does not claim public model-quality improvement.

## Result

P90 closure gate: PASS.

## Evidence

### Codex Wearing Nexus

- Report: `.nexus/reports/capability_route_smoke_summary.json`
- Result: `passed=true`
- Route quality:
  - `selected_to_invoked=0.9848484848484849`
  - `invoked_to_evidence=1.0`
  - `evidence_to_outcome=1.0`
  - `unnecessary_selected=0.015151515151515152`

### Gemini 3 Flash Wearing Nexus

- With Nexus: `.nexus/reports/p90_flash_route_autoreason/with_nexus_1778425342.jsonl`
- Without Nexus: `.nexus/reports/p90_flash_route_autoreason/without_nexus_1778425342.jsonl`
- Markdown report: `.nexus/reports/p90_flash_route_autoreason/gemini_nexus_report_1778425342.md`
- Result:
  - with Nexus: `SUCCESS`, `solve_rate=1.0`, `semantic_verified_rate=1.0`, `trust_mismatch_rate=0.0`
  - bare: `FAILED`, `solve_rate=0.0`, `semantic_verified_rate=0.0`, `trust_mismatch_rate=0.0`
- Cost note:
  - with Nexus wall time was high at about `242.8s`; this remains a route-cost optimization target.

### Gemini 3.1 Pro Wearing Nexus

- With Nexus: `.nexus/reports/p90_pro_route_autoreason/with_nexus_1778425643.jsonl`
- Without Nexus: `.nexus/reports/p90_pro_route_autoreason/without_nexus_1778425643.jsonl`
- Markdown report: `.nexus/reports/p90_pro_route_autoreason/gemini_nexus_report_1778425643.md`
- Result:
  - with Nexus: `SUCCESS`, `solve_rate=1.0`, `semantic_verified_rate=1.0`, `trust_mismatch_rate=0.0`
  - bare: `FAILED`, `solve_rate=0.0`, `semantic_verified_rate=0.0`, `trust_mismatch_rate=0.0`
- Cost note:
  - with Nexus wall time was about `113.3s`; this is better than Flash but still part of route-cost tuning.

### Three-Arm Capability Matrix

- Matrix: `.nexus/reports/capability_invocation_matrix_p90.json`
- Result: `passed=true`
- Required runtime capabilities checked:
  - `autoreason`
  - `belief`
  - `ddtree`
  - `drone`
  - `lancedb`
  - `nightshift`
  - `research`
  - `semantic_searcher`
  - `swarm`
  - `swarm_quiet_moment`
  - `ultra_review`
- Flash and Pro fresh arms both selected, invoked, produced evidence, contributed outcome, and reached public-safe receipt for `autoreason`.
- Codex smoke covered the wider route registry and confirmed all expected runtime route capabilities have at least one selected/invoked/evidence/outcome/public-safe path.

## Verification Commands

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=240 \
NEXUS_RLM_REPAIR_LOOP=1 \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=180 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_route_oracles_v1.json \
  --task-id-filter route-oracle-autoreason-001 \
  --max-tasks 1 --repeat-trials 1 --difficulty all --repo-kind-filter all \
  --force-flow hyper_sprint \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --timeout-sec 300 --total-timeout-sec 900 --stop-loss-sec 900 --per-task-stop-loss-sec 600 \
  --evidence-bundle --markdown-report auto --progress-log \
  --output-dir .nexus/reports/p90_flash_route_autoreason
```

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3.1-pro-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3.1-pro-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
NEXUS_RLM_REPAIR_LOOP=1 \
NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=240 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_route_oracles_v1.json \
  --task-id-filter route-oracle-autoreason-001 \
  --max-tasks 1 --repeat-trials 1 --difficulty all --repo-kind-filter all \
  --force-flow hyper_sprint \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --timeout-sec 300 --total-timeout-sec 900 --stop-loss-sec 900 --per-task-stop-loss-sec 600 \
  --evidence-bundle --markdown-report auto --progress-log \
  --output-dir .nexus/reports/p90_pro_route_autoreason
```

```bash
uv run python scripts/ops/capability_invocation_matrix.py \
  --arm codex:.nexus/reports/capability_route_smoke_summary.json \
  --arm flash:.nexus/reports/p90_flash_route_autoreason/with_nexus_1778425342.jsonl \
  --arm pro:.nexus/reports/p90_pro_route_autoreason/with_nexus_1778425643.jsonl \
  --output .nexus/reports/capability_invocation_matrix_p90.json

uv run pytest -q \
  tests/ops/test_capability_invocation_matrix.py \
  tests/engine/test_capability_wiring_audit.py \
  tests/engine/test_capability_receipt_policy.py \
  tests/engine/test_capability_routing_contracts.py \
  tests/engine/test_capability_coverage_gap.py
```

Key output: `46 passed`.

```bash
uv run python scripts/ops/nexus_pre_flash_gate.py --quick
uv run python scripts/ops/capability_route_smoke.py --print-only
```

Key output: both `passed=true`.

## Failure Lesson

The Gemini worker queue first failed because the sandbox blocked `uv` from reading `~/.cache/uv/sdists-v9/.git`. This is an environment execution failure, not a Gemini or Nexus route failure. Future queued Gemini worker runs should either run with an approved execution context that can access the UV cache, or set UV cache paths inside the workspace before dispatching tasks.

## Residual Debt

- `swarm`, `drone`, and `nightshift` are still guarded as pending-executor or receipt/shadow-backed for runtime public claims where applicable. They are not missing from route capability evidence, but executor-control hardening remains a separate implementation milestone.
- Route cost remains high for live Flash wearing Nexus. P90 closes invocation completeness, not cost parity.
