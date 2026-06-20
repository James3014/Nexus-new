---
title: RFC：nexus-receipt-core
status: draft
authors:
  - Nexus
created: 2026-06-16
updated: 2026-06-16
version: v1
tags:
  - rust
  - receipt
  - evidence
  - verification
  - open-source
---

# RFC：nexus-receipt-core

## 摘要

`nexus-receipt-core` 是一個以 verifier-first 為核心的開源子專案，目標是提供「可防篡改的 AI 執行 receipt 與 claimability 驗證能力」。

它的公開範圍刻意保持狹窄，只包含：
- canonicalization
- hash integrity verification
- schema compliance
- evidence completeness
- fail-closed result emission

它**不是** Nexus 全套治理系統的開源版，也**不包含** routing、policy、capability planning、student model runtime 等策略層。

## 背景與動機

目前 Nexus 已有較強證據基礎的部分，是 deterministic verification primitives，特別是 receipt verification、evidence integrity 與 fail-closed 驗證這條線；相對地，strategic routing、capability planning、budget policy 與 public claim gate 仍被明確保留在 Python 端，需等待更多 shadow evidence 後才適合進一步外部化。

這代表最合理的第一個開源邊界，不應是整套 agent runtime，而應是一個：
1. 可獨立使用，
2. 可驗證，
3. 不暴露 Nexus 核心策略差異化，

的證據驗證核心。

## 目標

本 RFC 提議建立 `nexus-receipt-core`，作為 Nexus 第一個公開開源子專案，提供：

- receipt canonicalization
- receipt hash 驗證
- public schema 驗證
- required evidence completeness 檢查
- claimability 的 fail-closed 驗證輸出

這個專案應能讓其他團隊**不依賴 Nexus 主系統**，也能驗證某份 AI 執行紀錄是否：
- 被篡改，
- 結構合法，
- 證據齊備，
- 達到可公開聲稱的最低門檻。

## 非目標

本 RFC **不**提議開源以下內容：

- `autonomicrouter.py`
- `capabilityplanner.py`
- routing heuristics
- policy engine
- 3B student runtime logic
- 訓練資料與 training export pipeline
- benchmark rows
- command outputs
- private identifiers
- hidden chain-of-thought

原因很直接：現有文件仍將 router 與 planner 保留在 Python，3B student 的 adoption 仍受 trust mismatch、held-out evaluation、redaction discipline 與 shadow gate 約束，因此這些區塊不適合列入第一波開源範圍。

## Phase 1 公開範圍

Phase 1 的公開範圍只包含以下五件事：

1. **Canonicalization** — 對 receipt JSON 做一致化正規化處理
2. **Hash integrity verification** — 驗證 receipt 的 canonical hash 是否匹配
3. **Schema compliance** — 驗證 receipt 是否符合公開 schema
4. **Evidence completeness** — 檢查 required evidence fields 是否齊全
5. **Fail-closed result emission** — 一旦驗證失敗，必須回傳明確錯誤結果，不可 silent pass

這個範圍故意避開 routing、planning、推理與決策面，只做驗證，不做策略。

## 倉庫結構

```text
nexus-receipt-core/
├── rust/
│   ├── receipt_verifier/
│   └── Cargo.toml
├── schemas/
│   ├── researchreceipt.v1.json
│   ├── routedecisionreceipt.v1.json
│   ├── patchinvocationboundary.v1.json
│   ├── autonomyobservationreceipt.v1.json
│   └── evidencebundle.v1.json
├── python/
│   ├── cli/
│   └── bindings/
└── docs/
    ├── README.md
    ├── SCHEMA_VERSIONING.md
    └── examples/
```

## Schema 對應關係

| 公開 schema 檔名 | 內部 artifact 名稱 | 狀態 |
|---|---|---|
| `researchreceipt.v1.json` | `researchreceipt.v1` | normative |
| `routedecisionreceipt.v1.json` | `routedecisionreceipt.v1` | normative |
| `patchinvocationboundary.v1.json` | `patchinvocationboundaryreceipt.v1` | normative |
| `autonomyobservationreceipt.v1.json` | `autonomyobservationreceipt.v1` | normative |
| `evidencebundle.v1.json` | `evidence_bundle.v1` | provisional，source-of-truth 仍維持 internal |

## 驗證模型

Rust verifier 應只負責：

- canonicalization
- hash integrity verification
- schema compliance
- evidence completeness
- fail-closed result emission

它**不應**負責：

- route selection
- policy decision
- capability planning
- model inference
- public claim generation

## 結果欄位定義

v1 的 normative result schema 以以下五個欄位為準：

- `hashmatch`
- `schemamatch`
- `evidencecomplete`
- `claimabilityconfirmed`
- `errorcode`

若保留 `isvalid`，它僅能作為 convenience derived field：

```
isvalid = hashmatch && schemamatch && evidencecomplete
```

`claimabilityconfirmed` 仍必須視為獨立的 fail-closed 判斷面，不能被簡化併入 `isvalid`。

## Python 介面策略

MVP 採 **CLI-first** 策略：

```bash
receipt verify <file> --strict
```

Python 端可透過 stdin/stdout 呼叫 Rust verifier。PyO3 bindings 僅列為 Phase 2 之後的評估項目。

## Release Gates

| Gate | 要求 | 驗證方式 |
|---|---|---|
| G1 | Python 與 Rust canonicalization 一致 | Cross-language parity suite |
| G2 | Mismatch 必須留下 report | Repo 內保存 mismatch report |
| G3 | Rust unit tests 覆蓋主要驗證路徑 | `cargo test`；coverage 僅作 internal release target |
| G4 | Python CLI 與 Rust verifier 互通 | End-to-end IPC tests |
| G5 | 被篡改的 receipt 永遠不可 claimable | Tamper fixtures + explicit error codes |
| G6 | 缺少必要證據時 fail-closed | Incomplete receipt fixtures |
| G7 | Public/internal schema 分界已文件化 | `SCHEMA_VERSIONING.md` |

## FlowMachine 邊界

FlowMachine **不是** Phase 1 的一部分。它只能被視為 shadow module 或 optional future module。

建議的後續升級 gates：

- FT1：authoritative transition matrix 已定義並文件化
- FT2：allowed / forbidden transition tests 已完成並通過
- FT3：dual-run mismatch ledger 為零
- FT4：selected sample 重複驗證維持零 mismatch
- FT5：rollback drill 通過

## 安全與隱私邊界

本專案不得公開：

- 真實 benchmark rows
- raw command outputs
- private identifiers
- internal training export payloads
- hidden chain-of-thought
- model-specific private metadata

## 為什麼先開這個

1. 它和當前 Rust hardening roadmap 最一致
2. 它能提供外部團隊可直接採用的獨立能力：receipt 驗證與 claimability 檢查
3. 它避開了 Nexus 真正的差異化核心：routing、planning、policy、student adoption

## 後續階段

- **Phase 2**：公開 protocol reference 與 schema/versioning 指南
- **Phase 3**：評估更外圍工具層（前提是 redaction、shadow evidence 與公開指標成熟）

## 開放問題

1. Public schema 檔名是否應完全沿用 internal naming？
2. `evidencebundle.v1.json` 是否應在第一版一起發佈？
3. 第一版對外介面是否應維持完整 CLI-only？
4. 什麼樣的 canonicalization corpus 才足以讓 Python/Rust parity 有高可信度？

## 決議

建議推進 `nexus-receipt-core` 作為 Nexus 第一個 verifier-first 開源子專案。

對外定位：

**Tamper-evident AI execution receipts and claimability verification.**
