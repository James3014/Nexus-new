# Nexus Hidden Retry Telemetry P34

## Goal

Fix the misleading cost accounting around hidden verifier bounded retry before doing more route-cost tuning. The target is not to remove the retry gate. The target is to make the retry visible as a composed model attempt so the next optimization can attack the real R/hyper wall source without blaming runner overhead.

## Result

- Status: PASS for telemetry correctness.
- Flash+Nexus delivery: 1/1 `SUCCESS` and `VERIFIED`.
- Flash bare delivery: 0/1 `FAILED` and `UNVERIFIED`.
- Public claim gate: `PASS`.
- Public verified delivery claim gate: `PASS`.
- Public cost safety posture: `PASS`.
- Public cost efficiency claim gate: `REGRESSED`.
- Allowed public wording key: `verified_delivery_uplift_with_cost_regression_localized_to_hidden_retry`.
- Remaining bottleneck: retry still costs an additional near-full model attempt; the next structural target is partial/minimal hidden retry, not more runner-overhead cleanup.

## Code Change

- `scripts/bench/capability_ab_runner.py`
  - Hidden verifier bounded retry now preserves first-attempt cost fields.
  - Retry model calls, attempt count, tokens, CLI elapsed, runner overhead, and phase wall are recorded separately.
  - Final row composes first attempt plus hidden retry into `model_calls`, `attempt_count`, `total_tokens`, and `model_attempts`.
  - `runner_overhead_basis` is now `composed_hidden_retry` for this path, avoiding the previous false attribution where retry wall was counted as wrapper overhead.

- `tests/benchmark/test_capability_ab_runner.py`
  - Hidden retry tests now assert composed `model_calls`, `attempt_count`, `total_tokens`, hidden retry token fields, and composed runner-overhead basis.

## Verification

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_failure_retries_with_failure_evidence_when_self_heal_env_enabled \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_failure_retries_inprocess_with_failure_evidence \
  tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_compact_retry_keeps_candidate_cap \
  -q
```

Result: `3 passed in 0.71s`.

```bash
uv run pytest \
  tests/benchmark/test_capability_ab_runner.py \
  tests/research/test_sprint_service.py \
  tests/test_battlesuit_gateway.py \
  tests/services/test_gemini_cli.py \
  -q
```

Result: `261 passed in 17.84s`.

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_CODEX_IGNORE_USER_CONFIG=1 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_model_required_uplift_v1.json \
  --output-dir .nexus/reports/p34_flash_model_required_repair_hidden_retry_telemetry \
  --task-id-filter model-required-repair-001 \
  --max-tasks 1 \
  --timeout-sec 210 \
  --per-task-stop-loss-sec 260 \
  --stop-loss-sec 520 \
  --total-timeout-sec 520 \
  --with-nexus-runner subprocess \
  --with-llm-mode hard \
  --with-model-provider gemini \
  --gemini-model gemini-3-flash-preview \
  --without-mode gemini \
  --force-learn-slo-ready \
  --neutralize-history \
  --materialize-missing \
  --enable-llm-self-heal \
  --evidence-bundle \
  --markdown-report auto
```

Result:

- `with_nexus`: `SUCCESS`, `semantic_status=VERIFIED`.
- `without_nexus`: `FAILED`, `semantic_status=UNVERIFIED`.
- Evidence bundle: `.nexus/reports/p34_flash_model_required_repair_hidden_retry_telemetry/evidence_bundle.json`.
- Markdown report: `.nexus/reports/p34_flash_model_required_repair_hidden_retry_telemetry/gemini_nexus_report_1778618426.md`.

## Key Metrics

| Metric | P34 Value |
|---|---:|
| Flash+Nexus wall | `108.5705s` |
| Flash bare wall | `60.7421s` |
| Wall ratio | `1.7874x` |
| Flash+Nexus tokens | `122850` |
| Flash bare tokens | `64873` |
| Token ratio | `1.8937x` |
| Flash+Nexus model calls | `2` |
| Flash bare model calls | `1` |
| First attempt tokens | `61800` |
| Hidden retry tokens | `61050` |
| Hidden retry wall | `50.2678s` |
| Hidden retry R phase wall | `38.8802s` |
| Hidden retry runner overhead | `0.656s` |
| Total runner overhead | `1.2034s` |
| Retry wall share | `0.463` |
| Retry token share | `0.4969` |
| Cost efficiency sample sufficient | `false` |
| Cost efficiency pair count | `1` |
| Minimum pairs for efficiency claim | `3` |
| Stable retry reason code | `hidden_retry_second_attempt_dominant` |

## Public Claim Posture

P34 is safe for a verified-delivery claim, but not for a cost-efficiency claim.

- Delivery: `PASS`.
- Cost safety: `PASS`.
- Cost efficiency: `REGRESSED`.
- Reason codes: `hidden_retry_second_attempt_dominant`, `hidden_retry_token_share_present`, `hidden_retry_wall_share_present`, `model_calls_not_improved`, `token_cost_not_improved`, `wall_cost_not_improved`.
- Sample sufficiency: `false`; P34 is a one-pair diagnostic run, not a broad efficiency claim.

Allowed wording:

> verified delivery uplift with cost regression localized to hidden retry.

Disallowed wording until the efficiency gate changes to `IMPROVED`:

> Nexus reduced cost.

## Mechanism Diagnosis

The previous row shape made a hidden retry look like one model call with very large runner overhead. P34 proves that was a telemetry artifact.

Current mechanism:

1. First Nexus attempt succeeds visibly but fails hidden verifier.
2. Hidden verifier failure triggers bounded hidden retry.
3. Retry is a second model attempt, not runner overhead.
4. Retry R/hyper phase consumes most retry wall: `38.8802s` of `50.2678s`.
5. Runner overhead is now small: `1.2034s` total.

Therefore the next optimization target is the retry strategy itself:

- avoid near-full second repair where hidden failure points to a narrow assertion;
- preserve claim/delivery/artifact gates;
- keep telemetry split by first attempt, retry model call, retry verifier, and runner overhead.

## Residual Debt

- Token ratio is now honestly higher because retry tokens are counted. This is correct accounting, not a new regression.
- Cost claim gate currently reports `PASS` despite token ratio above the nominal threshold, because delivery lift is present. Future public cost wording should distinguish "verified delivery lift with higher retry cost" from "cost reduction".
- Hidden retry remains expensive. The structural next step is a minimal hidden-retry lane that consumes verifier failure evidence and patches only the narrow failing contract.
