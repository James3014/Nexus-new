# 🧱 Phase 3 Taskboard: Algebraic Reasoning Evidence Closure

## 📋 欄位擴充計畫 (Schema Extension)

| Artifact | 新增欄位 | 狀態 |
| :--- | :--- | :--- |
| `diagnosis.json` | `reasoning_mode`, `violated_invariants[]`, `failed_proof_obligations[]`, `counterexamples[]`, `derivation_ref` | [x] |
| `repairfinal.json` | `reasoning_mode`, `rewrite_trace[]`, `resolved_invariants[]`, `equivalence_claim`, `risk_delta` | [x] |
| `auditresult.json` | `reasoning_mode`, `formal_gate_passed`, `obligation_coverage_pct`, `audit_notes_formal[]` | [x] |

## 📅 執行任務清單 (Tasks)

- [x] **T3-1**: 更新 `state_contracts.py` 中的 `NexusDiagnosis` 模型。
- [x] **T3-2**: 更新 `state_contracts.py` 中的 `Repair` 模型（或對應類別）。
- [x] **T3-3**: 更新 `state_contracts.py` 中的 `AuditResult` 模型。
- [x] **T3-4**: 實作 `Derivation` 在全鏈路中的引用與嵌入邏輯。
- [x] **T3-5**: 執行 Sandbox 任務，產出 `plan → diagnosis → repair → audit → manifest` 全鏈 Artifact。
- [x] **T3-6**: 更新 `Manifest` 封裝邏輯，納入 `formal_gate_passed` 摘要。
- [x] **T3-7**: 補齊單元測試（包含「空 invariants」與「證明失效」路徑）。
- [x] **T3-8**: 對接 `lessonevents.jsonl`，實現 Formal Lesson 的自動寫回。

---
[NEXUS STATUS: Phase 3 IN-PROGRESS]

## 🧬 智慧路由整合長計劃 v2 (P1-P34)

### 🧱 Phase 1-10: 核心地基與收據系統
- [ ] **P1**: 凍結能力契約 (文件化 phase/依賴/evidence)
- [ ] **P2**: 抽 `CapabilityRegistry` (去 god object)
- [ ] **P3**: 抽 `CapabilitySignalSet` (統一輸入)
- [ ] **P4**: 抽 `CapabilityConstraints` (治理硬約束: MemPalace/Artifact/Claim)
- [ ] **P5**: 抽 `CapabilitySelector` (單一 truth source)
- [ ] **P6**: 加 `SkillSignalSet` (skill 變輔助訊號)
- [ ] **P7**: 加 `SkillSlot` (skill 變能力內操作手冊)
- [ ] **P8**: 加 `CapabilityExecutionPlan` (phase DAG、並行、依賴)
- [ ] **P9**: 加 `ExecutorControls` (plan 真控制執行)
- [ ] **P10**: 加 `CapabilityReceipt` (selected 不等於 active)

### 🔗 Phase 11-25: 五支柱串接與能力具現
- [ ] **P11**: 加 `SkillReceipt` (skill 價值證明)
- [ ] **P12**: 接 LanceDB/Memory (歷史相似案例回饋)
- [ ] **P13**: 接 Belief (信心驅動升降級)
- [ ] **P14**: 接 MemPalace (能力/Skill 越權審計)
- [ ] **P15**: 接 Artifact/Claim (抗幻覺硬門)
- [ ] **P16**: CodeIntel/JIT 接 selector (客觀 code risk 訊號)
- [ ] **P17**: Autoreason receipt (正式化候選評審)
- [ ] **P18**: DDTree receipt (推理加速證明)
- [ ] **P19**: Ultra Review receipt (高風險治理證明)
- [ ] **P20**: Swarm receipt (MSA 真蜂群證據)
- [ ] **P21**: Drone receipt (委派任務收據)
- [ ] **P22**: Nightshift receipt (長任務自癒追蹤)
- [ ] **P23**: RLM X-loop (Recursive Research)
- [ ] **P24**: RLM R-loop (Recursive Repair)
- [ ] **P25**: Dynamic replan (A-reject/Timeout/Low-Belief 觸發)

### 🧬 Phase 26-34: 進化閉環與基準報告
- [ ] **P26**: OutcomeMemory (能力效果寫回)
- [ ] **P27**: Rule lifecycle (治理規則自我更新)
- [ ] **P28**: Report 去語義 (ab_eval 只讀 receipt)
- [ ] **P29**: 舊 router facade (淘汰舊路由封裝)
- [ ] **P30**: `AutonomicRouter` 降級 (信號源化)
- [ ] **P31**: `research_flow_service` 瘦身
- [ ] **P32**: Nexus-only benchmark (12 題本機驗證)
- [ ] **P33**: Gemini smoke (3 題 A/B 對照)
- [ ] **P34**: Gemini full report (公開數據發佈)
