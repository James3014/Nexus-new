# 7R pub-bug-004 Row-Level 證據總表

本報告為 Phase B 交付物，彙整 `pub-bug-004` 在標準續跑、自我修復與長超時等三類 bounded replay 中的實體遙測數據特徵，以物理寫死其阻塞原因。

---

## 📊 機器可讀證據矩陣引用 (Machine-Readable JSON Ref)
- **JSON Matrix Path**: [7R_pub_bug_004_evidence_matrix.json](file:///Users/jameschen/Workspace/nexus/.nexus/policy/7R_pub_bug_004_evidence_matrix.json)

---

## 🔍 Row-Level 證據矩陣 (Evidence Matrix)

| Replay Variant | Winner Source | Model Calls | Provider Tokens Measured | Delivery Status | Infrainvalid Reason | Route Policy Evidence | Expected Capability Evidence | Can Enter Audited Combine? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **standard replay** | `llm` (直連 API) | `True` | `False` | `verified` | `modelcallwithouttokens` | `🟢 Present` | `🟢 Present` | `🔴 No` (Tokenless) |
| **self-heal replay** | `local` (本地修復) | `False` | `False` | `blocked` | `modelrequiredlocaldeliveryblocked` | `🟢 Present` | `🔴 Missing` | `🔴 No` (Delivery Fail) |
| **longer-timeout replay** | `timeout fallback` | `True` | `False` | `partial` | `tokenless_timeout_fallback` | `🔴 Missing` | `🔴 Missing` | `🔴 No` (Timeout Abort) |

---

## 🔬 Telemetry 特徵與失敗分析

1. **Standard Replay 變體**：
   - *遙測表現*: 語意修補成功且 delivery 通過，但由於 sandbox 與 API gateway 阻斷，未能測得 provider 實體 tokens，被分類為 `modelcallwithouttokens`。
   - * combine 判定*: 拒絕聚合，維持 fail-closed。
2. **Self-Heal Replay 變體**：
   - *遙測表現*: 本地嘗試在無 model 協助下修復，但因缺乏 causality 引導， patches 無法通過 hidden pytest 的冪等性 (idempotency) 檢核，delivery 被阻斷。
   - * combine 判定*: 拒絕聚合，維持 fail-closed。
3. **Longer-Timeout Replay 變體**：
   - *遙測表現*: 延長 timeout 以獲取 API 反饋，但於 direct baseline seam 處觸發 repeated timeout，被 runner 物理 abort 以保護 denominator 帳務，僅留下 partial telemetry。
   - * combine 判定*: 拒絕聚合，維持 fail-closed。

---

## ⚖️ Machine Verdict 最終判定
- **Currently Non-Refillable (目前無法補救)**: `true`
- **Combine Eligible (是否具備聚合資格)**: `false` (維持 8R Blocked P0 Blocker 判定)

---
*Evidence Matrix Generated: 2026-05-29 (Phase B Complete)*
