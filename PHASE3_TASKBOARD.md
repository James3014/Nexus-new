# 🧱 Phase 3 Taskboard: Algebraic Reasoning Evidence Closure

## 📋 欄位擴充計畫 (Schema Extension)

| Artifact | 新增欄位 | 狀態 |
| :--- | :--- | :--- |
| `diagnosis.json` | `reasoning_mode`, `violated_invariants[]`, `failed_proof_obligations[]`, `counterexamples[]`, `derivation_ref` | [ ] |
| `repairfinal.json` | `reasoning_mode`, `rewrite_trace[]`, `resolved_invariants[]`, `equivalence_claim`, `risk_delta` | [ ] |
| `auditresult.json` | `reasoning_mode`, `formal_gate_passed`, `obligation_coverage_pct`, `audit_notes_formal[]` | [ ] |

## 📅 執行任務清單 (Tasks)

- [ ] **T3-1**: 更新 `state_contracts.py` 中的 `NexusDiagnosis` 模型。
- [ ] **T3-2**: 更新 `state_contracts.py` 中的 `Repair` 模型（或對應類別）。
- [ ] **T3-3**: 更新 `state_contracts.py` 中的 `AuditResult` 模型。
- [ ] **T3-4**: 實作 `Derivation` 在全鏈路中的引用與嵌入邏輯。
- [ ] **T3-5**: 執行 Sandbox 任務，產出 `plan → diagnosis → repair → audit → manifest` 全鏈 Artifact。
- [ ] **T3-6**: 更新 `Manifest` 封裝邏輯，納入 `formal_gate_passed` 摘要。
- [ ] **T3-7**: 補齊單元測試（包含「空 invariants」與「證明失效」路徑）。
- [ ] **T3-8**: 對接 `lessonevents.jsonl`，實現 Formal Lesson 的自動寫回。

---
[NEXUS STATUS: Phase 3 IN-PROGRESS]
