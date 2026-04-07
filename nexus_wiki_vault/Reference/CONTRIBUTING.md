---
id: contributing
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
path: nexus_wiki_vault/06_Ops/Reference/CONTRIBUTING.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
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
# [[contributing]] to Nexus v9 Autonomic | 參與 Nexus v9 自主演進 🚀

**[EN]** Welcome! To ensure the highest quality in autonomous code evolution, please follow the Nexus **P-D-R-A-C** autonomic protocol.
**[ZH]** 歡迎！為確保自主代碼演進的最高品質，請遵循 Nexus **P-D-R-A-C** 自主協議。

## 🧬 P-D-R-A-C Protocol | P-D-R-A-C 協議

1.  **P (Plan)**: Define your [[task]]. Use specialized planners (`nexus-planner-expert`).
    **P (計畫)**: 定義任務，使用專業計畫職能 (`nexus-planner-expert`)。
2.  **D (Diagnose)**: Identify failure modes. Use `nexus-debug-expert` for deep RCA.
    **D (診斷)**: 識別失效模式，使用 `nexus-debug-expert` 執行深層根因分析 (RCA)。
3.  **R (Repair/Refine)**: Apply patches using the autonomic fallback chain.
    **R (修復/精煉)**: 透過自主備援鏈套用補丁，確保可靠性。
4.  **A (Audit/Analyze)**: Run `nexus:test --full-chain` and `FlashJudge 8.0` [[Validation|validation]].
    **A (審計/分析)**: 執行 `nexus:test --full-chain` 指令與 `FlashJudge 8.0` 驗證。
5.  **C (Crystallize/Commit)**: Use `nexus:crystal` to integrate the experience into the brain.
    **C (結晶/提交)**: 使用 `nexus:crystal` 將經驗整合至系統大腦。

## 🛡️ Guidelines | 開發指南

- **Autonomic Awareness**: Every execution generates a trace in `tracelog.jsonl`.
  **自主意識**: 每一次執行都會在 `tracelog.jsonl` 中留下軌跡，確保變更可追蹤。
- **[[SKILL]] Modularity**: New features should be registered in `skills_inventory.json`.
  **職能模組化**: 新功能應作為「技能 ([[SKILL]])」註冊至 `skills_inventory.json`。
- **Isolation**: Always use isolated environments for [[task]] execution.
  **隔離執行**: 始終使用隔離環境執行任務，防止副作用。
- **Resilience**: Design for failure. Always provide backup logic for critical paths.
  **韌性設計**: 為失敗而設計，始終為關鍵路徑提供備援邏輯。

## 🧪 How to Verify | 如何驗證

**[EN]** Run the full autonomic verification chain:
**[ZH]** 執行完整的自主驗證鏈：

```bash
python3 scripts/nexus_cli.py nexus:test --full-chain "Your implemented feature"
```

Happy Evolving! | 祝演進順利！ 🛡️💎🚀✨🚩


---
[[System Overview]]