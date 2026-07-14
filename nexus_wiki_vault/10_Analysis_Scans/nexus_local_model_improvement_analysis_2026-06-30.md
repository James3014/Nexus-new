# 本地模型改善分析（白話版）
**日期**：2026-06-30（更新）

---

## 你的目標

| 情境 | 行為 |
|------|------|
| 雲端模型可用 | 雲端做主力，本地小模型幫忙輔助，省 token 和 retry 成本 |
| 雲端模型不可用 | 直接切到本地模型執行，不中斷 |

**已知主線**：3B judge + Qwen 7B + DeepSeek 6.7B + Nexus armor
**原則**：不開新路由，保持 6 月優化，本地模型要能用 Nexus 全能力

---

## 關鍵發現：本地模型沒有用到 Nexus 全能力

### 五月 Gemini + Nexus 全能力路由

```
任務 → CapabilityPlanner 選 34+ 個能力
  → S: Scope (file_lock, mempalace_gate, pregate)
  → P: Plan (codeintel, research, memory, belief, skill routing)
  → X: Recon (codeintel, research, lancedb, xray, architecture_scout)
  → D: Decide (autoreason, belief, ultra_review, swarm)
  → R: Repair (hyper, nightshift, drone, rlm, repair_loop)
  → A: Audit (artifact_gate, claim_gate, sandbox, jit_validation)
  → C: Closure (delivery_gate, learning, benchmark, meta_opt)
```

五支柱全部參與：LanceDB 找相似案例、Memory 記經驗、MemPalace 防越權、Belief 控信心、Artifact/Claim 驗證證據

### 現在本地模型實際執行的能力

| 能力 | 狀態 | 說明 |
|------|------|------|
| local_model_executor | ✅ 有 | 本地模型執行核心 |
| ddtree | ✅ 有 | 決策樹加速 |
| autoreason | ✅ 有 | 推理評審 |
| artifact_gate | ✅ 有 | 證據驗證 |
| claim_gate | ✅ 有 | 斷言驗證 |
| delivery_gate | ✅ 有 | 交付驗證 |
| repair_loop | ✅ 有 | Path A 修復流程 |
| memory | ⚠️ 只讀 | 被動 trace，不主動決策 |
| codeintel | ❌ 沒有 | 外部專用 |
| lancedb | ❌ 沒有 | 外部專用 |
| belief | ❌ 沒有 | 外部專用 |
| mempalace | ❌ 沒有 | 外部專用 |
| research | ❌ 沒有 | 外部專用 |
| hyper | ❌ 沒有 | 外部專用 |
| swarm/drone/nightshift | ❌ 沒有 | 外部專用 |
| sandbox | ❌ 沒有 | 外部專用 |

**34+ 個能力只用了 7 個**。五支柱只有 Artifact/Claim 有本地執行。

---

## 目前做到了哪裡

### 已完成（可以動的）

1. **三條執行路徑都接好了**
   - `single_local_model`：直接叫 Ollama 跑模型
   - `local_committee_only`：3B 當 judge、Qwen 7B 當主 proposer、DeepSeek 6.7B 當備用 proposer，Nexus armor 做格式修正
   - `localheal_pipeline`：走 HealPipeline 修復流程（C9 之後不再是空殼，有真實執行）

2. **6 月優化全部保留**
   - AG1：3B 同時當 gate + critic + evidence judge（省 call 次數）
   - AG2：只有意見不合時才叫 DeepSeek 6.7B（省 call 次數）
   - AG3：簡單任務 1.2 calls、困難任務 1.9 calls
   - AG4：不需要 14B
   - AG5：3B + 雙 7B 路線確認可行

3. **C10B 新模組已寫好（但還沒接進主流程）**
   - `HeterogeneousCandidateProvider`：根據任務特性決定要叫幾個模型
   - `JudgeSelector`：3B 用「角色優先順序」選出最佳候選
   - `CandidateIsolationGate`：U3 安全閘門，確保 hash 對得上、候選有隔離、verifier 有通過

4. **11 個新測試全部通過**

### 還沒接好的

| 項目 | 狀態 | 說明 |
|------|------|------|
| C10B 模組接進主執行流程 | ❌ 模組寫好了但沒接 | `HeterogeneousCandidateProvider` 和 `JudgeSelector` 還沒被 `local_model_executor.py` 呼叫 |
| 雲端偵測邏輯 | ⚠️ 測試有跑通但沒正式接 | `cloud_available` 資料有流過 `route_context`，但 planner 還沒自動判斷 |
| Runtime policy 改成可設定 | ❌ 硬編碼 False | `mutation_allowed` 等開關寫死關閉，需要改成用環境變數控制 |
| U3 完整接進主路徑 | ⚠️ 閘門寫好了但沒接 | `candidate_isolation_gate.py` 存在，但主執行流程還沒呼叫它 |
| 真實 Ollama 端到端測試 | ❌ 需要環境變數才跑 | 設 `NEXUS_RUN_REAL_LOCAL_MODEL_TESTS=1` 才會跑真實模型 |

