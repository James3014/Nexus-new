# Nexus 演化史：從雲端 AI 編排器到本地模型治理作業系統（v1 → v28）

**文件版本**: 3.0
**最後更新**: 2026-06-16
**適用對象**: 投資人、使用者、未來合作夥伴

---

## Executive Summary

Nexus 於 2026 年 2 月底誕生，在 4 個月內從 v1 演進至 v28.3。演化分為兩個截然不同的時代：

**雲端時代（2026-02 至 2026-05）**：Nexus 是一個包裝 Gemini/Codex/GPT 等雲端模型的 AI 編排器。它在雲端模型的強大推理能力之上，疊加了治理、記憶、學習等能力。v1 到 v25 的所有 SOTA 成績，都是雲端模型跑出來的。

**本地時代（2026-05-30 至今）**：Nexus 轉向本地 Qwen2.5 3B/7B/14b 模型。這是一個根本性的轉變——從「借助雲端大腦」變成「訓練本地小腦」。v26 之後的所有版本，都是在這個新範式下演進。

**轉折點**：2026-05-30，第一個 Ollama/Qwen2.5 commit，使用 14b 模型成功修復 astropy SWE-bench 實例。從那天起，Nexus 的核心問題從「如何更好地利用雲端模型」變成「如何讓本地小模型接近雲端模型的能力」。

**最終狀態（v28.3）**：在自建 benchmark 上 100% solve rate（bare 86.7% → Nexus 100%），在真實 SWE-bench 任務 astropy-14096 上首次成功修復（本地 14b 模型）。但真實 SWE-bench 的完整評估仍在進行中。

---

## 第一章：雲端時代（v1 - v25）

### 歷史背景

Nexus 於 2026 年 2 月底誕生，最初的模型後端是 **Gemini CLI** 和 **Codex CLI**——都是雲端 API。2026-03-11 遷移到當前 repo（`440aa906`: "Initial migration to Muse-Nexus"），隨後在 2026-03-14 發布 v9。

> commit `3929a49a`（2026-03-13）: "fix(gardener): switch subconscious reflection to **Gemini CLI flash model**"
> commit `761059fe`（2026-03-13）: "feat(codex-loop): add **gemini handoff** prompt adapter"

### v9「Autonomic」— 雲端模型的治理化（2026-03-14）

**代號**: Autonomic
**模型後端**: Gemini Flash + GPT（via Codex CLI）

v9 是 Nexus 第一個被命名的版本。它的核心創新不在模型本身（那是雲端廠商的工作），而在於**如何控管雲端模型的輸出**。

**核心突破**：
1. **Verification-Driven Development (VDD)**: 所有任務在執行前必須通過語義與安全性靜態掃描
2. **Phantom Guard**: 防止 AI 生成的「幻覺成功」——如果模型說「我修好了」但沒有物理 patch，任務被攔截
3. **Crystal Project（經驗結晶化）**: 每個成功的任務軌跡被存入 `.musestate`，實現跨會話經驗繼承
4. **P-D-R-A-C 生命周期**: Planning → Doing → Reviewing → Acting → Checking 閉環

**本質**: v9 不是「讓模型更聰明」，而是「讓模型的輸出更可信」。這在雲端時代是一個正確的策略——因為雲端模型的能力已經很強，瓶頸在於信任和治理。

---

### v16「Universal SOTA」— 雲端模型的天花板（2026-03-24）

**代號**: Battlesuit
**模型後端**: Gemini + Codex（雲端）

v16 在 70 個基準測試任務上全部通過。這是 Nexus 雲端時代的第一個里程碑——證明了在正確的治理框架下，雲端模型可以穩定地解決複雜任務。

---

### v17「Singularity OS」— 85.5% SOTA（2026-03-26）

**代號**: Singularity
**模型後端**: Gemini + Codex（雲端）

v17 將 SOTA 分數從 70/70 提升到 85.5%。同時引入了 Singularity Dashboard，讓操作者可以即時監控系統狀態。

**歷史意義**: v17 的 85.5% 是雲端模型在 Nexus 治理框架下的上限。之後的版本開始面臨一個問題：**雲端模型的能力已經夠了，但成本和延遲怎麼辦？**

---

### v19-v22: 從治理到生產（2026-03 ~ 2026-04）

這段時期的版本（v19 Tactical Swarm、v20 Latent Planning、v22 Eternal Neural Swarm）都是在雲端模型的基礎上，逐步建立生產級能力：

