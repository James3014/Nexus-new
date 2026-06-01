# 🛡️ LocalHeal Phase 4: Patch-Synthesis Hardening Program

## 🎯 核心目標
建立 Phase 4 (Targeted Edit) 的穩定補丁契約、量化觀測能力與受控優化決策路徑。優先解決 14B 模型的格式不穩與拒絕恢復問題。

## 📅 實作路線圖 (2026-06-01 ~ 2026-06-21)

### Milestone 1: Guardrail Hardening (防禦先行)
- [x] **T1**: Patcher Syntax Preflight (`ast.parse`) 實裝 + Focused Tests.
- [x] **T2**: PromptBuilder Strict Contract 契約收口 + Regression Tests.
- [x] **T3**: Refusal Recovery Directive 實作 + Refusal Fixtures.
- [x] **T4**: Patch Telemetry Schema 擴充 + Receipt Adapter 對齊.

### Milestone 2: Observation & Audit (先觀測再決策)
- [x] **T5**: 擴大內部審計探針組 (Internal Audit Probe Set)，維持 stop-layer 契約.
- [x] **T6**: 產出 Prompt/Refusal Telemetry (Observation-only) 審計報表.

### Milestone 3: Guarded Opt-In (受控放權)
- [x] **T7**: 撰寫 Guarded Opt-In Proposal 草案 (promotion effect: none).
- [x] **T8**: 完成小流量 Canary Checklist.

---

## 📈 成功標準 (Acceptance Criteria)
1. **防線完整**: `Syntax Preflight` 已實裝並通過測試，能 100% 攔截不合法 Python 語法。
2. **數據可得**: 已產出 `analyze_phase4_audit.py` 報表，成功歸類 `SEARCH_MISMATCH`, `SYNTAX_ERROR` 與 `REFUSAL`。
3. **隔離性**: 所有新功能與遙測均已封裝於 `observation-only` 區域。

[NEXUS STATUS: PHASE 4 HARDENING COMPLETED]