### 缺的最大一塊：本地模型沒用到 Nexus 全能力

| 缺的能力 | 為什麼缺 | 能不能接上本地 |
|----------|----------|---------------|
| lancedb | 外部專用，沒接本地 | ✅ 可以 — 本地 embedding 找相似案例，不需要大模型 |
| memory | 只讀 trace，不主動決策 | ✅ 可以 — 本地讀寫經驗，不需要大模型 |
| sandbox | 外部專用，沒接本地 | ✅ 可以 — 本地跑 pytest，不需要大模型 |
| codeintel | 外部專用，沒接本地 | ⚠️ 部分可以 — 本地 AST 分析，但深度有限 |
| belief | 外部專用，沒接本地 | ⚠️ 部分可以 — 本地用規則判斷信心，不需要大模型 |
| mempalace | 外部專用，沒接本地 | ⚠️ 部分可以 — 本地用規則檢查治理邊界 |
| research | 需要網路搜尋 | ❌ 難做 — 本地沒網路搜尋能力 |
| hyper | 需要大模型生成候選 | ❌ 不適合 — 本地 7B 生成品質不夠 |
| swarm/drone/nightshift | 需要多 agent 協作 | ❌ 不適合 — 本地沒有多 agent 基礎設施 |

---

## 下一步怎麼做（按順序）

### 第一步：把 C10B 模組接進主流程（約 1 天）

**做什麼**：在 `local_model_executor.py` 的 `local_committee_only` 分支裡，把 `HeterogeneousCandidateProvider` 和 `JudgeSelector` 接進去。

**效果**：
- 任務簡單 → 只叫 Qwen 7B（省成本）
- 任務有分歧 → 加叫 DeepSeek 6.7B（提品質）
- 3B judge 用角色優先順序選出最佳候選

### 第二步：接上本地能跑的 Nexus 能力（約 2-3 週）

**做什麼**：把 lancedb、memory、sandbox、codeintel、belief、mempalace 接上本地執行。

**效果**：本地模型從 7/34 個能力 → 13/34 個能力，接近五月全能力路由的一半。

| 能力 | 接法 | 工作量 |
|------|------|--------|
| lancedb | 本地 embedding + 向量搜尋 | 3 天 |
| memory | 本地讀寫經驗库 | 2 天 |
| sandbox | 本地跑 pytest | 2 天 |
| codeintel | 本地 AST 分析 | 3 天 |
| belief | 本地規則判斷信心 | 1 天 |
| mempalace | 本地規則檢查治理邊界 | 1 天 |

### 第三步：Runtime policy 改成環境變數控制（約 0.5 天）

**做什麼**：把 `capability_runtime_policy.py` 裡面寫死的 `False` 改成讀環境變數。

**效果**：預設還是關閉（安全），但需要時可以用環境變數打開。

### 第四步：U3 閘門接進主路徑（約 1 週）

**做什麼**：在候選選完之後、回傳結果之前，跑 `validate_candidate_isolation_receipt()`。

**效果**：如果 hash 不對、候選沒隔離、verifier 沒過，就不允許宣稱「local-only full execution」。

### 第五步：真實模型端到端測試（約 2 天）

**做什麼**：開 Ollama、跑真實 Qwen 7B + DeepSeek 6.7B，跑完整流程。

---

## 結論

| 項目 | 狀態 |
|------|------|
| 三條執行路徑 | ✅ 接好 |
| 6 月優化 | ✅ 保留 |
| C10B 模組 | ✅ 寫好，❌ 沒接 |
| Nexus 全能力 | ❌ 只用了 7/34 個 |
| 本地可接的能力 | lancedb、memory、sandbox、codeintel、belief、mempalace |
| 估計全部接好 | 約 3-4 週 |

---

## 檔案位置

| 檔案 | 路徑 | 用途 |
|------|------|------|
| 本地模型執行器 | `nexus/services/local_heal/local_model_executor.py` | 三條路徑的切換核心 |
| C10B 異質候選 | `nexus/services/local_heal/heterogeneous_candidate_provider.py` | 根據任務決定叫幾個模型 |
| C10B Judge 選擇器 | `nexus/services/local_heal/judge_selector.py` | 3B 用角色優先順序選候選 |
| U3 隔離閘門 | `nexus/services/local_heal/candidate_isolation_gate.py` | hash 對比 + 隔離 + verifier |
| Path A 執行器 | `nexus/services/local_heal/local_model_capability_executors.py` | C9 之後有真實執行 |
| Runtime Policy | `nexus/services/local_heal/capability_runtime_policy.py` | mutation/model call 開關（目前寫死 False） |
| Planner | `nexus/engine/capability_planner.py:884` | 決定用哪條 topology |
| CapabilityPlanner | `nexus/engine/capability_planner.py:34-633` | 34+ 能力定義（本地只用了 7 個） |