- **v19**: 多 agent 協作（Swarm DAG），吞吐量 +200%
- **v20**: JEPA 預測（零 token 規劃），ROI 預測精度 >85%
- **v22**: 多叢集聯邦部署，RTO 18 秒，首次進入生產級

**v22 的里程碑**: 100 PR 壓力測試 P95 2.8 秒、Chaos RTO 18 秒、3+ 叢集同步。這是在雲端模型上驗證的——因為本地模型當時還不夠快、不夠穩。

**v22 的基準測試框架**: 2026-04-25 開始建立 public benchmark framework（`4a828c96`），測試 Gemini Flash + Nexus 的組合。

---

### v23-v25: 治理的極致化（2026-04 ~ 2026-05）

- **v23**: 19 層治理架構，context 減量 30%
- **v24**: 治理的物理化（硬合約、回滾機制）
- **v25**: Brain-Armor Fusion（大腦 + 戰甲融合）

**雲端時代的結束信號**: 2026-05-28 的 L5.7 架構（`2c5b24b8`）是最後一個純雲端時代的架構。從那天起，系統開始為本地模型的轉型做準備。

---

## 第二章：轉折點（2026-05-30）

### 那一天發生了什麼

2026-05-30 07:47，第一個本地模型 commit：

> `a8afbb92`: "feat(local_heal): implement soft search replace parser and successfully solve astropy SWE-bench instance using 14b"

在同一天之內，commit message 聲稱連續修復了 3 個 astropy SWE-bench 實例（14096、13033、13236）。但**事實並非如此**——這些 commit 只是記錄「模型產出了 patch」，不代表 patch 通過了驗證。

以 astropy-13236 為例，模型產出的 patch 包含語法錯誤：

```python
# 少了 'd'
if not isinstance(data, Column):ata_is_mixin

# 無效的 Python 語法
index.columns[index.col_position(col.info.name)] = new_col.info.indices.append(index)
```

當時的 `predictions_swe.jsonl` 是手動寫入的，沒有經過完整的 reproduction → planning → localization → patch → verification pipeline 驗證。commit message 中的「successfully solve」是誇大的。

隨後建立了完整的 local_heal pipeline：BM25 + AST hybrid localizer、fuzzy SEARCH/REPLACE matcher、AST syntax validator、self-correction retry loop。這些基礎設施是真實的，但早期的「解題」記錄不可靠。

### 為什麼要轉向本地模型

從雲端到本地不是退步，而是**生存策略**。

轉向的核心動機是**成本風險**：商用模型（Gemini、GPT、Claude）的 API 費用持續上升，如果不建立本地模型能力，Nexus 的整個商業模式將被綁死在雲端廠商的定價權上。這不是「想不想」的問題，而是「能不能活下去」的問題。

次要因素：
1. **成本可控**: 本地模型一旦載入，邊際成本接近零；不受 API 漲價影響
2. **延遲穩定**: 本地推理不受網路波動影響
3. **隱私合規**: 代碼和 prompt 不會離開本機
4. **可用性**: 不依賴 API 配額和網路連線
5. **可定製**: 可以透過 LoRA/fine-tuning 針對特定領域優化

### 雲端時代的遺產如何繼承

Nexus 雲端時代建立的治理框架（VDD、Phantom Guard、Learning Closure、Evidence Chain）全部保留。本地時代的挑戰是：**如何在更弱的模型上，複製雲端模型的表現？**

答案是：**Nexus 的治理框架本身就是價值**。雲端模型之所以在 Nexus 下表現好，不只是因為模型聰明，而是因為 Nexus 的 pipeline 提供了精確的 context、結構化的 prompt、和驗證機制。這些機制在本地模型上同樣有效——甚至更重要，因為本地模型更需要「被引導」。

### 本地時代的真實起步

2026-05-30 的首次嘗試暴露了本地模型的核心問題：**模型可以生成 patch，但 patch 的品質不穩定**。語法錯誤、格式不對、邏輯不完整是常見的問題。這促使了 local_heal pipeline 的誕生——一個專門為本地模型設計的「引導+驗證」系統，確保模型的輸出經過多層過濾和修正。

---

## 第三章：本地時代（v26 - v28）

### v26「Algebraic Reasoning」— 本地模型的治理化（2026-06）

