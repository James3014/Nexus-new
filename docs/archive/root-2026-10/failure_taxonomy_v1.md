# 🧬 Nexus Failure Taxonomy V1

本文件定義了 Nexus 治理鏈中所有標準化錯誤類型，確保跨 Agent 審計與 RCA 語義對齊。

---

## 🔬 A. Research Phase (研究階段)
| Reason Code | 說明 | 攔截點 |
|---|---|---|
| `RESEARCH_CONTAMINATION` | 研究產物洩漏設計意圖（如建議如何修復） | `ContaminationGuard` |
| `MISSING_MASKED_BRIEF` | 未提供遮罩簡報，破壞隔離性 | `ResearchReceipt` |
| `FACTS_ONLY_VIOLATION` | 產物包含非事實性的推論或指令 | `ResearchReceipt` |

## 🧭 B. Route Phase (路由階段)
| Reason Code | 說明 | 攔截點 |
|---|---|---|
| `RATIONALE_MISSING` | 關鍵決策缺少可解釋性動機 | `RouteDecisionReceipt` |
| `INVALID_REASON_CODE` | 使用了未註冊的路由原因碼 | `RouteRationaleCode` |
| `GOVERNANCE_LOCK_VIOLATION` | 試圖繞過強制隔離或高風險鎖定 | `RouteDecisionAdapter` |

## 🧹 C. Pre-Patch Phase (補丁前置)
| Reason Code | 說明 | 攔截點 |
|---|---|---|
| `REFUSAL_DETECTED` | 模型道歉或明確拒絕執行任務 | `PatchInputClassifier` |
| `EMPTY_RESPONSE` | 模型回傳空內容或純空白 | `PatchInputClassifier` |
| `MISSING_PATCH_BODY` | 輸出缺少 Aider SEARCH/REPLACE 結構 | `PatchInputClassifier` |
| `UNSUPPORTED_FORMAT` | 補丁格式無法被 Sanitizer 正規化 | `PatchInputSanitizer` |

## 🛠️ D. Patch Phase (補丁執行)
| Reason Code | 說明 | 攔截點 |
|---|---|---|
| `SYNTAX_INVALID` | 補丁導致語法錯誤，未通過預檢 | `ast.parse` (Patcher) |
| `SEARCH_MISMATCH` | SEARCH 區塊無法在原始檔案中精確定位 | `Matcher` |
| `NAME_SANITY_ERROR` | 補丁引入了不合法的命名或符號衝突 | `NameSanityValidator` |

---
**NEXUS IDENTITY: 708b362ea + v3.0.9 RUNTIME-ALIGNED**
