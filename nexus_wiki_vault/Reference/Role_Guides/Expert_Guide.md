---
aliases: '[Developer Guide, Core Hardening, Expert Rules]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
status: production
tags: '[role, expert, guide, developer]'
title: Role Guide - Expert Developer
---

# 專家開發者指南 (Expert Guide)

## 1. 職責與主權
專家級開發者負責 Nexus **Layer 3 (Architecture)** 與 **Layer 2 (Governance)** 的演化。您具備修改 `nexus/core/` 檔案的權限，但必須遵循以下鐵律：

## 🛡️ 核心修改鐵律 (Hard Laws)
- **1-bit Core 不可侵犯**: 嚴禁降低 `OneBitGate` 的基礎信心門檻 (0.5)。任何修改必須經過 Antigravity 物理簽署。
- **A/B 基準強制化**: 所有的性能優化必須檢附 `benchmark_ab.json`，且增益必須 > 5% 始可進入 Promotion。
- **零 Print()**: 嚴禁在核心路徑中使用 `print()`。所有遙測必須對齊 `logging.getLogger("nexus.core")`。

## ⚙️ 關鍵流程
1. **Sandbox Setup**: 執行 `nexus sandbox --expert` 初始化隔離環境。
2. **Refactor Alignment**: 修改後執行 `uv run scripts/ops/wiki_sync_check.py` 確保文碼對位。
3. **Formal Closeout**: 產出 v24.1-canonical 交付憑證。

---
Back to [[System Overview]]