**代號**: Singularity
**模型後端**: Qwen2.5 7b/14b via Ollama

v26 是第一個專為本地模型設計的版本。核心創新是**代數化推理**——讓本地模型可以「推導出為什麼這樣做」。

**核心突破**:
1. **Algebraic Reasoning Evidence Chain**: 每個決策都有完整的推導鏈
2. **Blackboard Handoff Seam**: 跨 phase 的狀態共享
3. **Committee Orchestrator v26.5**: Multi-sample search + verifier-backed selection
4. **Calibration & Verifier Pack**: 校準系統，95% 成功率

**v26.5 的搜尋-驗證器平台**: 將 search 和 verification 拆分為 micro-contexts，提升本地模型在複雜任務上的精確度。

---

### v27「Modular Assembly Line」— 本地模型的工業化（2026-06）

**模型後端**: Qwen2.5 7b/14b + 3B Advisor

v27 將本地模型的能力從「偶爾成功」變成「可量產」。

**核心突破**:
1. **Local Deliberation Lane**: 7B 做 worker，14B 做 judge，3B 做 advisor
2. **Mass Production**: 針對 Django 和 Astropy 家族的大規模生產
3. **Modular Assembly Line**: 治理合約的標準化組裝

---

### v28「Meta-Stable Governance」— 架構凍結（2026-06）

**模型後端**: Qwen2.5 3B/7B/14b + Rules (L0)

v28 是目前的穩定版本（v28.3.0），也是 Nexus 歷史上第一個被「凍結」的架構。

**核心突破**:
1. **四層模組邊界**: 狀態層、遙測層、檢索層、判決層的公共介面進入 Stable 狀態
2. **Migration Contracts**: 舊版數據的遷移合約
3. **Local Heal Pipeline**: 全自動化修復流水線
4. **三層模型架構**:

| 層級 | 模型 | 角色 | 權限 |
|------|------|------|------|
| L0 | Rules | Runtime Governance | **唯一 authority** |
| L1 | 1.5B | Optional front-door hint | Advisory only |
| L2 | 3B | Shadow Advisor | Advisory only |
| L3 | 7B | Worker Lane | Advisory only |
| L4 | 14B | Judge/Synthesizer | Advisory only |

**架構凍結的意義**: 未來的改進只能在現有架構內進行，或者通過正式的 RFC 流程。

---

## 第四章：本地模型時代的量化表現

### 4.1 Token AB（180 runs，20 任務 × 3 trials × 3 modes）

| Mode | 成功率 | 回歸數 | 平均 tokens | 平均延遲 |
|------|--------|--------|------------|---------|
| Bare (Qwen2.5) | 86.7% | 8 | 15,912 | 83.2s |
| With Nexus | **100%** | 0 | 10,718 | 76.2s |

**Lift: +13.3pp，token -33%，回歸 8→0。**

### 4.2 真實 SWE-bench

- astropy-14096: ✅ solve_eligible=true（7b planning + 14b patching，312s）
- astropy-14182: ❌
- 真實任務勝率：1/2（樣本量太小）

### 4.3 與雲端模型的差距

| 指標 | 雲端時代 (v17, Gemini) | 本地時代 (v28, Qwen2.5) |
|------|----------------------|------------------------|
| SOTA 分數 | 85.5% | 100%（自建 benchmark） |
| 真實 SWE-bench | 未測試（雲端模型不需要 Nexus） | 1/2（進行中） |
| 成本 | 每次 API 調用 ~$0.01-0.10 | 本地推理成本 ~$0 |
| 延遲 | TTFT 受網路影響 | 本地推理延遲可控 |
| 隱私 | 代碼離開本機 | 代碼不離開本機 |

---

## 第五章：技術護城河（跨時代繼承）

### 5.1 VDD（Verification-Driven Development）— v9 遺產

v9 建立的 VDD 在本地時代變得更重要。雲端模型的輸出品質高，VDD 是「锦上添花」；本地模型的輸出品質波動大，VDD 是「必要防線」。

### 5.2 Phantom Guard — v9 遺產

防止幻覺成功的機制。在本地模型上，幻覺率更高，Phantom Guard 的價值更大。

### 5.3 Learning Closure — v9 遺產

從 bug 到免疫細胞的閉環。每一次失敗都被記錄、分析、並轉化為新的閘門規則。

### 5.4 Meta-Routing — v22 遺產

