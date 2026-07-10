# N30R-A2 V2 Four-Task Paired Bare/Core Evaluation Harness

## 1. 任务目的

建立 V2 配对评估工具，确保 Bare model 与 Nexus Full Armor 的公平比较。

## 2. Worktree and Baseline

| Field | Value |
|-------|-------|
| path | `/Users/jameschen/Workspace/nexus-n30r-v1-acceptance` |
| branch | `feat/n30r-v1-independent-acceptance` |
| baseline | `4b3109dde` |
| new worktree created | false (continuing A1 worktree) |
| Agent B worktree accessed | false |
| production files modified | false |

## 3. 四题清单

| Task ID | Source | Seed | Execution Order |
|---------|--------|------|-----------------|
| n30r_smoke_syntax | syntax_task.py | 4201 | Bare → Core |
| n30r_smoke_anchor | anchor_task.py | 4202 | Core → Bare |
| n30r_smoke_semantic | semantic_task.py | 4203 | Bare → Core |
| n30r_smoke_multi | multi_assert_task.py | 4204 | Core → Bare |

All task hashes and source fixture hashes computed from actual files.

## 4. Bare/Core Arm 定义

| Property | Bare (N30R_A_7B_BARE) | Core (N30R_B_7B_REAL_CORE) |
|----------|----------------------|---------------------------|
| model | qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct |
| provider | ollama | ollama |
| nexus_enabled | false | true |
| core_armor_enabled | false | true |
| max_model_calls | 1 | 2 |
| semantic_retry_allowed | false | true |
| max_semantic_retries | 0 | 1 |
| prompt_type | simple_repair | assertion_grounded_with_armor |
| oracle requirement | NOT_APPLICABLE | FULL_ARMOR_PATH_ACCEPTED |

## 5. 公平性契约

Same conditions enforced:
- Same model family, name, tag
- Same task statement, source fixture, verifier command
- Same timeout policy, trial count, seed policy
- Same provider endpoint, temperature/top_p

Documented differences:
- Bare: 1 primary model call, no retry
- Core: 1 primary model call + max 1 semantic retry (Armor cost)

## 6. AB/BA 交错顺序

```
syntax:   Bare → Core
anchor:   Core → Bare
semantic: Bare → Core
multi:    Core → Bare
```

Reduces execution order and warm-cache bias.

## 7. Seed Policy

```
base_seed = 4200
syntax    = 4201
anchor    = 4202
semantic  = 4203
multi     = 4204
```

Same seed per task for both arms.

## 8. Pair Validity

A task enters paired comparison only when:
- Both arms present with matching task identity
- Source fixture hash match
- Verifier contract hash match
- Model/provider actual match
- contract_valid=true, execution_completed=true
- Core oracle accepted (FULL_ARMOR_PATH_ACCEPTED for live)

## 9. Core Oracle Dependency

Core results only enter comparison when A1 oracle accepts:
- FULL_ARMOR_PATH_ACCEPTED → can enter live comparison
- DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING → dry-run only
- REJECTED_* → row = CONTRACT_INVALID, excluded from uplift

## 10. Invalid Row Policy

Invalid rows:
- Cannot become 0 score
- Cannot count in denominator
- Must count in invalid count
- Infra failure ≠ model failure

## 11. Metrics

Computed metrics:
- solve_delta, model_call_delta, wall_time_delta
- paired outcome matrix (both/bare_only/core_only/neither)
- failure family distribution
- response/parse/candidate/apply/verifier rates

## 12. Effectiveness Decision

| Status | Condition |
|--------|-----------|
| V2_NOT_RUN | No live results |
| V2_INVALID | valid_pairs < 4 or oracle rejected |
| V2_VALID_NO_UPLIFT | 4 valid pairs, delta = 0 |
| V2_DIRECTIONAL_UPLIFT | 4 valid pairs, delta > 0 |
| V2_DIRECTIONAL_REGRESSION | 4 valid pairs, delta < 0 |

Forbidden: "statistically significant", "proven improvement", "production ready"

## 13. Dry-run Result

```bash
python scripts/bench/n30r_v2_paired_eval.py \
    --manifest docs/bench/n30r/v2_four_task_paired_manifest.json \
    --plan-only
```

Result: 4 tasks, 8 scheduled rows, AB/BA alternating, 0 provider calls.

## 14. Tests

30+ behavioral tests covering:
- Manifest: 4 tasks, hashes, seeds, alternating order
- Plan mode: no provider calls, 8 rows
- Row rejections: missing arm, wrong model, hash mismatch, oracle rejection
- Terminal status: solve rules, verifier rules, timeout inference
- Metrics: paired matrix, deltas, failure families
- Effectiveness: no-uplift, uplift, regression classification

## 15. Merge Instructions

```bash
git add \
    scripts/bench/n30r_v2_paired_eval.py \
    tests/bench/test_n30r_v2_paired_eval.py \
    docs/bench/n30r/v2_four_task_paired_manifest.json \
    docs/bench/n30r/v2_paired_acceptance_policy.json \
    docs/reports/n30r_a2_v2_paired_eval_harness.md
git commit -m "bench: add N30R V2 paired bare-core evaluation harness"
```

## 16. Claim Boundary

| Claim | Value |
|-------|-------|
| V2 live executed | false |
| effectiveness measured | false |
| production_ready | false |
| public_claim_allowed | false |
| engineering_pilot_only | true |
| no_statistical_significance_claim | true |
