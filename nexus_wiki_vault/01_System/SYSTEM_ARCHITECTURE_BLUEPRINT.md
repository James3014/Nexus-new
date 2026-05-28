# Nexus 系統架構藍圖 (System Architecture Blueprint)
[VERSION: v3.0.2 HARDENED - SSoT]

## 🏛️ 核心架構：中心化策略引擎 (Centralized Lane Policy)
不再採用舊版的「分散式指令 (Decentralized Command)」模式。自 v3.0 起，所有能力分發與任務路由均由 \`nexus.engine.capability_planner.py\` 統一裁決。

### 1. 層級架構 (L1-L7)
- **L1-L2 (Perception)**: 鎖定 Rust 核心 (\`nexus-core\`)，執行實體 AST 解析。
- **L3-L4 (Orchestrator)**: \`CampaignGeneral\` 負責將史詩意圖拆解為原子節點。
- **L5-L6 (Governance)**: 所有的執行收據 (\`CapabilityReceipt\`) 必須通過中心化門檻。

### ⚙️ 技術連結 (The Core Seam)
- 所有 Lane Policy 的解析現在都是單一進入點，避免了 Swarm 節點間的配置幽靈 (Ghost Configurations)。
- 強化了 UDS 通訊穩定性，防止在高併發下的 Socket 洩漏。
