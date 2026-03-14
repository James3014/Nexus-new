# Contributing to Nexus v7 | 貢獻指南 🤝

---

## 🧬 Skills Architecture | 技能架構 (v1.5.2)

**[EN]** Nexus v7 is built on a modular "Skills" architecture.
**[ZH]** Nexus v7 建立在模組化的「Skills (技能)」架構之上。

### Structure | 目錄結構
```
skills/
  your-skill-name/
    SKILL.md          # Agent instructions | 代理指令
    scripts/          # Logic implementation | 邏輯實作
    examples/         # Reference patterns | 參考模式
```

---

## 🛠️ Defining a Skill | 定義新技能

1.  **Instruction First | 指令優先**: Use Nexus semantic format in `SKILL.md`.
    *   使用 Nexus 語意格式在 `SKILL.md` 中定義。
2.  **Mechanized Verification | 機械驗證**: Add negative constraints to prevent hallucinations.
    *   加入負面約束，防止該領域常見的幻覺。
3.  **State Integration | 狀態整合**: Compliance with `P-D-X-R-A-C` state machine.
    *   確保輸出的 JSON Schema 符合 `P-D-X-R-A-C` 狀態機。

---

### 1. Skill Development | 技能開發與擴充 🧪
**[EN]** To add a new skill to Nexus, follow our **Smart Inventory** spec:
**[ZH]** 若要為 Nexus 新增技能，請遵循 **智慧清單 (Inventory)** 規範：

1.  **Define in `scripts/skills_inventory.json`**:
    - `phases`: Use `["P", "D", "R", "A", "C"]` or `["*"]`.
    - `triggers`: Keywords that trigger this skill (e.g., `performance`, `security`).
2.  **Logic Implementation**: Place your Python logic or CLI tool in `scripts/`.

**Example Inventory Entry | 清單範例**:
```json
"security-scanner": {
  "phases": ["A"],
  "langs": ["python", "javascript"],
  "triggers": ["vulnerability", "leak"],
  "description": "Scan for security leaks during Audit phase."
}
```

### 2. PR Standards | PR 提交標準

*   **Contract First | 契約優先**: All communication MUST use validated JSON schemas.
    *   所有通訊「必須」使用經過驗證的 JSON Schema。
*   **Traceability | 可追溯性**: Every action MUST be logged to `tracelog.jsonl`.
    *   每一項操作「必須」記錄至 `tracelog.jsonl`。
*   **Safety | 安全考量**: High-risk operations MUST be gated by the `Circuit Breaker`.
    *   高風險操作「必須」由 `Circuit Breaker (熔斷器)` 守衛。

---

## 🚀 Submission | 提交流程

1.  Fork the repository | Fork 本儲存庫。
2.  Create feature branch | 建立功能分支 (`nexus/feature/your-skill`)。
3.  Add unit tests | 添加單元測試。
4.  Submit PR | 提交 Pull Request。

---
**Building the future of AI engineering together. | 共同構建 AI 工程的未來。** 🫡🦾
