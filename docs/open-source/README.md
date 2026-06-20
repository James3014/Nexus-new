# nexus-receipt-core

**Tamper-evident AI execution receipts and claimability verification.**

## 概述

`nexus-receipt-core` 提供一套輕量、獨立的驗證工具，用來確認 AI 系統產生的執行紀錄（receipt）是否：

- 未被篡改
- 結構符合公開規範
- 證據齊備
- 達到可公開聲稱的最低門檻

它**不是**一套完整的 AI 治理系統，也不包含路由、規劃、策略決策等功能。它只做一件事：**驗證**。

## 快速開始

### 安裝

```bash
cargo install nexus-receipt-core
```

### 驗證一份 receipt

```bash
receipt verify path/to/receipt.json --strict
```

輸出範例：

```json
{
  "hashmatch": true,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": true,
  "errorcode": null
}
```

### 驗證一份被篡改的 receipt

```bash
receipt verify tampered-receipt.json --strict
```

輸出範例：

```json
{
  "hashmatch": false,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": false,
  "errorcode": "HASH_MISMATCH"
}
```

## 支援的 Schema

| Schema | 用途 |
|--------|------|
| `researchreceipt.v1` | 研究執行紀錄 |
| `routedecisionreceipt.v1` | 路由決策紀錄 |
| `patchinvocationboundary.v1` | 程式碼修改邊界紀錄 |
| `autonomyobservationreceipt.v1` | 自主性觀察紀錄 |
| `evidencebundle.v1` | 證據彙整（provisional） |

詳細 schema 說明請見 [SCHEMA_VERSIONING.md](./SCHEMA_VERSIONING.md)。

## 非目標

以下內容**不在**本專案範圍內：

- 路由選擇（routing）
- 能力規劃（capability planning）
- 策略引擎（policy engine）
- 模型推論（model inference）
- 公開聲稱生成（public claim generation）
- 訓練資料與 benchmark

如需這些功能，請使用 Nexus 主系統。

## 與 Nexus 的關係

`nexus-receipt-core` 是 Nexus 的開源子專案，但它是一個**有意識地收斂範圍**的版本：

- **Nexus 內部**：包含完整的 agent runtime、router、planner、policy engine、3B student model
- **nexus-receipt-core**：只提取其中的 verifiable 部分——receipt 驗證與證據完整性檢查

換句話說，nexus-receipt-core 提供的是 Nexus 中「任何人都能獨立驗證」的那一部分。

## 授權

[待補充]

## 貢獻

歡迎提出 issue 與 PR。請先閱讀 [RFC.md](./RFC.md) 了解專案範圍與設計原則。
