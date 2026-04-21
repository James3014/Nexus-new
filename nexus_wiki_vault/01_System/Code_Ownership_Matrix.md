---
aliases: '[Ownership, Domain Control, Responsibilities]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: git-shortlog
status: sealed
tags: '[system, ownership, rbac, matrix]'
title: System - Code Ownership Matrix
---

# System - Code Ownership Matrix (v26 Hardened)

## One-sentence summary
本矩陣定義 Nexus 核心模組的物理擁有權、備援 Agent 與最高治理責任人。

## 👥 領域擁有權矩陣 (Ownership Matrix)

| Module Path (路徑) | Primary Owner | Backup Agent | Accountability (責任) |
| :--- | :--- | :--- | :--- |
| `nexus/core/` | **Antigravity** | Gemini-Nexus | 門禁誠信與 1-bit 邏輯。 |
| `nexus/services/` | **Codex** | Antigravity | 知識存儲與計費準確性。 |
| `nexus/experiments/`| **Gemini-Nexus**| Antigravity | POC 創新與 A/B 基準。 |
| `scripts/ops/` | **Antigravity** | Codex | 基礎設施穩定與 Wiki 對位。 |

## 🛡️ 決策主權 (Sovereignty)
- **Guardian (Antigravity)**: 具備 `ci_gate` 的最高阻斷權與合約封印權。
- **Innovator (Gemini-Nexus)**: 負責 MSA 與 Skill Forge 的演化路徑設計。
- **Oracle (Codex)**: 負責 `CritiqueEngine` 的美學標準與對話蒸餾規約。

---
**[Source: git shortlog -sne | HARDENED_V26]**
