# AutoResearch 三方對位真實能力矩陣
| 能力維度 | karpathy/autoresearch | ARC (Current) | DeepScientist | Nexus 控制平面目標 |
| :--- | :--- | :--- | :--- | :--- |
| **受限修改區** | ✅ 核心 (受限寫入) | ❌ 全域 (由 LLM 決定) | ❌ Quest 範圍 | ✅ 物理 Scope Lock (P2) |
| **固定評估集** | ✅ 核心 (Seed/Metric) | ❌ 隨機 (依賴 pytest) | ❌ 任務驅動 | ✅ 固定契約 Evaluator (P1) |
| **候選淘汰機制** | ✅ 候選產生與對比 | ✅ 100+ Variants | ❌ 序列探索 | ✅ Score-based 淘汰 (P1) |
| **安全回滾** | ✅ 直接覆蓋 | ❌ 無 (依賴 Git) | ✅ Git-based | ✅ 非破壞性治理回滾 (P1) |
| **人機接管** | ❌ 全自動 | ❌ 全自動 | ✅ 核心 (可接管) | ✅ 狀態機接管點 (P0) |
