# RFC-2026-05-05: GAN 驅動的 Autoreason 服務進化方案 (v2.1 Hardened)

## 1. 願景與動機
目前 `autoreason_service.py` 依賴機械式的「啟發式指標」，容易被「敘事幻覺」誤導。本計畫引入 **GAN (生成對抗網絡)** 邏輯，並針對博弈中發現的「預算黑洞」與「幽靈成功」進行架構硬化，實現具備物理嚴謹性與人類主權的安全推理。

---

## 2. 核心架構進化 (Architecture v2.1)

### A. 判別器與防禦生成 (GAN Core)
- **判別器 (The Discriminator)**：專門偵測候選方案的「致命缺陷」（競態、內存、API 破壞）。
- **防禦性合成 (Adversarial Synthesis)**：`Candidate AB` 必須正面回應並修復判別器指出的所有攻擊點。
- **語義 Borda 投票**：引入 LLM 盲評，判別器標記為「致命」的方案將被一票否決。

### B. 真理掛鉤 (Truth Hook) - 消滅幽靈成功
- **機制**：Wiki 更新與 `asi_ledger` 證據綁定。
- **約束**：若 Git Commit 中包含 Wiki 變更，但缺乏物理證據 ID，`Pre-commit Guard` 應自動阻斷。

### C. 預算熔斷門禁 (Budget Gate) - 算力保護
- **機制**：啟動前進行 Token 估算。
- **策略**：
    - 若連續兩輪投票 A 勝（A-Streak），立即熔斷。
    - 若單次任務預算消耗超過 50%，強制降級至 Standard 模式。

### D. 人類神諭協議 (Supreme Oracle Protocol) - 主權防線
- **機制**：當 Borda 證據與人類意志衝突時，人類可執行 `Override`。
- **學習閉環**：人類介入必須附帶 `Override_Reason`，該理由將作為物理約束寫入 **ASI 全域記憶**，防止後續任務重複衝突。

---

## 3. 詳細實作路徑

### Step 1: 數據模型擴展
修改 `AutoreasonCandidate` 與 `ASIRecord`，加入 `critiques`、`defenses` 與 `budget_spent` 欄位。

### Step 2: 注入對抗性邏輯
實作 `AutoreasonService.run_adversarial_cycle()`，協調判別器與生成器的多輪博弈。

### Step 3: 實作神諭接口
在 `pipeline.py` 的 Gate 階段加入 `OracleInterceptor`，支援結構化理由注入。

---

## 4. 驗收與證據
- **Log**: 顯示 `[ORACLE] Human override detected. Reason ingested into ASI.`
- **Guard**: 嘗試 Commit 無證據的 Wiki 變更應被拒絕。
- **Budget**: 報告中應顯示 `[BUDGET] Hitting 50% limit, downshifting to standard.`
