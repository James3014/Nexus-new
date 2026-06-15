# [NEXUS v26 ACTIVE] Preflight Before Local Collaboration Roadmap v2

**Status**: In Progress
**Date**: 2026-06-15
**Commit**: `79fb4ad1`

---

## 任務目標

在不破壞 fail-closed 治理與 authority 邊界的前提下，完成 Local Collaboration Roadmap v2 的前置收斂。

本輪**禁止**直接推進 3B gatekeeper proxy、7B/14B deliberation lane、limited assisted adoption 到主路徑；本輪只允許完成：
1. shadow evaluation 與 adoption-gate 前置證據補齊；
2. Rust / policy drill / telemetry 基礎硬化；
3. feature-flag / fallback / evidence contract 的掛載準備。

---

## A. Shadow Evaluation Evidence

| # | 任務 | 狀態 |
|:--|:-----|:----:|
| A1 | 修正 eval harness，四組使用同一 authority/success criterion/evidence contract | ✅ |
| A2 | 重新執行 30+ eligible shadow rows (easy/medium/hard + held-out) | ⏳ |
| A3 | 產出正式 shadow report (selector override, trust mismatch, cost per task) | ⏳ |
| A4 | student-induced trust mismatch → 立即停止 adoption 敘事 | ✅ (guard in place) |

## B. Rust Deterministic Kernel Evidence

| # | 任務 | 狀態 |
|:--|:-----|:----:|
| B5 | receipt_verifier Rust unit + IPC tests | ⏳ |
| B6 | flow_machine transition matrix fixture + dual-run | ⏳ |
| B7 | No sealed without unit + IPC + dual-run + rollback drill | ⏳ |

## C. Policy / Rollback / Manifest

| # | 任務 | 狀態 |
|:--|:-----|:----:|
| C8 | Policy-baseline-manifest: classification, commit, schema, test entrypoint, rollback drill | ⏳ |
| C9 | Rollback drills for incomplete policy families | ⏳ |
| C10 | Manifest coverage check: test_entrypoints, lane counts, hard lane drills | ⏳ |

## D. Telemetry & Feature-Flag Contract

| # | 任務 | 狀態 |
|:--|:-----|:----:|
| D11 | Runtime telemetry contract (observation-only, no authority change) | ⏳ |
| D12 | Feature-flag contract: flag ON = shadow/assisted observation only | ⏳ |
| D13 | Per-row evidence fields: selected/injected/used/outcome/route_path_id/report_path_id | ⏳ |

## E. Serving Maturity Gate Draft

| # | 任務 | 狀態 |
|:--|:-----|:----:|
| E14 | ExperimentalArchitectureGate + ServingMaturityChecklist (shadow-only) | ⏳ |
| E15 | Checklist: cold start, stability, token budget, fallback, fault isolation, role contract, rollback, human gate | ⏳ |

---

## 測試要求

- `cargo test` — changed Rust modules unit test count > 0
- `uv run pytest -q tests/integration/test_rust_kernel_smoke.py`
- `uv run pytest -q tests/integration/test_rust_wave3_cutover.py`
- 現有 S2T selector/contracts tests, gate tests, manifest coverage check, shadow report tests
- Shadow evaluation tests must verify: same path, same success criterion, same evidence contract

---

## 驗收標準

- Shadow evaluation 可比較，不再被 harness divergence 汙染
- 3B 仍維持 gated S2T selector/reranker advisor 定位
- trust_mismatch_rate 不上升，public_claim_precision 不下降
- Rust receipt_verifier + flow_machine 有 unit + IPC + dual-run 證據
- Policy-baseline-manifest 補齊
- Feature flags 只做觀測/shadow 掛載，不改 authority path
- **API 表面積穩定性**：嚴禁修改 `s2t_shadow_eval.py` 中的 `run_shadow_eval` 函式簽名。新增功能（例如傳遞放棄評估資料集路徑）必須走 `NEXUS_ABSTAIN_DATASET_PATH` 環境變數注入管道以相容 Parity 審計。


---

## 完成後才允許

- 3B gatekeeper proxy shadow 掛載
- 7B/14B local deliberation lane shadow-only 原型
- ExperimentalArchitectureGate 實際接線
- 低風險 assisted adoption 門檻設計
