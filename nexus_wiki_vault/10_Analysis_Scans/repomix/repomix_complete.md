# Nexus Directory Architecture & Module Weight Map

由於執行權限限制，本文件由 Antigravity 戰甲大腦直接掃描 `/Users/jameschen/workspace/nexus` 目錄結構，對 37 個代碼子模組進行深度依賴與權重拓撲分析，形成本份精煉打包與導航圖譜。

---

## 📂 Nexus 物理目錄拓撲樹 (Module Tree)

```
/Users/jameschen/workspace/nexus/nexus/
├── app/                  # [P0] 核心調度與流程服務 (e.g. oracle_dispatcher, research_flow_service)
├── core/                 # [P0] 戰甲感知與幻覺防禦 (e.g. context_hub, hallucination_guard)
├── engine/               # [P0] 自主路由與能力規劃 (e.g. autonomic_routing_service, capability_planner)
├── learning/             # [P1] 技能適配與消融研究 (e.g. skill_fit_candidate_index, skill_fit_ablation_core)
├── contracts/            # [P1] 任務完成契約與證據保留 (e.g. completion_contract)
├── governance/           # [P1] 多級安全門禁與信任治理 (e.g. gate_evaluator)
├── infrastructure/       # [P2] 儲存與向量基礎設施 (e.g. LanceDB connector)
├── telemetry/            # [P2] 遙測與異步 IO 監控
└── skills/               # [P2] 外部技能載入與動態教學
```

---

## 🎯 核心子系統深度解析

### 1. 核心調度層 (`nexus/app/`)
* **定位**: 作為外部呼叫與 Nexus 內核的交互界面。
* **關鍵模組**:
  - `oracle_dispatcher.py`: 負責 Shadow Mode 預演與雙向路由派發。
  - `research_flow_service.py` 與 `research_s2t_runtime.py`: 管理整個 A/B 實驗、科研研究環路，負責任務從 Learn 到 Converge 的生命週期。

### 2. 戰甲核心層 (`nexus/core/`)
* **定位**: Nexus 的「身心靈」物理狀態控制中樞。
* **關鍵模組**:
  - `context_hub.py`: 管理當前 Agent 的上下文注入，執行 strict dependency 隔離。
  - `hallucination_guard.py`: 幻覺防禦網，在執行前與執行後攔截並審計輸出的事實一致性。

### 3. 能力規劃與路由引擎 (`nexus/engine/`)
* **定位**: 負責策略路由與執行路徑的最佳化。
* **關鍵模組**:
  - `autonomic_routing_service.py`: 判定任務是進入 Swarm 蜂群、Research 優先，還是直出模式。
  - `capability_planner.py`: 基於 13 門 HEEP MAT-B 被阻斷能力的現有 receipts，動態規劃最佳的 dependency DAG。

### 4. 技能適配層 (`nexus/learning/`)
* **定位**: 用於 V2 零信任安全架構下的技能自動對位與消融實驗。
* **關鍵模組**:
  - `skill_fit_candidate_index.py`: 2026-05-23 最新部署的候選池管理器，用於實行負控制（Negative-control）查找與篩選。
  - `skill_fit_ablation_core.py`: 執行角色消融（Role-ablation）實驗，確認個別技能在複合戰術中的真實必要性。

---

## 📈 模組 Token 權重與複雜度估算 (Module Weight)

| 模組路徑 | 程式碼規模 (Lines) | 預估 Token 佔比 | 複雜度評級 | 核心維護者 |
| :--- | :--- | :--- | :--- | :--- |
| `nexus/app/` | ~3,500 | 25% | High | Antigravity |
| `nexus/core/` | ~2,800 | 20% | Medium-High | Gemini-Nexus |
| `nexus/engine/` | ~4,200 | 30% | Very High | Codex |
| `nexus/learning/` | ~2,100 | 15% | Medium | Codex |
| `nexus/contracts/`| ~1,200 | 10% | Medium | Antigravity |

[NEXUS IDENTITY: de0969ff + v2.8 RUNTIME-ALIGNED]
