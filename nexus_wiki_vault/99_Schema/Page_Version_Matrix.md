---
aliases: '[Alignment Verdict, Page Health, Audit Matrix]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
source_of_truth: repo-root-refactor-audit
status: hardened
tags: '[governance, audit, health, matrix]'
title: 📊 Page_Version_Matrix (v32.6 Sealed)
---

# Page_Version_Matrix (v32.6 Hardened)

## 1. 全庫頁面健康度與重構對位矩陣

| Folder | Page Name | Status | Alignment | Source of Truth (Code) |
| :--- | :--- | :--- | :--- | :--- |
| `00_Home` | README_Product | `🌲 STABLE` | 🟢 100% | (External Marketing) |
| `01_System` | Exit Code Registry | `🌲 STABLE` | 🟢 100% | `nexus/core/exit_codes.py` |
| `01_System` | Relationship Graph | `🌲 STABLE` | 🟢 100% | (Architecture Baseline) |
| `02_Modules` | Core Orchestrator | `🌲 STABLE` | 🟢 100% | `nexus/engine/coordinator.py` |
| `02_Modules` | Advanced Intelligence| `🌲 STABLE` | 🟢 100% | `nexus/governance/capability_gate.py` |
| `05_Protocols`| CLI Full Params | `🌲 STABLE` | 🟢 100% | `scripts/engine/nexus_cli.py` |
| `06_Ops` | Evidence Bundle Fmt| `🌲 STABLE` | 🟢 100% | `nexus/governance/evidence_guard.py` |
| `07_Compliance`| HI Scoring Spec | `🌲 STABLE` | 🟢 100% | `nexus/governance/hallucination_guard.py` |

## 2. 歷史重大重構紀錄 (Refactor Log)
- **v32.6**: 全面對位 `nexus/governance/` 與 `nexus/events/` 的物理目錄位移。
- **v32.1**: 修正核心主循環至 `nexus/engine/`。

---
**[NEXUS QUALITY SYSTEM: AUDIT_SEALED_V32.6]**
