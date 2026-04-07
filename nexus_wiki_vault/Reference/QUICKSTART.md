---
id: [[quickstart|quickstart]]
type: doc
status: active
created: 2026-04-07T07:29:29Z
updated: 2026-04-07T07:29:29Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/[[quickstart|QUICKSTART]].md
---
Waiver: 00_Home/[System Overview](../00_Home/System Overview.md).md
[source: 00_Home/[System Overview](../00_Home/System Overview.md).md]
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
# Nexus v9 Autonomic: Quick Start Guide | 快速上手指南 ⚡

---

## 1. Installation | 安裝

**[EN]** Nexus v9 requires Python 3.9+ and valid LLM [[api|API]] keys.
**[ZH]** Nexus v9 需要 Python 3.9+ 以及有效的 LLM [[api|API]] 金鑰。

```bash
# Clone the repository | 複製儲存庫
git clone https://github.com/nexus-ai/nexus-v9.git
cd nexus-v9

# Install dependencies | 安裝依賴
pip install -r requirements.txt

# Set up environment | 設定環境變數
export OPENAI_API_KEY="your_api_key"
export GOOGLE_API_KEY="your_gemini_key"
```

---

## 2. Autonomic Intelligence | 自主智慧

**[EN]** Nexus v9 introduces the **Crystal Analyzer**. After running some tasks, trigger a learning cycle to optimize routing weights.
**[ZH]** Nexus v9 引入了 **Crystal 分析器**。在執行一些任務後，啟動學習循環以優化路由權重。

```bash
# Analyze tracelogs and crystallize experience
# 分析執行日誌並結晶經驗
python3 scripts/nexus_cli.py nexus:crystal
```

---

## 3. Full-Chain [[Validation|Validation]] | 總合驗證

**[EN]** Use `--full-chain` to run a complete P-D-R-A cycle with integrated fallback support.
**[ZH]** 使用 `--full-chain` 執行完整的 P-D-R-A 循環，內建備援支援。

```bash
# Verify a feature end-to-end with fallback protection
# 具備備援保護的端到端功能驗證
python3 scripts/nexus_cli.py nexus:test --full-chain "voice narration UI"
```

---

## 4. Skills & Resilience | 職能與韌性 🧠🚀

**[EN]** Nexus v9 automatically routes to the best [[SKILL]] and provides **Fallback Resilience** if the primary [[SKILL]] fails.
**[ZH]** Nexus v9 自動路由至最佳職能，並在首選職能失效時提供**備援韌性**。

```bash
# Example: Fallback Chain in action
# 範例：備援鏈運作中
python3 scripts/nexus_cli.py nexus:feature --[task](task.md) "optimize database indexes" --bypass-cb
```
**[EN]** Observe the `🛡️ [v9 Override]` or `🎯 [SkillsRouter]` logs to see autonomic decisions.
**[ZH]** 觀察 `🛡️ [v9 Override]` 或 `🎯 [SkillsRouter]` 日誌，查看自主決策過程。

---

## 5. WarRoom v9 Telemetry | 戰情室遙測

**[EN]** Real-time monitoring of [[SKILL]] hit rates and performance metrics.
**[ZH]** 即時監控職能命中率與效能指標。

```bash
python3 scripts/nexus_cli.py nexus:warroom
```

---
**Build Smarter. Evolve Faster.** 🫡🦾💎🚀✨🚩


---
[System Overview](../00_Home/System Overview.md)