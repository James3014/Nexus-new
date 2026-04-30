---
aliases:
- Artifact Chain
- SSoT Flow
- Delivery Receipt
confidence: high
last_compiled: 2026-04-30
owner: agent
related_pages:
- '[Evidence Map](Protocol - Evidence Map.md)'
- '[System Overview](../00_Home/System Overview.md)'
source_of_truth: nexus/delivery/receipt.py
status: active
tags:
- protocol
- evidence
- chain
- manifest
- receipt
title: Protocol - Evidence Chain
type: protocol
version_scope:
- v24.1
- v26
---

# Protocol - Evidence Chain (v24.1-canonical)

## One-sentence summary
本頁定義 Nexus v26 標準證據鏈與 **v24.1-canonical 交付收據** 的物理檢查規範。 [Source: nexus/delivery/receipt.py]

## Role / responsibility
- **鏈式追蹤**: 確保 `manifest.json` 完整包含單次任務的所有子工件。
- **誠信校驗**: 透過 8 點物理檢查確保交付物之真實性。
- **證據封印**: 產出不可竄改的 `receipt.json` 作為晉升憑證。
- **斷言驗證 (Claim Verification)**: 將主觀的完成聲明 (Claim) 轉化為由物理證據支撐的物理事實，杜絕敘事幻覺。

## 📜 v24.1 交付收據規格 (Delivery Receipt)
所有任務結案前必須產出 `receipt.json`，並通過以下 8 大誠信檢查（8-Point Integrity Check）：

| 檢查項 | 物理意義 | 實作工具 |
| :--- | :--- | :--- |
| **Integrity** | 檔案完整性與雜湊校驗 | `sha256` |
| **Anti-Drift** | 防止治理規約漂移 | `verify_governance_seal.py` |
| **Lineage** | 血緣追蹤，確保工件因果鏈完整 | `verify_lineage_chain.py` |
| **Verifier** | 證據驗證器，檢查檔案狀態 | `evidence_verifier.py` |
| **Tests** | 單元與集成測試驗證 | `pytest` |
| **Regression** | 迴歸診斷，確保無功能倒退 | `diagnose_regression.py` |
| **Report Integrity** | 報告斷言與物理事實對位 | `verify_report_claims.py` |
| **Acceptance** | 最終驗收門檻檢查 | `acceptance-check` |

## 🔗 鏈式封印邏輯
1. **Artifact Generation**: 每個 Phase 產出的工件必須立即寫入 `.nexus/artifacts/`。
2. **Manifest Binding**: `manifest.json` 必須包含所有工件的 SHA256 摘要。
3. **Receipt Sealing**: 結算時產出 `receipt.json`，對整個 Manifest 進行最終封印。
4. **Arweave Distillation**: 關鍵證據將被蒸餾並獲取永久 TX ID。

## 🛡️ 異常處理
- **Receipt Missing**: 任務被標記為 `UNVERIFIED`，禁止晉升至生產分支。
- **Check Failure**: 任何一項檢查項失敗，`delivery_gate_passed` 即為 `False`，觸發 `fail-closed` 邏輯。

---
[System Overview](../00_Home/System Overview.md)
