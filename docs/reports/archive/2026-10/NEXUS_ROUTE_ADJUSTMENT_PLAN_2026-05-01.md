# Nexus New Route Optimization Plan (2026-05-01)

## 目的
回答近期討論：`create_goal` 新路由是否應該只為當日題目調參，還是保留整體能力。結論如下：

- 不應只針對今天題目優化。
- 這些調整必須落在可重複驗證的全域能力路由策略，而非單次任務過擬合。

## 觀察摘要

1. 今日 public 報告中出現的成本上升，不完全來自路由決策本身，而是測試配置（例如 `--force-flow hyper_sprint`）放大了高成本路徑。
2. `research_flow_service.py` 的 `build_route()` 已具備 baseline/hyper 分流邏輯：
   - 會根據 `is_doc_fix`、`has_hard_signal`、`has_commercial_signal`、候選信心度等訊號做分流。
   - 在非強制流程時，存在 baseline 選擇（如 smoke report 有 `simple_bug_prefer_baseline` 的案例）。
3. 因此目前的路由不是「壞設計」，而是**配置 + 佈署策略**（是否強制走 hyper）使成本上升。

## 風險：只針對今日題目微調

- 高風險：只用今日 sample 做 threshold 調整會導致對當日 distribution 過擬合。
- 影響：改善這些題目但可能退化其他 domain（doc fix、非商用、easy/long-tail、非 baseline-friendly cases）。
- 這樣不符合「保持能力強度」的目標。

## 全域優化原則

1. 先把 `--force-flow hyper_sprint` 從 public bench 的比較路徑移除，回到 auto-routing。
2. 保持 `with_llm_mode=all` + `candidate/round/parallel` metadata，不丟失能力證據。
3. 使用分層評估：
   - 目標函數同時看：solve rate、report validity、trust mismatch、wall time、cost proxy。
   - 不只看單一場景。加入難度/任務類型分層。
4. 僅在證據明確時調整路由閾值，不直接硬切策略。

## 建議調整順序（逐步）

### A. 立刻改
- Benchmark 指令：移除 `--force-flow hyper_sprint`。
- 保留 baseline/hyper fallback 行為，避免 baseline 反向壓力測試被屏蔽。
- 對 commercial/public 的 `route_reason` 檢查保持，但不直接把其當作全域優先規則。

### B. 可控參數微調（不動主策略）
- 以 tuning 檔方式微調：
  - `baseline_fast_sec`
  - candidate/round/parallel 上限
  - hard/risk/commercial 信號門檻
- 每次只改一個參數，跑對照，降低混雜效應。

### C. 回歸與門檻
- 以多集合 A/B 跑完才上線：
  - public value（原始分佈）
  - doc-fix/safety/trust subset
  - 低/中/高難度子集
  - 不同 base LLM 類型
- 規則：
  - 能力不得退化（solve rate/gate pass 在統計上不可下降）。
  - 成本/時間若下降為主，需顯著且穩定。

## 預期判斷結果

- 若是配置問題主因：取消強制 hyper 後，baseline 路徑會回到可觀比例，成本明顯下降且能力維持。
- 若是路由門檻問題：在固定多場景回測下可透過微調閾值取得更平衡，不需要改路由主體。

## 結論

這次不是「路由設計全壞」，而是「路由策略與實驗設定混在一起」。

建議先做配置還原 + 分層 A/B + 單參數微調；確保每次變更都能用跨場景指標證明是**全域收益**而非單日題目優化。
