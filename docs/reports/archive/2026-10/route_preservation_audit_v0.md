# 🛡️ Nexus Phase 52.5: Route Preservation Audit Report

本報告對目前 **P48/P52 Qwen real-model lane** 與 **5月 Gemini/Nexus 歷史主線**、**6月 LocalHeal/Surgical 模組**的整合度進行了深度路由 preservation 審計，以確保我們在提升小模型能力的過程中，沒有偏離 Nexus 系統的主路徑。

---

## 1. Executive Verdict
目前 P48/P52 成功建構的 70% 成功率確定性自癒與重試環，本質上是一個高效的**局部 Sandbox 修復工具 (Local Model Armor isolated solve lane)**。它在代碼層面繼承了 `hybrid_route` 決約、`candidate_isolation` 與 `canonical_span` (含 AST/traceback) 等核心防禦。
然而它與 5 月的 Gemini / Cloud-First E2E 主路徑以及 6 月的 LocalHeal modular pipeline (Reproduction, Planning, Localization, PatchSynthesis, Verification) 存在**平行旁路 (Bypass) 現象**。新線尚未被收斂為 `HealOrchestrator` 的執行 backend。
在下一階段，我們應將此能力接回 `HealOrchestrator`，使其成為大一統的 Local Provider Backend，防止分裂為兩套 Nexus。

---

## 2. 5月 Gemini/Nexus Route Preservation Matrix (Route A)

| Capability | Source File / Symbol | Historical Purpose | Current Code Exists | Current Qwen Lane Uses It | Evidence | Verdict | Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `hybrid_route` | [hybrid_route.py](file:///Users/jameschen/Workspace/nexus/nexus/contracts/hybrid_route.py) | 判定 Cloud-First, Local-Only 等路由模式 | Yes | Yes | 呼叫 `hybrid_route_decision` 做 fail-closed 阻斷 | **ACTIVE** | KEEP |
| `cloud_first_local_guard` | [capability_ab_runner.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/capability_ab_runner.py) | Gemini E2E 跑卡與 local guard trace | Yes | No | Qwen lane 無調用 cloud model 流程，故被繞過 | **PRESENT_BUT_BYPASSED** | KEEP |
| `capability_ab_runner` | [capability_ab_runner.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/capability_ab_runner.py) | A/B 基準評估與報表渲染 | Yes | No | Qwen 採用獨立 batch 腳本執行評估 | **PRESENT_BUT_BYPASSED** | RECONNECT |

> [!WARNING]
> **AB Runner 歷史 Bug 披露**：執行 `test_capability_ab_runner.py` 時發生 3 項 FAILED，原因為 `scripts/bench/capability_ab_runner.py` 第 8209 行 `_build_h5_guarded_local_candidate_benchmark_trial` 中引用了未定義的 `replay_allowed`。這說明 5 月的 Gemini E2E runner 目前因歷史代碼變更積壓了 NameError。

---

## 3. 6月 LocalHeal Optimization Preservation Matrix (Route B)

| Capability | Source File / Symbol | Historical Purpose | Current Code Exists | Current Qwen Lane Uses It | Evidence | Verdict | Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HealOrchestrator` | [orchestrator.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/orchestrator.py) | 驅動五階段 Linear pipeline 流程 | Yes | No | Qwen lane 直接跳過線性階段調用 isolated solve | **PRESENT_BUT_BYPASSED** | WRAP_AS_BACKEND |
| `SelfCorrector` | [corrector.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/corrector.py) | 執行類型化 retry（如 syntax error） | Yes | No | 使用專用的簡化 feedback builder 進行 retry | **PRESENT_BUT_BYPASSED** | WRAP_AS_BACKEND |
| `env_denoiser` | [env_denoiser.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/env_denoiser.py) | 淨化並隔離環境雜音 | Yes | No | 當前採用 mock dict 進行 test pollution 隔離 | **PRESENT_BUT_BYPASSED** | KEEP |

---

## 4. 6月 Surgical / AST Rewriter Matrix (Route C)

| Capability | Source File / Symbol | Historical Purpose | Current Code Exists | Current Qwen Lane Uses It | Evidence | Verdict | Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GranularMethodLocalizer` | [granular_localizer.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/granular_localizer.py) | 利用 AST 與 BM25 進行 symbols 定位與行號切片 | Yes | No | Qwen lane 目前採用 mock 傳入 controls["locked_search"] | **PRESENT_BUT_BYPASSED** | RECONNECT |
| `get_canonical_search_span` | [canonical_span.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/canonical_span.py) | 從源碼定位 canonical span 範圍 | Yes | Yes | 透過 `local_model_source_anchor.py` 調用以防範越界 | **ACTIVE** | KEEP |

---

## 5. Current Qwen Armor Lane Integration Matrix (Route D)

| Capability | Source File / Symbol | Historical Purpose | Current Code Exists | Current Qwen Lane Uses It | Evidence | Verdict | Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `diff_repair` | [diff_repair.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/diff_repair.py) | 確定性修復畸形或無縮排 patch | Yes | Yes | 將 Qwen micro-batch 成功率拉升至 70% | **ACTIVE** | KEEP |
| `failure_feedback_builder` | [failure_feedback_builder.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/failure_feedback_builder.py) | 組裝 minimal verifier logs 進行 retry | Yes | Yes | 成功引導 3 題進行第二輪嘗試並安全記錄 | **ACTIVE** | KEEP |

---

## 6. Bypassed Capabilities (缺口分析)
1. **五階段 Orchestration**：Qwen lane 繞過了 Reproduction, Planning, Localization 等上游模組，直接對 mock 的 spans 進行 edit。
2. **Surgical Localization**：未整合 `GranularMethodLocalizer`，導致目前仍處於 controls 固定配置的 10 題微型 fixtures，無法對大規模 repo 進行自動切片。
3. **AB Runner 整合**：無法在 `capability_ab_runner` 中一併評估小模型的 A/B 指標。

---

## 7. Must-Reconnect List (優先重接清單)
1. **接入 HealOrchestrator Backend**：將 Qwen 的 `isolated_local_solve_loop` 重構為 `LocalPatchSynthesisBackend`，並註冊進入 `HealOrchestrator` 的 PatchSynthesis/Verification 節點。
2. **修復 AB Runner 的 NameError**：修正 `capability_ab_runner.py` 第 8209 行的未定義變數 bug，使 Gemini 與 Qwen 能在同一個 benchmark 基建中執行。
3. **連通 Granular Method Localizer**：在 `CapabilityAdapter` 中，若 input problem 無 locked_search，自動調用 `GranularMethodLocalizer` 對目標 symbol 進行 AST 分析與 context 抽取。

---

## 8. Recommended Next Phase (建議下一階段)
### Phase 56: MSA (Multi-System Alignment) Unified Backend Integration
- 將 `diff_repair` 與 `failure_feedback_builder` 抽象為通用 backend 模組。
- 修復 `capability_ab_runner.py` 歷史變數錯誤。
- 將本輪 Qwen 的 isolated solve lane 收斂回 `HealOrchestrator` 線性流水線中，實現 Nexus 系統的一體化。
