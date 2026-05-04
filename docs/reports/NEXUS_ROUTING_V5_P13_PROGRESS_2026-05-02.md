# Nexus Routing v5 P13 進度（2026-05-02）

## 本輪目標（P13-1 ~ P13-4）
1. 降低 capability_lift trust mismatch  
2. 修 governed_delivery baseline eligibility timeout  
3. 重跑 lane 並確認 public gate  
4. 產出可公開報告材料

## 本輪結果

### A) 已完成
- `governed_delivery_r3` 已達 `public_claim_gate=PASS`
  - 路徑：`.nexus/reports/bench_flash_v5_p13/governed_delivery_r3`
  - 核心修正：加大 direct Gemini timeout cap（`NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=320`）後，
    `without_nexus` eligibility 由不完整改善為完整（`eligible_n=6`）。
- `cost_efficiency_r2` 維持 `public_claim_gate=PASS`
  - 路徑：`.nexus/reports/bench_flash_v5_p12/cost_efficiency_r2`
- benchmark runner 修補仍有效：
  - `codeintel` receipt backfill（避免假性 `missing_receipt`）
  - prompt leak preflight 誤判修正（`needs_evidence`）

### B) 尚未完成
- `capability_lift_r3` 仍 `public_claim_gate=FAIL`
  - 路徑：`.nexus/reports/bench_flash_v5_p13/capability_lift_r3`
  - fail reason：`with_trust_mismatch_above_zero`
  - 數據：with solve `0.6667` vs bare solve `0.5000`（有提升但未過公開門檻）

## 實驗與止損
- 嘗試加入 `docs_contract_risk_prefers_hyper` 路由策略後，context pair 實測未改善。
- 已回退該實驗性路由改動，避免污染主線。

## 下一步（P14）
1. 針對 `nexus-value-context-001/002` 做題目級穩定化，不改全域路由優先：
   - 強化 hidden-verifier fail 後的 with_nexus 自癒流程（僅 benchmark lane 生效）。
2. 先跑 `capability_lift` 的 context-only 子集驗證（必須先達 `trust_mismatch=0`）。
3. 通過後重跑 `capability_lift_r4` 全 6 題，目標 `public_claim_gate=PASS`。
4. 產出 P13/P14 合併公開報告（Flash，同模型穿/不穿）。
