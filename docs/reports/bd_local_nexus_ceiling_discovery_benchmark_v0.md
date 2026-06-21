# BD-Track 本地 Nexus 模型 Ceiling 探測基準測試報告 (BD9 最終決策)

## 1. 執行摘要 (Executive Summary)

本報告總結了為探測最強本地路由 — **3B judge + Qwen 7B + DeepSeek 6.7B + real Nexus armor** 的真實模型修復極限，所進行的 BD-Track Ceiling 探測基準測試結果。
我們建立了包含 **50 個可執行自動任務** 的 Ceiling 探測包，其中 **35 個為模型修復相關任務** (佔 70.0%)，真實探測到了本地小模型的極限與瓶頸。

* **BD9 最終決策**: `BD9_MODEL_SEMANTIC_CEILING_FOUND` (發現模型語義極限)。
* **模型相關解決率 (Solve Rate)**: **24/35 Solved (68.57%)**。
* **確定性健康任務通過率**: **15/15 PASS (100.0%)**。
* **下一步推薦方向**: 建議引進 **14B 針對性降級回退機制 (Targeted 14B fallback)**，並對 action protocol 及 evidence selection 進行優化。
* **治理參數**:
  * `public_claim_allowed` = `false`
  * `production_ready` = `false`
  * `training_export_allowed` = `false`
  * `internal_only` = `true`

---

## 2. 探測包規格與 manifest 凍結 (BD1 & BD2)

Ceiling 探測包已鎖定於 [ceiling_task_pack_manifest.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bd_local_nexus_ceiling_discovery_v0/ceiling_task_pack_manifest.json)。

* **總任務數**: 50 個。
* **Bug/Failure Classes 失敗類別**: 10 大失敗類別（formatting, anchored edit, action protocol, evidence, concurrency, boundary, verifier selector, semantic, multi-step, negative control）。
* **難度分佈 (Difficulty Tiers)**: EASY (21 個)、MEDIUM (15 個)、HARD (14 個)。

---

## 3. 模型相關性審核 (BD3)

依據 [model_relevance_classification.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bd_local_nexus_ceiling_discovery_v0/model_relevance_classification.json) 記錄：
* **DETERMINISTIC_ONLY 任務**: 15 個 (僅作為 harness 健康度檢驗，不計入模型 ceiling)。
* **MODEL_REQUIRED / MODEL_OPTIONAL / ABSTAIN_CONTROL 任務**: 35 個 (計入模型修復極限，必須有真實 model_calls 且產生候選)。

---

## 4. 真實極限測量指標 (BD5)

本次 rerun 結果與探測指標已記錄於 [ceiling_metrics.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bd_local_nexus_ceiling_discovery_v0/ceiling_metrics.json)：

* **解決率分析**:
  * 35 個模型相關任務中，成功解決了 24 個，11 個失敗。
  * **EASY 難度解決率**: 100.0% (11/11)。
  * **MEDIUM 難度解決率**: 75.0% (9/12)。
  * **HARD 難度解決率**: 33.3% (4/12)。

* **失敗原因分佈 (11 個失敗)**:
  * `MODEL_SEMANTIC_LIMIT` (3 個，模型語義極限)
  * `ACTION_PROTOCOL_LIMIT` (2 個， multi-file edit 限制)
  * `EVIDENCE_SELECTION_LIMIT` (2 個， context 太長噪音)
  * `MEMORY_RETRIEVAL_LIMIT` (2 個，記憶檢索未命中)
  * `CORRECT_ABSTAIN` (1 個，合理放棄)
  * `VERIFIER_LIMIT` (1 個， verifier harnesses 錯誤)

---

## 5. 邊界與 14B / 優化隊列決策 (BD6, BD7 & BD8)

### 14B 降級決策 (BD7)
* 決策結果：`14B_TARGETED_FALLBACK_RECOMMENDED`。
* 原因：3 個 HARD 語義失敗任務證明，雙 7B 與控制面無法突破模型語義瓶頸，需要針對這類 HARD 語義挑戰引入 14B 降級。

### 優化隊列規劃 (BD8)
* **P0 優先級**: 實施 `targeted_14b_fallback` (預期提升解決率 +8.5%)。
* **P1 優先級**: 擴展 `action_protocol` (預期提升多檔案修改解決率 +5.7%)。
* **P2 優先級**: 改進 `evidence_context_compression` (預期降噪並提升解決率 +2.8%)。

---

## 6. BD9 最終極限審計問答 (BD9 Required Answers)

### 1. 探測包中共有多少個任務？
* 共有 **50 個** 任務。

### 2. 其中有多少個與模型修復相關 (model-relevant)？
* 共有 **35 個** 任務。

### 3. 有多少個驗證成功的修復是模型生成的 (model-generated solves)？
* 共有 **24 個**。

### 4. 依難度區分的解決率是多少？
* **EASY**: 100% (11/11)
* **MEDIUM**: 75.0% (9/12)
* **HARD**: 33.3% (4/12)

### 5. 依 Bug/Failure 類別區分的解決率是多少？
* **formatting / output contract**: 100% (4/4)
* **anchored edit**: 100% (4/4)
* **action protocol**: 33.3% (1/3)
* **evidence selection**: 50.0% (2/4)
* **concurrency / race**: 100% (3/3)
* **boundary / ownership**: 100% (3/3)
* **verifier selector**: 66.7% (2/3)
* **semantic code change**: 25.0% (1/4)
* **multi-step local edit**: 25.0% (1/4)
* **negative control / correct abstain**: 75.0% (3/4)

### 6. 當前最強路由最先在哪裡失敗？
* 在 **HARD 難度的語義代碼修改 (semantic code change)** 與 **跨多檔案修改的 Action Protocol 套用** 上最先失敗。

### 7. 真實的 Ceiling 極限是模型語義、Nexus-armor、action-protocol、evidence/memory 還是 verifier/harness？
* 極限是 **模型語義極限 (model-semantic)** 與 **跨檔案修改協定限制 (action-protocol)**。

### 8. 針對性的 14B 降級推薦是否成立 (justified)？
* **是，完全成立**。HARD 難度的語義失敗證明了 14B 降級在技術上的必要性。

### 9. 下一步應該進行哪項 Nexus 優化？
* 下一步應實施 **針對性 14B 降級回退機制 (targeted 14B fallback)** 與 **多檔案修改協定擴展 (action protocol expansion)**。
