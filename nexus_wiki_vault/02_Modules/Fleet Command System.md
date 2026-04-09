# 📡 Module: Fleet Command System (v23.7)

## 🌌 概述
艦隊指揮系統是 Nexus 從「單體演化」轉向「分散式多工協作」的核心。它透過主管引擎 (Supervisor Engine) 實現任務的自動化拆解、委派與總合。

## 🔩 核心組件
1. **Supervisor Engine**: 負責任務的語義拆解 (Decomposition)。
2. **Sensory Probe (Style Ingester)**: 負責吞噬外部環境審美，即時同步 \`DESIGN.md\`。
3. **Session Metabolism Engine (AutoDream)**: 取代了暴力的字串截斷，透過語義蒸餾 (Distillation) 將數萬 Token 的繁雜 Task Tree、失敗教訓與核心信念（Beliefs）壓縮成一顆極其輕量的 `session_seed.json` (結晶種子)。這不僅建立了物理斷點確保續傳 (Resume) 能力，更是阻斷 LLM「幻覺連鎖反應」與達成「超低延遲啟動 (TTFT)」的核心無損蒸餾機。

## 🛠️ 操作指令
- \`nexus delegate <task>\`: 發動全艦隊合力開發。
- \`nexus resume\`: 從最後一個物理斷點恢復執行。
- \`nexus style-ingest <url>\`: 同步外部設計魂魄。

## 🧬 Federated Learning v0.9 (艦隊演化)

Nexus v0.9 將單機 NAS 優化提升至 **聯邦學習 (Federated Learning)** 級別，實現跨租戶的智慧聚合與隱私保護。

### 核心機制：FedAvg + DP-SGD
- **聚合演算法**: `FedAvg` (Federated Averaging)，透過 `np.mean` 彙整各租戶的 16 維 `router_bias_delta`。
- **隱私防禦**: `DP-SGD` (Differential Privacy)，注入 **拉普拉斯噪聲 (Laplace Noise)**。
    - **隱私預算 (ε)**: 1.0
    - **靈敏度縮放**: 0.002
- **目標 Fitness**: **0.995** (SOTA 級別收斂)。

### 物理實作
- **入口腳本**: `uv run scripts/ops/federated_engine_v09.py`
- **數據載體**: `tenants/tenant-000~009/dna_delta.json`
- **全域 DNA**: `configs/federated_dna.yaml`

## 📈 治理要求
- 所有的 Swarm 工作必須產出物理證據 (\`swarm_work.json\`)。
- 所有的總合產物必須產出最終清單 (\`mission_complete.json\`)。
- **聯邦同步**: 必須維持 10/10 的租戶聚合比例，否則 CI 守門拒絕發版。
