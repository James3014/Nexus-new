# 📖 System Overview & Glossary (v32.6)
**[PHYSICAL_STATUS: REFACTOR_ALIGNED | LAYER_1_FOUNDATION]**

## 1. 系統架構變革 (2026-04-21)
Nexus 已完成核心重構，實現了 **Engine (執行)**、**Governance (治理)** 與 **Events (事件)** 的深度解耦。

## 2. 術語表 (Glossary)
- **AAAK**: 30x 語義提煉方言。
- **1-bit Core**: 原子化決策判決核心。
- **Events Backbone**: 由 `nexus/events/` 驅動，取代舊版單體 `event_bus.py`。
- **Capability Gate**: 物理層級的階段性工具隔離機制。

## 3. 🛑 核心錯誤碼 (SSOT)
| Code | Label | Semantics | Source (Code) |
|---|---|---|---|
| **0** | SUCCESS | 任務完成，證據完整。 | `exit_codes.py` |
| **1** | FAILED | 修復失敗，無須升級。 | `exit_codes.py` |
| **2** | ESCALATED | 需重啟 CampaignGeneral。| `exit_codes.py` |
| **3** | HUMAN_REVIEW | 治理違規，人工介入。 | `exit_codes.py` |

---
**[Source: nexus/core/exit_codes.py | REFACTOR_READY]**
