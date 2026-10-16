# NEXUS_SUPERVISED_BARE_FIRST_P52_2026-05-13

## Goal

Reduce Flash+Nexus hidden-lite first-call overhead without removing Nexus verification, claim, delivery, or trust gates.

## Change

- Hidden-lite compact routes now use supervised bare-first by default.
- First model call uses the same bare-equivalent prompt shape as the without-Nexus arm.
- Nexus stays active as ghost governance: preflight, route policy, hidden verifier, evidence fields, and delivery accounting remain active.
- If the supervised bare attempt fails, Nexus attempts bounded deterministic pre-rescue before invoking a second model or `run_hyper_sprint`.
- Prompt parity telemetry is recorded through `gateway_prompt_chars`, `gateway_payload_chars`, `gateway_total_chars`, `nexus_first_call_prompt_mode`, and `prompt_purity_index`.

## Evidence

### Unit / integration

- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q`
  - `198 passed`
- `TMPDIR=/private/tmp TEMP=/private/tmp TMP=/private/tmp uv run pytest tests/benchmark/test_capability_ab_runner.py tests/research/test_sprint_service.py tests/test_battlesuit_gateway.py tests/services/test_gemini_cli.py -q`
  - `267 passed`

### Flash A/B

Report directory:

- `.nexus/reports/p52_flash_model_required_repair_supervised_bare_first_3pair/`

Runner:

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --task-id-filter model-required-repair-001 \
  --output-dir .nexus/reports/p52_flash_model_required_repair_supervised_bare_first_3pair \
  --with-nexus-runner subprocess \
  --with-llm-mode all \
  --with-model-provider gemini \
  --without-mode gemini \
  --gemini-model gemini-3-flash-preview \
  --repeat-trials 3 \
  --timeout-sec 180 \
  --total-timeout-sec 720 \
  --stop-loss-sec 720 \
  --per-task-stop-loss-sec 240 \
  --neutralize-history \
  --evidence-bundle \
  --markdown-report auto
```

Key results:

- Nexus verified delivery: `3/3`
- Bare verified delivery: `0/3`
- Trust mismatch: `0`
- Nexus average wall: `49.1201s`
- Bare average wall: `54.2139s`
- Median paired wall ratio: `0.7958`
- Nexus average tokens: `61549.6667`
- Bare average tokens: `63155.6667`
- Median paired token ratio: `0.9670`
- Model calls: `1.0` vs `1.0`
- Hidden retry wall/token share: `0.0`
- Hyper sprint wall: `0.0`
- Public verified delivery gate: `PASS`
- Cost efficiency gate: `IMPROVED`

## Diagnosis

P51 proved the remaining regression was not `run_hyper_sprint`, hidden retry, or runner overhead. The remaining cost came from Nexus first-call prompt overhead. P52 fixes the seam by moving hidden-lite to ghost governance: keep Nexus as a verifier/governor, but make the first model prompt bare-equivalent.

## Residual Debt

- The public claim gate still fails for unrelated public-report hygiene: Brain Hub guidance and route-quality public-safe capability rows.
- This is a 1-task x 3-trial Flash slice, not a broad public benchmark.
- Next validation should expand to multiple hidden-lite tasks before changing public wording beyond this evidence scope.
