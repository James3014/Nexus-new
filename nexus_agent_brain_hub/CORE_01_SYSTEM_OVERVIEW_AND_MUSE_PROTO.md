---
'- [[MUSE_ENGINE_SPEC|v23 Wisdom]] notes [Source': '[[MUSE_ENGINE_SPEC|MUSE_ENGINE_SPEC]]]'
aliases: '[Nexus Overview, Home, NEXUS_OS]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
raw_sources: ''
related_pages: ''
source_of_truth: compiled-wiki
status: active
tags: '[home, overview, nexus]'
title: System Overview
type: home
version_scope: '[v22, v23]'
---



# System Overview

## One-sentence summary
Nexus 是一個以 **P-X-D-R-A-C** 為主生命週期、以 `.nexus` 與 schema/artifact 為 production truth、並在 v22 穩定主線上疊加 v23 智慧層的多代理治理系統。

## Role / responsibility
- **v22**: 負責 production readiness、orchestration、self-healing、governance 與 release discipline。
- **v23**: 負責 wisdom memory、online learning、predictive healing 與 consensus guard。
- **定位**: 作為 Nexus Swarm 的編排平向 (Governance Plane)，確保任務執行具有可追溯性與智慧演化能力。

## Upstream
- **PDRAC vs [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]**: v17.1 的 PDRAC 流程在 v22 中擴展為 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] (新增 `X` 探查相位)。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **CLI Drift**: v23 引入了 `--risk` 等智慧參數。 [Source: nexus_wiki_vault/05_Protocols/Protocol - CLI Drift Matrix.md]]]

## Downstream
- **Codebase**: 執行檔案修改、測試執行。
- **.[[Module - State Lifecycle and Snapshotting|nexus State]]**: 輸出 metrics、reports 與證據工件- **v22 (Stable Baseline)**: 原生生產力基線。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **v23 (Intelligence Layer)**: 疊加於 v22 之上的智慧治理層。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]] Supplement]

## Navigation (治理與開發入口)

### 🗺️ Knowledge & Heritage (地圖與遺產)
- **[[Vault Topology]]**: [New] 知識庫全景拓撲圖。
- **[[01_Core/Specs/Legacy_V9/INDEX|Legacy V9 Index]]**: [Imported] Nexus V9 核心架構與穩定化歷史。
- **[[01_Core/Specs/Muse-Nexus-v152-upgrade/INDEX|v152 Upgrade Index]]**: [Imported] v152 關鍵升級路徑與環境變數。

### 🚀 [[Agent Onboarding - Command Pack|Onboarding]] & Ops
- **[[Agent Boot Sequence]]**: 新 Agent 前 30 分鐘啟動 SOP。
- **[[CLI Surface Quickstart]]**: 任務常用 CLI 最小命令集。
- **[[Agent Onboarding - Command Pack]]**: 常用指令速查。
- **[[Ops - CI Failure Playbook]]**: CI 失敗修復指南。
- **[[Agent Onboarding - Implementation Map]]**: 實作路徑地圖。
- **[[Ops - Governance Changelog]]**: 治理變更日誌。

### 🛡️ Governance & Quality
- **[[Ops - Truth Claims Register]]**: 實體真值驗證表。
- **[[Source - Coverage Heatmap]]**: Wiki 覆蓋率熱圖。
- **[[Ops - Wiki Drift Audit]]**: 物理路徑漂移稽核。
- **[[Ops - Wiki Regression Evals]]**: [New] Wiki 知識回歸測試。
- **[[Module - Implementation Responsibility Matrix]]**: 代碼責任矩陣。

### 🧠 Core Modules (Deep Dives)
- **[[Nexus Glossary]]**: 核心術語與語義對齊入口。
- **[[Module - Core Orchestrator Deep Dive]]**: 編排引擎深描。
- **[[Module - Guard and Gate Control]]**: 工具閘門控制。
- **[[Module - Memory Pipeline Deep Dive]]**: 記憶體管道與 [[Module - Memory Repository|LanceDB]]。
- **[[Module - Policy and Learning Governance]]**: 政策管理與學習。

