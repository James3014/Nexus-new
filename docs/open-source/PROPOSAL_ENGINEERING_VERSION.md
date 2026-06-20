---
title: Nexus Receipt Core — Engineering Implementation Version
version: v4
last_updated: 2026-06-16
tags:
  - open-source
  - engineering
  - CLI
  - rust
  - verification
---

# Nexus Receipt Core — 工程工具版提案

## 定位

**Tamper-evident AI execution receipts and claimability verification.**

給 DevOps / Platform Engineer 用的驗證工具。不關心 AI 怎麼推理，只驗證「輸出有沒有完整證據鏈、有沒有被篡改、能不能被公開聲稱」。

## 目標使用者

- 負責部署 AI agent 的 platform team
- 需要 audit trail 的 compliance engineer
- 想在 CI/CD pipeline 中加入 AI 輸出驗證的 DevOps

## 核心功能

### 1. CLI：`receipt verify`

```bash
# 基本驗證
receipt verify --input task_receipt.json

# 指定 schema 版本
receipt verify --input task_receipt.json --schema v2.1

# 嚴格模式（fail-closed）
receipt verify --input task_receipt.json --strict

# 輸出結構化報告
receipt verify --input task_receipt.json --format json > audit_report.json
```

**驗證項目（對齊現有 receipt 欄位）：**

| 欄位 | 說明 | 驗證內容 |
|------|------|----------|
| `hashmatch` | 哈希匹配 | SHA-256 是否一致 |
| `schemamatch` | Schema 匹配 | 是否符合公開 schema 定義 |
| `evidencecomplete` | 證據完整性 | required fields 是否存在 |
| `claimabilityconfirmed` | 可聲稱性 | 是否可以公開聲稱 |
| `errorcode` | 錯誤碼 | 驗證失敗時的具體錯誤 |

### 2. Library：Rust crate `nexus_receipt_core`

```rust
use nexus_receipt_core::{Receipt, Verifier, VerificationResult};

let receipt = Receipt::from_file("receipt.json")?;
let verifier = Verifier::strict();
let result = verifier.verify(&receipt)?;

match result {
    VerificationResult::Valid => println!("Receipt is valid"),
    VerificationResult::Invalid(errors) => {
        for err in errors {
            eprintln!("Failed: {}", err);
        }
    }
}
```

### 3. Python bindings（Phase 2 評估）

```python
import nexus_receipt

result = nexus_receipt.verify("receipt.json")
assert result.is_valid
assert result.is_claimable  # Can this be publicly claimed?
print(f"Evidence count: {len(result.evidence)}")
```

**注意：** MVP 只做 CLI，bindings 列為 optional。Python API 穩定性不保證直到 v1.0 release。

## 技術架構

```
┌─────────────────────────────────────────┐
│              Public API                 │
│  CLI (Rust binary)                      │
│  JSON Schema (any language)             │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         nexus_receipt_core (Rust)        │
│                                         │
│  ┌────────────┐  ┌──────────────────┐  │
│  │ Canonical   │  │ 5-Point          │  │
│  │ JSON Parser │  │ Integrity Check  │  │
│  └────────────┘  └──────────────────┘  │
│                                         │
│  ┌────────────┐  ┌──────────────────┐  │
│  │ SHA-256    │  │ Schema           │  │
│  │ Hasher     │  │ Validator        │  │
│  └────────────┘  └──────────────────┘  │
└─────────────────────────────────────────┘
```

## 不做的東西

- 不做策略推理（誰產生這個 receipt、為什麼產生）
- 不做模型推理（不關心 receipt 背後的 AI 是什麼）
- 不做訓練資料處理
- 不做 runtime decision（不決定要不要執行某個 action）
- 不做 FlowMachine（需額外 gate，見路線圖 Phase 1.5）

## 與 Nexus 的關係

- Receipt Core 是 Nexus 治理層的「證據驗證子系統」
- 可獨立採用，不依賴 Nexus 主專案
- Nexus 主專案負責產生 receipt，Receipt Core 負責驗證 receipt
- 任何非 Nexus 的 agent 系統也可以產生符合 schema 的 receipt 並用 Receipt Core 驗證

## 里程碑（修正版）

| 階段 | 內容 | 預計時間 |
|------|------|----------|
| M1 | Rust receipt_verifier + canonical JSON + SHA-256 | Week 1-2 |
| M2 | 5-point integrity check（hashmatch, schemamatch, evidencecomplete, claimabilityconfirmed, errorcode） | Week 3 |
| M3 | Public JSON Schema 定義 + 驗證 | Week 4 |
| M4 | CLI 完成 | Week 5 |
| M5 | 文件 + 示例 | Week 6 |
| M6 | Cross-language canonicalization test suite | Week 7-8 |
| M7 | Release gate 驗證（G1-G7） | Week 9-10 |

## 風險與緩解

| 風險 | 影響 | 緩解 | Gate |
|------|------|------|------|
| Python/Rust canonicalization mismatch | 驗證失效 | 先完成 mismatch report，建立 cross-language test suite | G1, G2 |
| Schema 頻繁變更 | 使用者困惑 | 版本化 schema，backward compatibility guarantee | G7 |
| 模擬數據混入 | 可信度受損 | 開源前徹底清除模擬 timestamp | G5 |
| FlowMachine 未驗證就公開 | 過渡錯誤不被檢測 | Shadow module 機制，FT1-FT5 gate | FT1-FT5 |
