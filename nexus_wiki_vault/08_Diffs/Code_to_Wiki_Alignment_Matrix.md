---
aliases:
- Alignment Verdict
- Wiki Health Matrix
confidence: high
last_compiled: '2026-05-06'
owner: agent
source_of_truth: 06_Ops/Ops - Wiki Drift Audit.md
status: hardened
tags:
- diff
- audit
- alignment
- health
title: Code to Wiki Alignment Matrix
type: audit
version_scope: v26
---

# Diff - Code to Wiki Alignment Matrix (v26 Hardened)

## One-sentence summary
紀錄代碼與 Wiki 之間的「誠信對位」現況，標註可直接落地與仍需演進的區塊。

## Role / responsibility
- 持續監測 Code 實作與對應 Wiki 的一致性。
- 將對位缺口轉為可追蹤的治理任務。

## Upstream
- `06_Ops/Ops - Wiki Drift Audit.md`
- `06_Ops/Ops - Truth Claims Register.md`

## Downstream
- `07_Compliance/Current_Compliance_Status.md`
- `06_Ops/Ops - Governance Changelog.md`

## Related modules / files
- `06_Ops/Ops - Wiki Drift Audit.md`
- `06_Ops/Ops - Wiki Page Type Contracts.md`
- `06_Ops/Ops - Closeout Hard Gate.md`

## Source notes
- 資訊基於對位與漂移稽核輸出彙整。[Source: 06_Ops/Ops - Wiki Drift Audit.md]

## Open questions / conflicts
- [ ] 如何區分「短期對齊技術債」與「架構層面缺口」？
- [ ] 對齊矩陣是否要增加「回歸概率」欄位以影響修復優先順序？

## 📊 對位狀態矩陣 (Alignment Matrix)

| Domain | Code Entity (代碼) | Wiki Doc (文檔) | Alignment (對位) | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **退出語義** | `exit_codes.py` | `Exit_Code_Registry.md` | 🟢 **100%** | **HARDENED** |
| **幻覺審計** | `hallucination_guard.py`| `Hallucination_Guard_Scoring_Spec.md` | 🟢 **100%** | **HARDENED** |
| **路由決策** | `router.py` | `Router_Decision_Flow.md` | 🟡 **90%** | **EVOLVING** |
| **結案契約** | `ci_gate.py` | `Closeout_Hard_Gate.md` | 🟢 **100%** | **HARDENED** |
| **機群通信** | `swarm.py` | `Swarm_MultiNode.md` | 🟡 **85%** | **EVOLVING** |
| **代碼擁有** | `git shortlog` | `Code_Ownership_Matrix.md` | 🟢 **100%** | **SEALED** |

## Link to System
[[System Overview]]
