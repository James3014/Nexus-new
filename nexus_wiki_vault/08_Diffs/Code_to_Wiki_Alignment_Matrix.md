---
aliases: '[Alignment Verdict, Wiki Health Matrix]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: code-audit-20260420
status: hardened
tags: '[diff, audit, alignment, health]'
title: Diff - Code to Wiki Alignment Matrix
---

# Diff - Code to Wiki Alignment Matrix (v26 Hardened)

## One-sentence summary
本矩陣紀錄 Nexus 代碼實體與 Wiki 文檔之間的「誠信對位」現狀，標註已硬化與尚在演進中的區塊。

## 📊 對位狀態矩陣 (Alignment Matrix)

| Domain | Code Entity (代碼) | Wiki Doc (文檔) | Alignment (對位) | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **退出語義** | `exit_codes.py` | `Exit_Code_Registry.md` | 🟢 **100%** | **HARDENED** |
| **幻覺審計** | `hallucination_guard.py`| `Hallucination_Guard_Scoring_Spec.md` | 🟢 **100%** | **HARDENED** |
| **路由決策** | `router.py` | `Router_Decision_Flow.md` | 🟡 **90%** | **EVOLVING** |
| **結案契約** | `ci_gate.py` | `Closeout_Hard_Gate.md` | 🟢 **100%** | **HARDENED** |
| **機群通信** | `swarm.py` | `Swarm_MultiNode.md` | 🌿 **85%** | **EVOLVING** |
| **代碼擁有** | `git shortlog` | `Code_Ownership_Matrix.md` | 🟢 **100%** | **SEALED** |

## 🛡️ 實體驗證週期
- **自動化**: 每次 `ci_gate` 執行時，`wiki_sync_check.py` 會自動刷新本矩陣的部分信心度指標。
- **手動審計**: 每月由 Antigravity 進行一次全量地毯式對位校準。

---
**[NEXUS AUDIT: ALIGNMENT_VERIFIED_V26]**
