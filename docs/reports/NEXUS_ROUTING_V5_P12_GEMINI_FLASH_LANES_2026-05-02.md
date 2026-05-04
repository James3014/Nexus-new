# Nexus Routing v5 P12 — Gemini 3 Flash 同模型三條 Lane 報告（2026-05-02）

## 範圍
- 模型：`gemini-3-flash-preview`
- 比較：`without_nexus=gemini` vs `with_nexus(subprocess + full capability stack)`
- 固定條件：hidden verifier 開啟、同 task manifest、同輪次（6 tasks/lane）

---

## 結果總覽

### 1) capability_lift_r2
- 路徑：`.nexus/reports/bench_flash_v5_p12/capability_lift_r2`
- Public claim gate：`FAIL`
- 失敗原因：`with_trust_mismatch_above_zero`

數據（eligible only）：
- with_nexus：solve `0.5000`、semantic `0.5000`、trust_mismatch `0.5000`、avg_wall `78.1734s`、avg_tokens `30575.3333`、avg_model_calls `1.1667`
- without_nexus：solve `0.3333`、semantic `0.3333`、trust_mismatch `0.0000`、avg_wall `26.2408s`、avg_tokens `23664.8333`、avg_model_calls `1.0000`
- solve 提升：`+50.02%`（但因 trust mismatch 未達公開門檻）

### 2) governed_delivery_r2
- 路徑：`.nexus/reports/bench_flash_v5_p12/governed_delivery_r2`
- Public claim gate：`FAIL`
- 失敗原因：`run_eligibility_incomplete`

數據（eligible only）：
- with_nexus：solve `1.0000`、semantic `1.0000`、trust_mismatch `0.0000`、avg_wall `66.6454s`、avg_tokens `30517.5000`、avg_model_calls `1.1667`
- without_nexus：eligible `1/6`（其餘多數 `timeout_before_model_call`）、solve `1.0000`、semantic `1.0000`、trust_mismatch `0.0000`

解讀：
- with_nexus 表現穩定且全通，但 baseline eligibility 不完整，無法作為公開 claim 的公平比較。

### 3) cost_efficiency_r2
- 路徑：`.nexus/reports/bench_flash_v5_p12/cost_efficiency_r2`
- Public claim gate：`PASS`

數據（eligible only）：
- with_nexus：solve `1.0000`、semantic `1.0000`、trust_mismatch `0.0000`、avg_wall `64.7371s`、avg_tokens `24547.5000`、avg_model_calls `1.0000`
- without_nexus：solve `0.5000`、semantic `0.5000`、trust_mismatch `0.0000`、avg_wall `19.0006s`、avg_tokens `22453.8333`、avg_model_calls `1.0000`
- solve 提升：`+100.00%`

---

## 本輪修補與驗證

### 已修補
1. `capability_ab_runner` receipt backfill
   - 當 task 期望 `codeintel`，且 scan/impact 報告存在但 receipt 缺漏時，補齊 `codeintel` receipt，避免假性 `missing_receipt`。
2. prompt leak preflight 誤判收斂
   - `needs_evidence` 等通用狀態字不再被當作 hidden literal leak。

### 測試
- `tests/benchmark/test_capability_ab_runner.py`（新增/更新 case）通過
- preflight（`nexus-value-trust-002`）由 leak fail 轉為 pass（在 hidden verifier 啟用下）

---

## 目前阻塞（公開報告角度）

1. capability_lift：with_nexus `trust_mismatch_rate=0.5`，需降到 `0` 才能過 public claim gate。
2. governed_delivery：without_nexus 多題 `timeout_before_model_call`，導致 eligibility 不完整。

---

## 下一步（P13）

1. **P13-1（P0）**：逐題修 `capability_lift` mismatch（先修 `repair-002/context-001/context-002` 三題）。
2. **P13-2（P0）**：baseline timeout 定位與止損（governed lane）：
   - 檢查 `gateway_timeout`、prompt size、model_call=0 行為；
   - 提供 lane 專用 timeout profile，先保 `eligible_n` 完整。
3. **P13-3（P1）**：重跑 `capability_lift_r3` + `governed_delivery_r3`，目標兩條皆 `public_claim_gate=PASS`。
4. **P13-4（P1）**：輸出可公開總報告（Flash，同模型穿/不穿 Nexus，三 lane 全 PASS）。
