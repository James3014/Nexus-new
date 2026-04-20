# 🛠️ Skill Self-Assembly & JIT (Just-In-Time)

## 1. 技能自動組裝引擎
Nexus 不使用固定的功能集，而是根據任務動態載入技能。

## 2. 技術特性
- **JIT Loading**: 只有當任務需要時，技能模組才會被編譯並注入內存。
- **AST Validation**: 在技能執行前，自動進行抽象語法樹 (AST) 掃描，防止代碼注入。
- **Weight Learning**: 根據歷史執行成功率，動態調整技能的調度權重。

## 3. 技能合約 (Skill Contract)
每個技能必須具備：
1. **Schema**: 定義輸入/輸出。
2. **Gate**: 執行後的物理驗收邏輯。
3. **Evidence**: 強制產出 `tracelog`。

## 4. 技能交換 (Skill Exchange)
多個 Drone 之間可以共享技能執行的 Artifacts，實現協同進化。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Platform Core Registry.md]**
