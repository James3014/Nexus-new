# nexus-receipt-core

Verify AI execution receipts for integrity, completeness, and safe public use.

`nexus-receipt-core` 是一個用來驗證 AI 執行紀錄的工具。它可以檢查一份 receipt 是否被篡改、格式是否正確、證據是否齊全，以及是否應該被 fail-closed。

## 功能

- 驗證 receipt 內容是否被修改
- 驗證 receipt 是否符合預期 schema
- 檢查必要 evidence 是否存在
- 輸出明確的 fail-closed 驗證結果

## 不包含

本專案不處理：

- 任務路由
- 能力規劃
- 政策判斷
- 模型推理
- 訓練資料匯出
- 私有 benchmark 資料

這些部分仍屬於 Nexus 主系統內部。

## 安裝

```bash
cargo build
```

## 使用

```bash
# 完整驗證（預設）
cargo run -- verify ./receipt.json

# 跳過 hash 檢查（僅檢查 schema + evidence）
cargo run -- verify ./receipt.json --skip-hash
```

## 驗證結果欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `hashmatch` | `Option<bool>` | Hash 驗證結果。`Some(true)` = 通過、`Some(false)` = 未通過、`None` = 未檢查 |
| `schemamatch` | `bool` | Schema 是否符合 |
| `evidencecomplete` | `bool` | Evidence 是否齊全 |
| `claimabilityconfirmed` | `bool` | 最終判定：僅當所有檢查都通過時為 `true` |
| `errorcode` | `Option<String>` | 第一個失敗的檢查。值域：`hash_mismatch`、`hash_not_checked`、`schema_mismatch`、`evidence_incomplete`、`parse_error`。`null` 表示驗證通過。 |

### `hashmatch` 三態語意

```
Some(true)  → 已檢查，通過
Some(false) → 已檢查，未通過
None        → 未檢查（例如 --skip-hash 或 parse 失敗）
```

`claimabilityconfirmed` 只有在 `hashmatch == Some(true)` 且其他檢查都通過時才為 `true`。  
`hashmatch == None` 絕不會被視為通過。

## 範例輸出

### 驗證通過

```json
{
  "hashmatch": true,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": true,
  "errorcode": null
}
```

### Hash 不匹配

```json
{
  "hashmatch": false,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": false,
  "errorcode": "hash_mismatch"
}
```

### 跳過 Hash 檢查

```json
{
  "hashmatch": null,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": false,
  "errorcode": "hash_not_checked"
}
```

## 這個專案適合誰

你可能會用到它，如果你想：

- 驗證 AI workflow 的輸出紀錄
- 建立可防篡改的 execution log
- 在公開結果前先確認證據是否完整
- 把「驗證」從 agent 決策邏輯中拆出來獨立處理

## 設計原則

- **Tamper-evident**：內容被改過就應該驗不過
- **Fail-closed**：證據不足時不能模糊放行
- **Verifier-first**：只做驗證，不做策略

## 專案定位

`nexus-receipt-core` 不是完整的 Nexus 開源版。它是一個小而清楚的核心元件：AI execution receipt verifier。

## 文件

- [RFC.md](./RFC.md) — 完整設計論述與邊界
- [SCHEMA_VERSIONING.md](./SCHEMA_VERSIONING.md) — Schema 版本策略與 public/internal 對照
- [RESULT_SCHEMA.md](./RESULT_SCHEMA.md) — 驗證結果欄位定義與 fail-closed 規則
- [INSTALL.md](./INSTALL.md) — 安裝與排錯指南
