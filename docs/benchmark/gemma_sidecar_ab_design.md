# Gemma Sidecar A/B 實驗設計

**日期**: 2026-06-16
**目的**: 測試 Gemma 12B 作為 planning/diagnosis sidecar 是否能提升 Qwen 14B patch lane 的表現
**狀態**: 待執行

---

## 實驗設計

### 兩組比較

| 組別 | Planning | Diagnosis | Patch | 預期效果 |
|------|----------|-----------|-------|---------|
| **A (baseline)** | Qwen 7b | Qwen 7b | Qwen 14b | 現有配置 |
| **B (sidecar)** | **Gemma 12B** | **Gemma 12B** | Qwen 14b | 更好的前置品質 → 更高的 patch 成功率 |

### Gemma Sidecar 的角色

Gemma 12B 不直接接 patch authority，只做：
1. **Planning draft**：產生 repair plan（替代 7b 的 planning phase）
2. **Repro diagnosis**：分析 reproduction 失敗原因，判斷是否 env-fixable
3. **Patch proposal**：產生候選 patch（但最終由 Qwen 14b 決定）
4. **Candidate rerank**：多候選時排序
5. **Failure explanation**：結構化失敗分類

### 實驗參數

- **Tasks**: 15-20 題（從 manifest 選取，混合 solved/unsolved/env-fail）
- **每個 task 跑 2 次**（A 組 + B 組），共 30-40 runs
- **Protocol**: 同 S1-S7 的 receipt v1 + fail-closed claim boundary
- **Seed**: 固定 temperature=0.0 確保可重現

### 評估指標

| 指標 | 計算方式 | 重要性 |
|------|---------|--------|
| Claimable solve rate | verification success / total | 最高 |
| Stop-layer alignment | expected == observed / total | 高 |
| Patch failure taxonomy | PATCH_MISMATCH / SEMANTIC_WRONG / SYNTAX_INVALID 分佈 | 高 |
| Token efficiency | total_tokens / solved | 中 |
| Time efficiency | wall_time / solved | 中 |
| Planning accuracy | planning phase success / total | 中（sidecar 專用） |

### 判斷標準

| 結果 | 判斷 |
|------|------|
| B 組 solve rate 明顯 > A 組，且 stop-layer 不退化 | Gemma sidecar 有效，正式掛入 |
| B 組 solve rate ≈ A 組，但 planning 準確度更高 | Gemma sidecar 有潛力，需要更多題目驗證 |
| B 組 solve rate ≤ A 組 | Gemma sidecar 無效，移除或重新定位 |

### 實作步驟

1. 修改 `local_model_policy.py`：新增 `gemma12b_sidecar` 配置
2. 修改 `phases/planning.py`：支援 Gemma 作為 planning model
3. 修改 `phases/reproduction.py`：支援 Gemma 作為 repro diagnosis
4. 跑 A 組（現有配置）× 15 題
5. 跑 B 組（Gemma sidecar）× 同 15 題
6. 比較 receipt v1 結果
