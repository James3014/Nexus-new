# Nexus Public Value Comparison

日期：2026-05-01

## What

本報告彙整三個模型的「同模型 bare vs 同模型 wearing Nexus」比較：

1. `gemini-3-flash-preview`
2. `gemini-3.1-pro-preview`
3. `gpt-5.5`

Nexus 在這裡是戰甲，不是獨立 agent。所有 headline 都必須遵守同模型、同任務、同 verifier、同 eligibility 的比較原則。

## 三模型主證據

| Model | Evidence scope | Gate status | Bare verified | Nexus verified | Lift | Trust mismatch | Claim status |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 12 題 x 1 trial, v2 bundle | PASS | 8/12, 66.7% | 12/12, 100.0% | +33.3pp | 0.0% | public candidate |
| Gemini 3.1 Pro | 12 題 x 2 trials, v1 historical bundle | historical | 5/24, 20.83% | 24/24, 100.0% | +79.17pp | 0.0% | historical candidate |
| GPT-5.5 | 8 題 x 2 trials, v2 bundle | performance PASS, capability FAIL | 8/16, 50.0% | 16/16, 100.0% | +50.0pp | n/a | performance candidate only |

## Repeat / Observation Evidence

| Model | Evidence scope | Gate status | Bare eligible verified | Nexus eligible verified | Lift | Why not headline |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 12 題 x 2 trials, v2 bundle | FAIL | 14/23, 60.9% | 24/24, 100.0% | +39.1pp | 1 bare `timeout_before_model_call` |
| GPT-5.5 | 12 題 x 2 trials, v2 bundle | markdown FAIL | 13/23, 56.52% | 22/24, 91.67% | +35.15pp | 1 bare `auth_failed`; Nexus claim/wearing thresholds below 100% |

## Why

跨三模型共同訊號很一致：

1. Nexus 的主要價值是 verified delivery，而不是速度。
2. Nexus 最常補足的是自癒修復、上下文/記憶、Claim/Delivery Gate、Artifact evidence。
3. Nexus 會增加 orchestration wall time。
4. Token 成本不一定單向增加；GPT-5.5 8x2 主候選中 Nexus tokens 較低，但 wall time 較高。
5. Report Trust 必須 fail-closed；有 infra invalid 的 repeat run 只能作 observation。

## 三條產品化指標

### 1. 能力提升

| Model | Main lift |
| :--- | ---: |
| Gemini 3 Flash | +33.3pp |
| Gemini 3.1 Pro | +79.17pp historical |
| GPT-5.5 | +50.0pp |

### 2. 治理與可交付

| Model | Evidence |
| :--- | :--- |
| Gemini 3 Flash | v2 public gate PASS, route decision 100%, Nexus wearing 100% |
| Gemini 3.1 Pro | historical rows 24/24 wearing evidence, v1 bundle limitation |
| GPT-5.5 | v2 performance public gate PASS on 8x2, but capability-specific gate FAIL; 12x2 observation has infra invalid and markdown gate FAIL |

### 3. 成本效率

| Model | Wall time | Model calls | Tokens |
| :--- | :--- | :--- | :--- |
| Gemini 3 Flash 12x1 | 32.57s -> 49.16s | 1.00 -> 1.08 | 27,432 -> 30,813 |
| Gemini 3.1 Pro historical 12x2 | 17.98s -> 48.49s | 1.00 -> 1.79 | 21,162 -> 39,663 |
| GPT-5.5 8x2 | 9.28s -> 65.50s | 1.00 -> 1.00 | 12,699 -> 8,540 |

## Capability Claim Matrix

| Capability area | Public-safe evidence today | Boundary |
| :--- | :--- | :--- |
| Hyper / repair | Flash and GPT show repair wins; Pro historical supports it | claim per benchmark scope only |
| CodeIntel / Memory | Flash repeat shows context/docs wins | not yet broad docs sync claim |
| MemPalace / Claim / Delivery Gate | Flash 12x1 and Pro historical show governance/trust gains | must keep evidence bundle links |
| Autoreason / Ultra Review | reported public-safe in Flash runner report | claim only when receipt-backed |
| DDTree / repair_loop | often selected-only | do not claim outcome contribution yet |
| Swarm / Drone / Nightshift | not consistently triggered in these headline runs | do not claim value from these reports |

## Public Claim Boundary

可公開候選說法：

> 在固定 hidden-verifier benchmarks 上，Nexus 作為同模型的治理與證據戰甲，將 verified delivery 在 Gemini 3 Flash 從 66.7% 提升到 100.0%。GPT-5.5 的 8x2 performance candidate 從 50.0% 提升到 100.0%，但 capability-specific gate 尚未通過。Gemini 3.1 Pro historical run 也顯示 20.83% 到 100.0% 的提升，但該輪 evidence bundle 是 v1 historical evidence，需與新版 v2 hardened gate 分開標註。

不可說：

- 不可說 Nexus 對所有模型、所有任務都必然 100%。
- 不可說 Nexus 更快；目前主要 run 都顯示 wall time 上升。
- 不可把 Pro historical v1 和 Flash v2 hardened gate 當作完全同級證據。
- 不可用這三份報告宣稱 Swarm / Drone / Nightshift 帶來提升。
- 不可把有 infra invalid 的 12x2 observation 包裝成 public PASS。

## Evidence Index

- Flash report：`docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md`
- Pro report：`docs/reports/GEMINI31PRO_NEXUS_VALUE_REPORT_2026-05-01.md`
- GPT-5.5 report：`docs/reports/GPT55_NEXUS_VALUE_REPORT_2026-05-01.md`
- Flash v2 evidence：`.nexus/reports/bench_gemini3flash_value12x1_20260501_route_gate_public/evidence_bundle.json`
- Pro historical evidence：`.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/evidence_bundle.json`
- GPT-5.5 v2 evidence：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12/evidence_bundle.json`

## Next

1. Re-run Flash 12x2 with zero infra invalid to upgrade repeat observation into public candidate.
2. Create sanitized/public Pro benchmark prompts so 3.1 Pro can be rerun under current external disclosure policy.
3. Re-run GPT-5.5 12x2 with zero infra invalid and current hardened markdown/evidence consistency.
4. Add a small public report generator so these tables are generated from evidence bundles, not hand-maintained.

## Tooling Added

- Report generator：`scripts/bench/nexus_value_comparison_report.py`
- Sanitized manifest generator：`scripts/bench/sanitize_public_benchmark.py`
- Sanitized manifest artifact：`.nexus/reports/sanitized_public_benchmark_nexus_value_v1.json`

Sanitized reruns should use the sanitized manifest as the reviewable disclosure artifact. It removes local file scope fields such as `allowed_files` and `forbidden_files`, preserves fixture/task contract metadata, and marks the manifest as `nexus_public_benchmark_sanitized_manifest_v1`.