A/B 測試驅動的能力路由。在本地時代，這個機制用來決定「用 7b 還是 14b」、「要不要啟動 deliberation」。

### 5.5 三層模型架構 — v28 創新

L0 規則引擎（唯一 authority）+ 1.5B gatekeeper + 3B advisor + 7B worker + 14B judge。這是本地時代的獨特架構——雲端時代不需要這麼多層，因為雲端模型本身就夠強。

---

## 第六章：未來路線圖

### 短期（1-3 個月）

1. **擴大 SWE-bench 評估**: 10-20 個 Verified 任務
2. **Repo Map 實現**: AST-based 倉庫結構索引
3. **Test-Driven Refinement**: 測試失敗回饋到 prompt

### 中期（3-6 個月）

1. **Code2LoRA**: 為每個 repo 生成專屬 LoRA adapter
2. **PACT 壓縮**: 3B advisor token -40-50%
3. **SWE-Explore**: Multi-granularity retrieval

### 長期（6-12 個月）

1. **BenchEvolver**: 自我挑戰訓練
2. **EvoMem**: Patch-based evolution memory
3. **多語言支援**: JavaScript/TypeScript/Rust

---

## 附錄：版本里程碑時間線

### 雲端時代

| 版本 | 代號 | 時間 | 模型後端 | 核心里程碑 |
|------|------|------|---------|-----------|
| v1 | - | 2026-02 | Gemini + Codex | Nexus 誕生 |
| v9 | Autonomic | 2026-03-14 | Gemini + Codex | VDD, Phantom Guard, Crystal Project |
| v16 | Battlesuit | 2026-03-24 | Gemini + Codex | 70/70 SOTA |
| v17 | Singularity | 2026-03-26 | Gemini + Codex | 85.5% SOTA, Dashboard |
| v19 | Tactical Swarm | 2026-03-31 | Gemini + Codex | Swarm DAG, +200% throughput |
| v20 | Latent Planning | 2026-03-31 | Gemini + Codex | JEPA zero-token planning |
| v22 | Eternal Neural Swarm | 2026-04-01 | Gemini + Codex | Multi-cluster federation, RTO 18s |
| v23 | 19-Layer Governance | 2026-04-05 | Gemini + Codex | Context -30%, governance injection |
| v24 | Governance Hardening | 2026-04-10 | Gemini + Codex | Physical governance contracts |
| v25 | Brain-Armor Fusion | 2026-05 | Gemini + Codex | Soul Pentad, Plan-to-Build Compiler |

### 轉折點

| 日期 | 事件 | 意義 |
|------|------|------|
| 2026-05-30 07:47 | 第一個 Ollama/Qwen2.5 commit | 雲端→本地的轉折點 |
| 2026-05-30 | 模型生成了 3 個 astropy patch（未經驗證） | 暴露本地模型的核心問題：patch 品質不穩定 |
| 2026-06-16 | astropy-14096 經完整 pipeline 驗證成功 | 本地模型首次真正修復真實 SWE-bench 任務 |

### 本地時代

| 版本 | 代號 | 時間 | 模型後端 | 核心里程碑 |
|------|------|------|---------|-----------|
| v26 | Algebraic Reasoning | 2026-06 | Qwen2.5 7b/14b | Evidence chain, Blackboard handoff |
| v27 | Modular Assembly Line | 2026-06 | Qwen2.5 7b/14b + 3B | Deliberation lane, mass production |
| v28 | Meta-Stable Governance | 2026-06 | Qwen2.5 3B/7B/14b | Architecture freeze, 4-layer boundaries |

---

## 附錄：關鍵數據來源

| 數據 | 來源 | 驗證狀態 |
|------|------|----------|
| 首次 commit | `git log --reverse` (440aa906, 2026-03-11) | ✅ |
| 雲端模型使用 | `git log` (3929a49a: "Gemini CLI flash model") | ✅ |
| 本地模型轉折 | `git log` (a8afbb92, 2026-05-30: "solve astropy using 14b") | ✅ |
| Token AB 180 runs | `.nexus/reports/token_ab/runs_raw.jsonl` | ✅ |
| astropy-14096 receipt | `.nexus/reports/local_heal/astropy__astropy-14096/receipt.json` | ✅ |
| v22 production metrics | `RELEASE_NOTES.md` | ✅ |
| v28 architecture freeze | `28_V28_ARCHITECTURE_FREEZE.md` | ✅ |
