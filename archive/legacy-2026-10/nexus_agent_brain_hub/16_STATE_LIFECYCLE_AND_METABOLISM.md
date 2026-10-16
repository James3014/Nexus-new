# 🔄 State Lifecycle & Metabolism
**[PHYSICAL_STATUS: METABOLIC_STABILITY | PYDANTIC_ENFORCED]**

## 1. 核心生存與狀態管理
Nexus 透過 `SessionMetabolism` 與 Pydantic 契約確保任務的長期穩定性與邏輯純度。

## ⚙️ 實體化代謝規約
- **狀態生命週期**: 從 `INIT` 到 `COMMITTED` 的 5 階段完整遷徙追蹤。
- **物理斷點 (Checkpoint)**: 支援任務意外中斷後的精準恢復，路徑：`.nexus/metabolism/task_stack.json`。
- **會話蒸餾 (Distill)**: 當 Token 使用量 > 85% 時，自動提煉 Trace 為 `session_seed.json`。
- **狀態修剪 (Pruning)**: `StateRepository` 自動執行歷史 Tail-Cut (100 條上限)，防止檔案無限膨脹。
- **美學硬門檻 (Aesthetic Gate)**: 產出代碼的 Critique Score 必須 >= 90，否則拋出 `AestheticViolation` 並阻斷。

## 2. Pydantic 契約約束
- **Runtime Validation**: 核心數據結構（如 `NexusState`）禁止未定義欄位注入，確保 API 契約穩定。

---
**[Source: Truth Realignment Audit Stage 5 - 2026-04-20]**
