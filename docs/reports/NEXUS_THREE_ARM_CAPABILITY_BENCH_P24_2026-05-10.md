# Nexus Three-Arm Capability Benchmark P24

## Goal

用三種方式確認新路由在「應該調用能力」時是否真的產生可審核 receipt：

1. Codex-operated Nexus route smoke
2. Gemini 3 Flash wearing Nexus
3. Gemini 3.1 Pro wearing Nexus

## Result

| Arm | Benchmark | Result | Capability Receipt Result |
|---|---|---:|---|
| Codex-operated Nexus | `scripts/ops/capability_route_smoke.py` | PASS | PASS: all route oracle expected capabilities public-safe |
| Direct Codex model wearing Nexus context | `capability_ab_runner.py`, 3 route-oracle tasks | FAIL | FAIL: direct Codex path did not invoke expected executors |
| Gemini 3 Flash wearing Nexus | `route-oracle-autoreason-001` | FAIL | FAIL: `timeout_before_receipt`, no Nexus bootstrap/context/phase receipt |
| Gemini 3.1 Pro wearing Nexus | `route-oracle-autoreason-001` | PASS | PASS: `autoreason` selected/invoked/evidence/gate/outcome/public-safe |

## Evidence

### Codex-operated Nexus

`uv run python scripts/ops/capability_route_smoke.py`

- `passed=true`
- `receipt_diagnostic_pass=true`
- route oracle public-safe:
  - `autoreason`
  - `ddtree`
  - `drone`
  - `lancedb`
  - `nightshift`
  - `research`
  - `swarm`
  - `ultra_review`
- runtime receipt public-safe:
  - `semantic_searcher`
  - `swarm_quiet_moment`

### Direct Codex Model Path

Output:

- `.nexus/reports/p24_codex_nexus_route_oracle/with_nexus_1778384488.jsonl`

Observed:

- `route-oracle-autoreason-001`: missing `autoreason`
- `route-oracle-ddtree-001`: missing `ddtree`
- `route-oracle-ultra-review-001`: missing `ultra_review`

Diagnosis:

Direct Codex path records Nexus context and gates, but does not execute the normal Nexus capability executor path for these route-oracle capabilities. It is not a valid proof path for capability invocation until the Codex provider arm is routed through the same receipt-backed executor seam.

### Gemini 3 Flash

Output:

- `.nexus/reports/p24_flash_nexus_autoreason_1x/with_nexus_1778385331.jsonl`

Observed:

- `status=FAILED`
- `semantic_status=UNVERIFIED`
- `infra_invalid_reason=nexus_delivery_invalid`
- `timeout_stage=timeout_before_receipt`
- `nexus_bootstrap_completed=false`
- `nexus_context_delivered=false`
- `nexus_wearing_valid=false`
- expected `autoreason` missing

Diagnosis:

Flash did not reach a Nexus receipt-producing state under this benchmark contract. This is a runtime/timeout problem, not a successful capability invocation.

### Gemini 3.1 Pro

Output:

- `.nexus/reports/p24_pro_nexus_autoreason_1x/with_nexus_1778385536.jsonl`

Observed:

- `status=SUCCESS`
- `semantic_status=VERIFIED`
- `nexus_wearing_valid=true`
- phases observed: `P`, `X`, `D`, `R`, `A`, `C`
- pillars observed: `lancedb`, `memory`, `mempalace`, `belief`, `artifact`
- expected `autoreason` public-safe
- `autoreason`: selected, invoked, evidence_present, gate_passed, outcome_contributed, public_claim_safe

## Decision

- Capability wiring itself is proven by deterministic route smoke.
- Pro+Nexus proves the true model path can produce the expected `autoreason` receipt.
- Flash+Nexus does not yet prove this under the route-oracle benchmark because it times out before receipt.
- Direct Codex provider path is not equivalent to the normal Nexus executor path and should not be used as capability invocation proof until fixed.

## Required Next Fixes

1. Add a Codex provider path that invokes normal Nexus capability executors, or mark direct Codex route-oracle capability proof unsupported.
2. Add Flash receipt-first timeout protection: emit a failure receipt when bootstrapping times out before capability evidence, instead of leaving the row with empty phases/pillars.
3. Add a two-layer benchmark split:
   - route/receipt benchmark: validates capability invocation without requiring hidden repair success
   - model solve benchmark: validates Flash/Pro can solve while wearing Nexus
