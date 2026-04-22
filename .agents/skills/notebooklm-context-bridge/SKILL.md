---
name: notebooklm-context-bridge
description: 🛡️ NotebookLM 語義橋接器。專門負責「跨筆記本辯證分析」與「原汁原味知識提取」。強制執行反腦補協議，確保 Agent 輸出基於原始文獻。
version: 2026.04.21
---

# NotebookLM Context Bridge

## 🎯 核心定位
- **Primary Job**: 在多個 NotebookLM 之間執行語義比對、衝突偵測與戰術合成。
- **反腦補協議**: 嚴禁 Agent 進行二創或過度修辭，回覆必須「引用原句」並標註出處。

<decision_boundary>
Use when:
- 涉及兩個不同領域（如：技術 vs 哲學）的對位審計。
- 用戶要求「不要你的解釋，直接給我原文」。
- 需要將 NotebookLM 的知識轉化為具體的物理指令。
</decision_boundary>

<workflow>
Step 1: ID Routing (載體定位)
- 動作: 明確識別任務涉及的 Notebook IDs。
- 指令: `notebooklm list` 獲取當前環境下的活躍載體。

Step 2: Dual-Query (雙向提問)
- 動作: 針對同一個議題，向不同載體發出「專屬視角提問」。
- 規約: 提問詞必須包含「請直接引用資料庫內容」、「禁止腦補」。

Step 3: Dialectical Synthesis (辯證合成)
- 動作: 建立「不同見解對照表」，陳列衝突點。
- 配套: 產出包含物理參數（A 筆記本）與執行心法（B 筆記本）的「戰術矩陣」。

Step 4: Truth Verification (真理核帳)
- 動作: 回讀生成的 Markdown 檔案，確保其與 NotebookLM 的原文邏輯 100% 吻合。
</workflow>

<output_contract>
- [Source Quote]: 原始引用文字。
- [Cross-Ref]: 跨本對位點。
- [Tactical Cmd]: 可操作的物理指令建議。
</output_contract>
