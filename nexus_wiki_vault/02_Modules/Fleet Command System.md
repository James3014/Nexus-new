# 📡 Module: Fleet Command System (v23.7)

## 🌌 概述
艦隊指揮系統是 Nexus 從「單體演化」轉向「分散式多工協作」的核心。它透過主管引擎 (Supervisor Engine) 實現任務的自動化拆解、委派與總合。

## 🔩 核心組件
1. **Supervisor Engine**: 負責任務的語義拆解 (Decomposition)。
2. **Sensory Probe (Style Ingester)**: 負責吞噬外部環境審美，即時同步 \`DESIGN.md\`。
3. **Metabolism Checkpoint**: 建立物理斷點，確保任務續傳 (Resume) 能力。

## 🛠️ 操作指令
- \`nexus delegate <task>\`: 發動全艦隊合力開發。
- \`nexus resume\`: 從最後一個物理斷點恢復執行。
- \`nexus style-ingest <url>\`: 同步外部設計魂魄。

## 📈 治理要求
- 所有的 Swarm 工作必須產出物理證據 (\`swarm_work.json\`)。
- 所有的總合產物必須產出最終清單 (\`mission_complete.json\`)。