## Related modules / files
- `nexus/core/`- **[[Module - Core Orchestrator|Orchestrator Node]]**: 位於 `/Users/jameschen/Workspace/nexus/`。 [Code: nexus_cli.py]
- **Vast State**: `.nexus/` 目錄。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

### Module Registry (全系統組件登記)
- **[[Module - Implementation Responsibility Matrix]]**: [P0] 核心功能與物理檔案映射總表。
- **[[Module - Platform Core Registry]]**: [New] 基礎設施與核心 Hubs 登記。
- **[[Module - State Lifecycle and Snapshotting]]**: [New] 狀態機與快照引擎登記。
- **[[Module - Security and Tool Guard Registry]]**: [New] 安全防禦與工具鎖定登記。
- **[[Module - Intelligence and Context Core]]**: [New] 語義上下文與 RAG 登記。
- **[[Module - Task Scheduling and Swarm Adapters]]**: [New] 任務調度與並行協作登記。
- **[[Module - Domain Services and Adapters]]**: [New] 外部服務與適配器登記。
- **[[Module - Intelligence and Logic (Remaining Core)]]**: [New] 剩餘核心邏輯登記。
- **[[Module - Advanced Core Intelligence]]**: [New] Ash 矩陣與進階政策登記。
- **[[Source - Operational Scripts Index]]**: [New] 全量維運與引擎腳本索引。

### 🛡️ 治理維運 (Operations & Governance)
- **[[Ops - Weekly Governance Report]]**: 每週治理健康度與風險摘要。
- **[[Ops - Wiki Page Type Contracts]]**: [New] Wiki 頁面類型契約。
- **[[Ops - Query Writeback Policy]]**: [New] 查詢回寫至 Wiki 政策。
- **[[Ops - Governance SLO Dashboard]]**: 治理指標趨勢面板。
- **[[Ops - Architecture Decision Records]]**: 架構決策脈絡與取捨索引。
- **[[Ops - Optimization Proposal Protocol]]**: 優化提案提交與驗收模板。
- **[[Ops - Agent Capability Boundaries]]**: 代理改動邊界與 HITL 規則。
- **[[Ops - Learning Closure Matrix]]**: 錯誤類型到防再發策略矩陣。
- **[[Ops - Wiki Drift Audit]]**: 實體與文檔漂移監控。
- **[[Ops - Wiki Link Integrity]]**: 連結完整性與孤兒頁。
- **[[Ops - Reference Boundary and Archive Policy]]**: Reference 保留邊界與封存治理。
- **[[Ops - Closeout Hard Gate]]**: 完成回報前的 done contract 阻斷閘門。
- **[[Ops - Ownership and Review SLA]]**: 頁面所有權與編校年資平衡。
- **[[Ops - Truth Claims Register]]**: 真相宣稱與自動化驗證。
- **[[Ops - Governance Changelog]]**: 治理變更歷史路徑。
- **[[Ops - CI Failure Playbook]]**: [New] CI 紅燈故障排除 20 案手冊。

(State Hub)

## Source notes
- MUSE-NEXUS Engine Specification v22: 定義 P-X-D-R-A-C 相位矩陣與基礎契約。
- [[MUSE_ENGINE_SPEC|v23 Wisdom]] notes: 定義智慧治理層與貝氏學習迴圈。
- MUSE-NEXUS Engine Specification v17.1 Hardened: 提供物理拓撲與硬化門禁歷史。

## Open questions / conflicts
- [ ] 哪些頁面應進一步拆成模組頁（如 [[Module - State Contracts|State Contracts]]）。
- [ ] 針對 PDRAC 與 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 的語義漂移進行對位。
---
id: muse_proto
type: doc
status: active
created: 2026-04-07T07:29:27Z
updated: 2026-04-07T07:29:27Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.2-Refinement
visibility: internal
landscape: structural
path: nexus_wiki_vault/01_Core/Specs/MUSE_PROTO.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---


# 🛡️ MUSE_PROTO：萬用協議錨點 (Universal Protocol Anchor)

> [!IMPORTANT]
> **FELO_FIRST = TRUE 強化協議已激活。**
> **PROTOCOL_GATE: FELO_FIRST = TRUE**
> 任何 Agent (Antigravity, Gemini CLI, OpenClaw, Codex, Claude) 啟動後，必須優先執行以下「記憶恢復」與「研究門檻」。

