---
aliases: '[Alignment Verdict, Page Health, Audit Matrix]'
confidence: high
last_audit: '2026-04-21 21:00'
last_compiled: '2026-04-21'
owner: agent
source_of_truth: repo-root-mesh-audit
status: hardened
tags: '[governance, audit, health, matrix, mesh]'
title: 📊 Page_Version_Matrix (v32.7 Sealed)
---

# Page_Version_Matrix (v32.7 Hardened)

## 1. 全庫頁面健康度與服務網格對位矩陣

| Folder | Page Name | Status | Alignment | Source of Truth (Code) |
| :--- | :--- | :--- | :--- | :--- |
| `00_Home` | README_Product | `🌲 STABLE` | 🟢 100% | (External Marketing) |
| `01_System` | Exit Code Registry | `🌲 STABLE` | 🟢 100% | `nexus/core/exit_codes.py` |
| `02_Modules` | Core Orchestrator | `🌲 STABLE` | 🟢 100% | `nexus/engine/coordinator.py` |
| `02_Modules` | Engine Services | `🌲 STABLE` | 🟢 100% | `nexus/engine/bootstrap.py` |
| `02_Modules` | Router Decision Flow| `🌿 EVOLVING`| 🟡 90% | `nexus/engine/autonomic_routing_service.py` |
| `06_Ops` | Evidence Bundle Fmt| `🌲 STABLE` | 🟢 100% | `nexus/governance/evidence_guard.py` |
| `07_Compliance`| HI Scoring Spec | `🌲 STABLE` | 🟢 100% | `nexus/governance/hallucination_guard.py` |
| `07_Compliance`| Capability Gate | `🌲 STABLE` | 🟢 100% | `nexus/governance/capability_gate.py` |

## 2. 歷史重大重構紀錄 (Refactor Log)
- **v32.7**: 實施 **Service Mesh (服務網格)** 重構，將引擎與學習模組拆解為 20+ 個微型服務。
- **v32.6**: 全面對位 `nexus/governance/` 與 `nexus/events/` 的物理目錄位移。

---
**[NEXUS QUALITY SYSTEM: AUDIT_SEALED_V32.7]**
