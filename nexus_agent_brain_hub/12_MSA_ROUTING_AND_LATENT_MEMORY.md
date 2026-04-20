# 🧬 MSA Routing & Latent Memory Architecture

## 1. 核心定義 (Experimental POC)
MSA Routing 是將模型層的 Memory Sparse Attention 概念引入 Nexus 治理層，實現「記憶容量」與「推理能力」的解耦。

## 2. 三階段推理管線 (3-Stage Inference)

### 階段 1：離線編碼 (Offline Encoding)
- **msa_indexer.py**: 透過 `git diff` 進行增量索引。
- **Metadata**: 掛載 `type` (code, belief, artifact, rule) 與 `source_hash`。

### 階段 2：線上路由 (Online Routing)
- **msa_router_contract.py**: 實作 `Fail-Closed` 機制。
- **門檻**: 若 `confidence_score < 0.75`，回傳 `UNKNOWN`，阻斷無根據的生成。

### 階段 3：稀疏生成 (Sparse Generation)
- **Context Interleaving**: 僅將經由 Router 選中的 Top-k 記憶節點注入 Context Window。
- **Tier 0 Protect**: `MemPalace` 規約強制不被稀疏化，永遠掛載於頂層。

## 3. 記憶免疫系統 (Immune System)
- **msa_quarantine.py**: 所有新生成的證據必須在隔離區通過「雙門檻驗收」後才能被 Promote。
- **msa_lifecycle.py**: 當 `source_hash` 漂移時，自動觸發信心度衰退 (`confidence_decay`)。

---
**[Source: nexus_wiki_vault/04_Research/MSA_Routing_Architecture.md]**