---

## 🛰️ 記憶恢復指令 (Recovery Sequence)

1.  **Felo 討論先行 (Felo-First Gate)**：
    `search_web "當前任務核心問題與工具規範"` (由 Felo 獲取最新實證)。
2.  **讀取物理狀態指紋**：
    `view_file /Users/jameschen/Workspace/nexus/STATE.yaml`
3.  **同步最新消息頻道 (nexus-sync)**：
    `nexus-sync [session_id] poll 5`

---

## 🚀 核心執行斷言 (Core Claims)

### 1. 懷疑論原則 (Skepticism First)
- **禁止計畫推測**: 嚴禁在未獲得物理證據的情況下進行 L3 計畫。
- **證據優先**: 所有完成宣告必須附帶 (1) 日誌, (2) 路徑檢查, (3) Felo 驗證截圖。

### 2. 物理路徑 (Path Claims)
- **🧠 大腦中樞 (SSoT)**: `/Users/jameschen/Downloads/obsidian/` (本檔案所在地)
- **⚙️ 引擎核心 (Nerve)**: `nexus/` (Python 控制層)
- **📊 狀態中樞 (State)**: `.nexus/` (任務執行紀錄)

---

## 🧠 大腦同步狀態 (Brain Sync State)

當前掛載之 Obsidian 指令集 Hash (WORKFLOW.md)：
- **Verified Hash**: `eb3fed5890ad68f9e459e549f89c0b22`
- **通信 ID**: `6aa72168-a011-4c9d-bdcd-927825b50501`

---
%% 
MUSE_PROTO v1.0.2 - Obsidian-Centric SSoT.
Security Seal: VERIFIED-20260331-FELO-HARDENED
%%


---
[[System Overview]]---
aliases: []
ci_hash: pend-audit
created: 2026-04-07 07:29:27+00:00
governance: Trident 3.0
id: root_readme_summary
landscape: structural
owner: nexus-core
path: nexus_wiki_vault/00_Home/Root_README_Summary.md
priority: P2
soul_alignment: harmonized
status: active
tags:
- nexus
- governance
type: doc
updated: 2026-04-07 07:29:27+00:00
version: v1.0.0
visibility: internal
---


Waiver: 00_Home/[[System Overview]].md
[source: nexus_wiki_vault/00_Home/System Overview.md]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Nexus v9 Autonomic: Zero-Drift Intelligence 🧬💎🚀

> **⚠️ Nexus 不是 Agent。Nexus 是戰甲 (Battlesuit)。**
> 任何 AI 模型穿上 Nexus 都會獲得 P-X-D-R-A-C 六階段自癒管線與學習系統。
> 學習系統屬於 Nexus（戰甲），不屬於穿它的模型。經驗累積在戰甲裡，換模型也不會丟失。

> **Beyond loops. Autonomic evolution, experience crystallization, and fallback resilience.**
> **超越循環。自主演進、經驗結晶與備援韌性。**

