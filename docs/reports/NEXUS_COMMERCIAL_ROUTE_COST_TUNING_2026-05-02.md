# 商用 Lane create_goal 路由成本調整（細節）

## 任務
在不犧牲功能能力下，針對 `create_goal` 新路由做 cost-efficiency lane 的第二輪優化，確認是否為路由設計缺陷，並確認是否能成為全域策略而非只對今日題目。

## 數據
1. 目前 `bench_commercial_cost_efficiency_gemini3flash_20260502`（6 題）中，`with_nexus` 全部 `route_recommended_flow` 都是 `hyper_sprint`，且 `route_reason` 全為 `commercial_public_task_prefers_hyper`。
2. 我們重算這 6 題在 2026-05-02 既有輸入（`task_type=public_*`, `candidate_count=3`, `root_cause_confidence=0.55`）時，新的路由建議為：
   - `baseline`：4 題（`simple_bug_prefer_baseline`）
   - `hyper_sprint`：2 題（`complex_bug_prefer_hyper` 1、`commercial_public_task_prefers_hyper` 1）
3. 目前 with/without 原始成績差異仍是：超時 wall 平均 62.42s vs 18.45s。
4. 估算新路由的節流效果（採用 4 baseline + 2 hyper 並保留 baseline 失敗再重試 hyper）：
   - 無法 baseline 的兩題保留原本 hyper 成果，不會直接降解成功率
   - 其餘 4 題轉 baseline 可直接沿用原 6 題中的 baseline 成本（12.48s、12.89s、17.74s、12.50s）
   - 估計總 wall 下降到約 282s（約 47.0s 平均），相對原 374.5s（62.4s 平均）有明顯下降

## 證據
1. 代碼變更：
   - `nexus/app/research_flow_service.py`
     - 新增 ` _classify_commercial_signal()`：分離 `has_commercial_signal` 與 `has_strong_commercial_signal`。
     - 非強勢商用信號不再直接觸發 `hyper_sprint`。
     - 將非強勢 public 任務的 `is_risky_bug` 從 `candidate_count=3 / low_confidence=0.55` 這類預設噪音信號中解除耦合，只有在有硬訊號（hard/commercial strong）時才推高為 hyper。
     - `build_hyper_execution_profile()` 對強勢商用才保留 `commercial_public_task` 強化/`prefer_direct_hyper`。
2. 測試驗證：
   - `tests/app/test_research_flow_service.py`
     - 新增：`test_build_route_treats_public_non_strong_commercial_task_as_baseline`
     - 新增：`test_build_hyper_execution_profile_weak_public_commercial_task_not_hard`
     - 相關既有 public/commercial 測試維持通過
3. 驗證命令：
   - `pytest -q tests/app/test_research_flow_service.py -k "public_commercial or public_non_strong or weak_public_commercial"`
   - `pytest -q tests/app/test_research_flow_service.py -k "public_commercial or public_non_strong or weak_public_commercial"`
   - `pytest -q tests/app/test_research_flow_service.py -k "public_commercial or public_non_strong or weak_public_commercial"`（重跑相同子集確認穩定）
4. 與舊路由比較：
   - `docs/reports/NEXUS_COMMERCIAL_LANES_GEMINI3FLASH_REPORT_2026-05-02.md` 已記錄舊版全部公估結果。
   - `NEXUS_COMMERCIAL_LANES_GEMINI3FLASH_REPORT_2026-05-02.md` 中 cost lane 的 route_reason 仍是商用通用路徑，顯示前版對「是否強勢商用」沒有分級。

## 判斷
這次屬於「路由策略可精煉」而非重設計：不是全域拋棄 Hyper，而是把 `public_*` 的商用訊號分兩級，讓非高風險題先保留 baseline + 失敗後 fallback 的可見收益，既降成本又保留能力。此調整可套用到全域能力，而不是只對今日 6 題手工調參。

## 與已驗證成本 profile 的關係

本調整應與 benchmark runner 層的成本控制合併使用，但兩者的證據邊界不同：

1. **已實跑證明**：`--skip-llm-baseline --llm-candidate-cap 1` 在 cost-efficiency lane 中維持 Nexus 100% verified delivery，並把 avg wall 從 62.42s 降到 36.66s、tokens 從 35,984 降到 28,064。
2. **本報告證明**：商用訊號分級讓 route decision 從「public 一律 hyper」變成「強商用才 hyper、弱商用可 baseline」。這是跨模型適用的 planner 策略。
3. **尚未宣稱**：目前 public benchmark 在 `--skip-llm-baseline` 且未指定 `--force-flow` 時會強制 `hyper_sprint`，以避免 baseline 路徑變成本地無模型修補。因此本次 4 baseline / 2 hyper 是 route recomputation evidence，還不是 public benchmark outcome evidence。

產品化建議：

- 對公開 same-model A/B：先採用已驗證的 `--skip-llm-baseline --llm-candidate-cap 1`，保留 model-wearing 與 public gate。
- 對路由內部優化：保留本次商用訊號分級，避免新路由在弱商用任務上過度升級。
- 下一步若要讓路由分級也直接反映在公開 benchmark 成本上，需新增「Nexus baseline LLM path」，讓 baseline 仍由同一模型穿 Nexus 執行，而不是退回本地非模型修補。

## Route-aware 實跑回查

追加實跑後，route-aware baseline 目前不能升為公開 default：

1. `routeaware_cap1_fixed` 確認修正後確實產生 `baseline 4 / hyper 2`，但 with Nexus 只有 `83.3%`，public claim gate 因 `with_trust_mismatch_above_zero` 失敗。
2. 補上 self-heal/failure-tail hard signal 後，分流變成 `baseline 3 / hyper 3`，但 with Nexus 仍只有 `50.0%`，且 `local_fallback_unhelpful_rate=0.5`。
3. 失敗 row 共同特徵是 `baseline_llm_failed_replan_hyper` + `gateway_error` + `fallback_used=true`，代表 baseline LLM path 目前仍會被 local fallback 污染，不適合公開 claim。

因此目前採用策略是：

- **公開 benchmark default**：`--skip-llm-baseline --llm-candidate-cap 1`。
- **planner 內部保留**：商用訊號分級與 self-heal hard signal。
- **暫不採用**：route-aware baseline 作為公開成本 lane default。
- **後續工程化條件**：新增 strict Nexus LLM baseline，要求 baseline 由同一模型產生有效 patch；LLM failure 不得被 local fallback 洗成成功或混入 public denominator。

診斷 evidence：

- `.nexus/reports/bench_commercial_cost_efficiency_gemini3flash_routeaware_cap1_fixed_20260502/evidence_bundle.json`
- `.nexus/reports/bench_commercial_cost_efficiency_gemini3flash_routeaware_cap1_selfheal_20260502/evidence_bundle.json`
