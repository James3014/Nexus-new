# ⚖️ Truth Validator & Physical Verdict
**[PHYSICAL_STATUS: APPLICATION_VALIDATED | NO_MOCK_ALLOWED]**

## 1. 物理應用層驗收
Nexus 拒絕「綠燈假象」。在結案前，系統必須確認物理服務與數據庫的真實狀態。

## ⚙️ 實體化驗收規約
- **實體 Ping (Endpoint Check)**: 
    - 實作於 `nexus/core/truth_validator.py`。
    - 使用 `curl` 真正呼叫應用端點（如 `localhost:8000`）。
- **數據庫真值 (DB Verdict)**: 
    - 透過 `pg_isready` 或對應驅動確認數據庫連接與 Schema 正確性。
- **Fail-Closed 判決**: 
    - 若物理 Ping 失敗，即便測試通過，系統仍判定為 `FAILED` 並阻斷 Promote。
- **隔離區推廣 (Promote)**: 
    - 只有通過物理真值驗收的補丁，才允許從影子環境晉升。

## 2. 物理實體
- **Validator**: `nexus/core/truth_validator.py`。
- **Verdict 插槽**: 整合於 `NexusPipeline` 的 Phase 6 (Closeout)。

---
**[Source: Truth Realignment Audit Stage 10 - 2026-04-20]**