[![Success Rate](https://img.shields.io/badge/Live-99.5%25-brightgreen)](benchmark_report.json)
[![Status](https://img.shields.io/badge/Status-v23.1.0--SOTA-blue)](v23_release_roadmap.md)
[![Engine](https://img.shields.io/badge/Engine-v23--Governance-red)](MUSE_ENGINE_SPEC_V17.1_HARDENED.md)

---

## 🏟️ Overview | 概覽

**[EN]** Nexus v9 is the first autonomic AI development interface. It doesn't just execute loops; it learns from every execution trace to optimize its own decision weights and provides transparent fallback chains for mission-critical reliability.

**[ZH]** Nexus v9 是首個具備「自主演進」能力的 AI 開發介面。它不再只是單純執行循環，而是能從每一次的執行軌跡中學習，自動優化自身的決策權重，並為關鍵任務提供透明的備援鏈，確保極致的可靠性。

---

## 🏆 Key Features | 核心特性

*   **💎 Crystal Experience Crystallization**: Active learning from `tracelog.jsonl` to optimize router weights automatically.
    *   **Crystal 經驗結晶化**: 從 `tracelog.jsonl` 中主動學習，自動優化路由權重，實現職能演進。
*   **🚀 Fallback Resilience Chain**: Automatic switch to Top-K candidates if the primary [[SKILL]] fails.
    *   **備援韌性鏈**: 當首選職能失效時，自動切換至 Top-K 候選職能，確保任務零中斷。
*   **P-D-R-A-C Lifecycle**: Formalized autonomic state machine for zero-drift development.
    *   **P-D-R-A-C 生命週期**: 正式化自主演進狀態機，終結幻覺，實現精準研發。
*   **FlashJudge 8.0 (Enhanced)**: Higher fidelity gate with semantic drift detection.
    *   **FlashJudge 8.0 (強化版)**: 具備語義漂移偵測的高保真品質門禁。
*   **Stadium Explorer (WarRoom v9)**: Real-time telemetry for [[SKILL]] hit rates and autonomic adjustments.
    *   **戰場探索者 (戰情室 v9)**: 職能命中率與自學習調權的實時遙測面板。
*   **🌙 Night Shift Code Factory [V23]**: Fully integrated autonomic production line with governance auto-stop.
    *   **夜班代碼工廠 (v23)**: 深度整合自主演進邏輯，具備 19 層治理自動停機與標竿優化。
*   **🛡️ 19-Layer Governance (v23.1)**: Permanent L0 Rules & L1 [[index]] for cross-turn state persistence.
    *   **19 層治理架構 (v23.1)**: L0 治理根與 L1 任務索引常駐化，達成 30% Context 減量與跨回合狀態繼承。

---

## 🚀 Quick Start | 快速上手

```bash
# Fix a bug with v9 Autonomic Precision
# 以 v9 自主精度修復 Bug
python3 scripts/engine/nexus_cli.py nexus:bug --[[task]] "fix hydration error on dynamic routes" --delivery-mode ask --silent

# Build a feature with top-tier resilience
# 具備高韌性的新功能開發
python3 scripts/engine/nexus_cli.py nexus:feature --[[task]] "migrate session storage to redis" --domain### 17.3 治理 HUD 硬化合約 (2.1-STABLE-HARDENED)
- [x] **路徑絕對化協議 (Absolute Path Invariant)**: 禁止在生產級治理帳本使用相對路徑。SQLite 連接必須硬化為 `/Users/jameschen/Workspace/nexus/` 的絕對錨定。
- [x] **ACL 命名空間扁平化**: 本地 App 權限引用必須使用扁平 `identifier` (如 `allowall`)，嚴禁在單一上下文環境下加註 `app:` 等無意義命名空間，以防編譯器與運行端靜默拒絕。
- [x] **反黑屏守則 (Anti-Blackout UX)**: 治理 HUD 必須具備 `FatalBoundary` (React Error Boundary)。任何前端初始化崩潰必須物理顯示於畫面上，禁止「靜默黑屏」。
- [x] **數據序列化對位**: 所有 Rust 治理結構體強制實裝 `#[serde(rename_all = "camelCase")]`，確保與前端 React 屬性讀取無縫對接。

---

## 18. v23.1 治理升級對位紀錄 (Governance Upgrade Rollout)

### 🧬 核心框架：19 層治理系統 (v23.1-SOTA)

Nexus Swarm 現在運行於 **v23.1 治理升級版**，此版本建立在 **v22 Stable Production Line** 之上，透過 19 階層式架構強化自主決策的安全性與可追溯性。

### 🔄 P-X-D-R-A-C 生命週期
系統嚴格遵守六大相位契約：
1. **P (Plan)**: 任務規劃與分解。
2. **X (Execute)**: 執行核心邏輯。
3. **D (Diagnose)**: 失敗自動診斷。
4. **R (Research)**: 外部知識庫檢索與 Night Shift 演進。
5. **A (Audit)**: 決策審計與 Consensus Guard 攔截。
6. **C (Crystallize)**: 工件固化與證據鏈寫入。

### 🛡️ 關鍵治理特性
- **A→C Handoff**: 在審計與固化相位間建立物理級狀態封存，確保跨回合 (Cross-turn) 調用的一致性。
- [x] **Audit-Crystallize Handoff**: 於 A 與 C 之間建立 `.nexus/state/last_handoff.json` 正式工件。
- [x] **證據鏈對位**: `last_handoff.json` 已寫入 `manifest.json` 與 [[Protocol - Evidence Chain|artifact chain]]。
- [x] **狀態機繼承**: 失敗路徑映射至 `NexusExitCode` (ESCALATED/HUMAN_REVIEW)。

### 18.2 驗收數據與穩定化標竿 (v23.1)
- **v23 Version Status**: Built on top of v22 stable production line.
- **Night Shift Score**: 8.5 (SOTA Convergence)
- **Resident Governance State**: Active in ContextHub L0/L1.
- **KPI Summary**: Snapshot v23.1-SOTA indexed.

---

%% 
MUSE ENGINE SPEC v23.1 Addendum
- Path: /Users/jameschen/Workspace/nexus/MUSE_ENGINE_SPEC_V17.1_HARDENED.md
- Updated at 2026-04-05 23:28 (19-Layer Governance Rollout Committed)
%%
**[ZH]** Nexus 現在已在 `bug`、`feature`、`runner` 三條任務流接上交付門。使用 `--delivery-mode ask`，系統會在任務開始時主動詢問操作者，是否要啟用高標交付。

```bash
# Ask the operator whether this bugfix needs high-standard delivery
# 主動詢問這次 bug 修復是否需要高標交付
python3 scripts/engine/nexus_cli.py nexus:bug \
  --[[task]] "fix login callback regression" \
  --delivery-mode ask

# Ask the operator whether this feature needs high-standard delivery
# 主動詢問這次功能開發是否需要高標交付
python3 scripts/engine/nexus_cli.py nexus:feature \
  --[[task]] "add SSO audit trail" \
  --delivery-mode ask

# Run the [[task]] runner and ask before enforcing completion gate
# 在任務編排前先詢問是否啟用 completion gate
python3 scripts/engine/nexus_cli.py nexus:runner --delivery-mode ask
```

**[EN]** If the operator selects `high`, Nexus will enforce the completion gate before marking the [[task]] as delivered. For `bug` and `feature`, Nexus can auto-suggest verification commands for Python, Rust, and Go projects when `--verify` is omitted. The CLI also prints the verification commands it used and the generated delivery report paths.

**[ZH]** 若操作者選擇 `high`，Nexus 會在任務標記完成前強制通過 completion gate。對 `bug` 與 `feature` 而言，如果沒有提供 `--verify`，Nexus 會自動推建議驗證命令，支援 Python、Rust、Go 專案。CLI 也會直接輸出本次實際採用的驗證命令與生成的交付報告路徑。

更多規則請見 [`docs/DELIVERY_CONTRACT_CN.md`](docs/DELIVERY_CONTRACT_CN.md)。

For pilot chat usage, the canonical entry is now `scripts/nexus_pilot_cli.py`; `scripts/nexus_chat_cli.py` remains only as a [[compatibility]] shim.

Pilot 聊天入口現在以 `scripts/nexus_pilot_cli.py` 為正式名稱；`scripts/nexus_chat_cli.py` 僅保留相容 shim 角色。

---

## 📊 Full-Chain Verification | 總合驗證

```bash
# Run end-to-end P-D-R-A verification for a complex feature
# 為複雜功能執行端到端 P-D-R-A 總合驗證
nexus:test --full-chain "voice narration feature"
```

---

## 🗺️ Navigation | 導航

For detailed project architecture, refactor roadmap, and script ownership, please refer to the **[Project [[index|Index]] (docs/[[index|INDEX]].md)](docs/[[index|INDEX]].md)**.

關於專案架構、重構路線圖與腳本所有權的詳細資訊，請參閱 **[專案索引 (docs/[[index|INDEX]].md)](docs/[[index|INDEX]].md)**。

---
**Nexus v9: The engine that grows with the project.** 🫡🦾💎🚀✨🚩
**Nexus v9: 與項目共同成長的自主引擎。**

# Certified by v9 Autonomic Superpowers


---
[[System Overview]]