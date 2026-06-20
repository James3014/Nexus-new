# Schema Versioning

## 版本政策

本專案管理兩套 schema：

1. **Public Schema** — 公開提供的 JSON Schema 定義，供外部驗證器使用
2. **Internal Schema** — Nexus 內部治理系統使用的 artifact 定義

## Schema 對照表

| 公開 schema 檔名 | 內部 artifact 名稱 | 狀態 |
|---|---|---|
| `researchreceipt.v1.json` | `researchreceipt.v1` | **Normative** — 穩定版本，正式公開 |
| `routedecisionreceipt.v1.json` | `routedecisionreceipt.v1` | **Normative** — 穩定版本，正式公開 |
| `patchinvocationboundary.v1.json` | `patchinvocationboundaryreceipt.v1` | **Normative** — 穩定版本，正式公開 |
| `autonomyobservationreceipt.v1.json` | `autonomyobservationreceipt.v1` | **Normative** — 穩定版本，正式公開 |
| `evidencebundle.v1.json` | `evidence_bundle.v1` | **Provisional** — 尚未獨立版本化，source-of-truth 仍為內部定義 |

## 狀態定義

### Normative
- 定義已穩定，不會在 minor version 間進行不兼容變更
- 公開的 JSON Schema 與內部定義一致
- 可被外部系統依賴

### Provisional
- 定義仍在演進中，可能發生不兼容變更
- source-of-truth 仍為內部定義，公開版本僅供參考
- 不建議外部系統依賴
- 未來獨立版本化後將升為 Normative

## Public vs Internal 邊界

1. Public schema 是內部治理 artifact 的**子集**
2. Public schema 不得引用或暴露 internal-only 欄位
3. Internal artifact 名稱中的 `.v1` 直接對應 public schema 的 `.v1.json`
4. 任何 internal artifact 若要升為 public，必須經過 RFC 審議流程

## 驗證結果欄位

所有 public schema 的驗證結果使用統一的 normative result schema：

```json
{
  "hashmatch": true,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": true,
  "errorcode": null
}
```

`isvalid` 欄位若存在，僅作為 derived convenience field：

```
isvalid = hashmatch && schemamatch && evidencecomplete
```

注意：`claimabilityconfirmed` 是獨立的 fail-closed 判斷面，不被包含在 `isvalid` 中。
