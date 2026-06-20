---
title: Nexus Open-Source Subproject Roadmap
version: v4
last_updated: 2026-06-16
status: draft
tags:
  - open-source
  - roadmap
  - governance
  - rust
  - evidence
related:
  - NEXUS_V26_RUST_3B_REVISED_PLAN_2026-06-12.md
  - NEXUS_DECISION_PACK_v26.md
  - NEXUS_GOVERNANCE_CONSOLIDATED_MASTER.md
---

# Nexus 開源子專案路線圖

## 切入原則

1. **可驗證**：功能邊界清楚，有明確的輸入/輸出/驗證條件
2. **可獨立使用**：別的團隊可以不依賴 Nexus 核心就能採用
3. **不暴露核心策略**：不暴露 router、capability planning、policy、訓練資料面

## 市場定位

**Tamper-evident AI execution receipts and claimability verification.**

不賣「治理戰甲」，只做一件事：驗證 AI 輸出是否有完整證據鏈、是否被篡改、能不能被公開聲稱。

---

## 綜合比較矩陣

| 方向 | 優先級 | 可驗證性 | 獨立採用度 | 策略暴露風險 | 準備度 | 市場定位 |
|------|--------|----------|------------|--------------|--------|----------|
| **Rust Receipt Verifier** | P0 | 高 | 高 | 低 | 需先過 canonicalization gate | Tamper-evident evidence 基礎設施 |
| **Public Schema + CLI** | P0 | 高 | 高 | 低 | 高 | 標準化工具鏈 |
| **FlowMachine / Transition Validator** | P1（shadow） | 中 | 中 | 低 | 需 transition matrix + dual-run gate | Workflow 治理引擎（未來） |
| **Protocol Reference** | P2 | 高 | 高 | 低 | 高 | 協議標準層 |
| **LocalHeal** | P3（條件式） | 中 | 中 | 中 | 數據不足 | 本地模型修復引擎（未來） |
| **S2T Export / Redaction Toolkit** | P3（高風險） | 高 | 低 | **高** | 資料安全風險 | 資料衛生工具（暫緩） |

---

## 三段式路線圖

### Phase 1：nexus-receipt-core（Rust verifier + Public Schemas + CLI）

**範圍：只做驗證，不做策略。**

**子項目結構：**
```
nexus-receipt-core/          # 主倉庫
├── rust/                    # Deterministic verification engine
│   ├── receipt_verifier/    # Canonical JSON + SHA-256 + schema compliance
│   └── Cargo.toml
├── schemas/                  # Public JSON Schema definitions
│   │
│   # Public filename ↔ Internal artifact name mapping:
│   ├── researchreceipt.v1.json          # → researchreceipt.v1 (internal, normative)
│   ├── routedecisionreceipt.v1.json     # → routedecisionreceipt.v1 (internal, normative)
│   ├── patchinvocationboundary.v1.json  # → patchinvocationboundaryreceipt.v1 (internal, normative)
│   ├── autonomyobservationreceipt.v1.json # → autonomyobservationreceipt.v1 (internal, normative)
│   └── evidencebundle.v1.json          # → evidence_bundle.v1 (internal, provisional — source-of-truth TBD)
├── python/                   # Python interface（CLI 為主，bindings 為次）
│   ├── cli/                  # receipt verify <file>
│   └── bindings/             # pyo3 (optional, post-MVP)
└── docs/
    ├── README.md             # 主打 tamper-evident, claimability
    ├── SCHEMA_VERSIONING.md
    └── examples/
```

**Rust 端只做五件事：**
1. **Canonicalization**：JSON 格式校準（鍵排序、字串編碼、數值正規化）
2. **Hash integrity**：SHA-256 匹配
3. **Schema compliance**：驗證 receipt 是否符合公開 schema
4. **Evidence completeness**：檢查 required fields 存在
5. **Fail-closed result emission**：任何驗證失敗一律 return error code，不 silent fail

**公開 receipt 欄位（與現有文件對齊）：**
- `hashmatch` — canonical hash 是否匹配
- `schemamatch` — schema version 是否有效
- `evidencecomplete` — required evidence 是否齊全
- `claimabilityconfirmed` — 是否可以公開聲稱
- `errorcode` — 驗證失敗時的錯誤碼
- `isvalid`（optional derived field）— 若保留，定義為 `hashmatch && schemamatch && evidencecomplete` 的 convenience 欄位，不作為唯一判定來源

**Result schema source-of-truth：** v1 normative result schema 以 `hashmatch`、`schemamatch`、`evidencecomplete`、`claimabilityconfirmed`、`errorcode` 五欄位為準；`isvalid` 若存在僅為 convenience wrapper，不影響 fail-closed 判定。

**內部欄位（private schema layer，不公開）：**
- 策略面欄位（哪些 receipt 需要產生、何時產生）
- Internal routing metadata
- Model-specific fields

**Python interface 策略：**
- **MVP 只做 CLI**：`receipt verify <file> --strict`，透過 stdin/stdout 通訊
- **Phase 2 評估是否加 pyo3 bindings**：等 schema 穩定後再決定
- 不對外承諾 Python API 穩定性，直到 v1.0 release

**Phase 1 Release Gates（必須全部通過才能發佈 v1.0）：**

| Gate | 條件 | 驗證方式 |
|------|------|----------|
| **G1: Canonicalization parity** | Python 與 Rust canonicalization 100% 一致 | Cross-language test suite：同一輸入，兩端產生相同 hash |
| **G2: Mismatch report** | 若有任何 Python/Rust 差異，必須產出完整 mismatch report 並修復 | 報告存档於 repo，包含所有 failing cases |
| **G3: Unit tests** | Rust unit tests 非空，覆蓋所有驗證路徑 | `cargo test` 覆蓋率作為內部 release target（不設外部承諾百分比） |
| **G4: IPC tests** | Python CLI 與 Rust binary 的 IPC 通訊正常 | 端到端測試：Python 呼叫 Rust binary，驗證輸入輸出 |
| **G5: Tamper detection** | 被篡改的 JSON 不能 claimable | 故意修改 receipt，驗證返回 error code |
| **G6: Missing evidence fail-closed** | 缺少 evalmetrics 或必要證據時 fail | 送 incomplete receipt，驗證不 silent pass |
| **G7: Schema versioning** | Public schema 與 private schema 已分離 | Public/internal schema separation 已文件化 |

**永遠不納入 Phase 1：**
- FlowMachine / transition validation（需额外 gate，見下方）
- Capability routing 或 policy engine
- 任何模型推理邏輯
- 訓練資料或 benchmark rows

---

### Phase 1.5（FlowMachine 條件式扩展）

FlowMachine 是 shadow 模組，不是 Phase 1 的一部分。只有當以下 **所有** gate 都通過時，才可從 shadow 提升為正式模組：

| Gate | 條件 |
|------|------|
| **FT1** | Authoritative transition matrix 已定義並文檔化 |
| **FT2** | Allowed/forbidden transition tests 已實作並通過 |
| **FT3** | Python-vs-Rust dual-run mismatch ledger 為零 |
| **FT4** | Selected sample 上 mismatch rate = 0%（連續 3 次測試） |
| **FT5** | Rollback drill 成功（transition 錯誤時可回滾） |

任一 gate 未過，FlowMachine 維持 shadow/optional，不進入公開承諾。

---

### Phase 2：Protocol Reference + Schema 固化

在 Receipt Core v1.0 穩定且 schema versioning 固化後，再開 protocol reference：

**內容：**
- 三大協議文檔化（RLM、Evidence Chain、Capability Routing）
- 每個協議附帶最簡 Python 參考實作（50-100 lines）
- 與 nexus-receipt-core 的整合示例
- Schema 版本管理策略（backward compatibility guarantees）

**定位：** 「tamper-evident AI evidence 的協議層」—— 不綁定任何語言或框架。

---

### Phase 3：LocalHeal / S2T 周邊（條件式）

只有當以下條件都滿足時，才考慮開放 LocalHeal 或 S2T 相關工具：
- 真實 shadow evidence 已累積足夠數據
- Redaction discipline 已建立並測試通過
- 公開指標（如 SWE-bench solve rate）達到可公開水準
- **絕對不碰**：student 本體、router、training export 內核

---

## 永遠不開放的部分

| 項目 | 原因 |
|------|------|
| autonomic router / capability planner | 核心決策策略，暴露即喪失差異化 |
| 3B student 本體與訓練資料 | S2T selector/reranker advisor 定位，runtime adoption 需 shadow evidence + trust mismatch + held-out evaluation 全部過關 |
| 內部 training export pipeline | redaction failure 為高風險事項，直接洩漏 private identifiers |
| 真實 benchmark rows / command outputs | 含 private identifiers |
| Belief confidence engine / MemPalace policy | 策略面，非驗證面 |

---

## 命名與定位

| 選項 | 倉庫名 | 敘事 | 評估 |
|------|--------|------|------|
| **推薦** | `nexus-receipt-core` | Tamper-evident AI execution receipts and claimability verification | 最貼現狀，不浮誇，與現有文件一致 |
| 次選 | `nexus-evidence-kit` | 證據工具包 | 直接呼應 Nexus 哲學，但聽起來偏小 |
| 避免 | `nexus-governance-sdk` | 治理 SDK | 太宏大，暗示已產品化整套治理策略 |
| 避免 | `nexus-trust-engine` | 信任引擎 | 過度承諾，容易讓外界誤解 |

---

## 風險矩陣

| 風險 | 影響 | 緩解 | Gate |
|------|------|------|------|
| Python/Rust canonicalization mismatch | 驗證失效，可信度崩潰 | 先完成 mismatch report，建立 cross-language test suite | G1, G2 |
| Schema 頻繁變更 | 使用者困惑 | 版本化 schema，backward compatibility guarantee | G7 |
| 模擬數據混入 | 可信度受損 | 開源前徹底清除模擬 timestamp | G5 |
| FlowMachine 未驗證就公開 | 過渡錯誤不被檢測 | Shadow module 機制，FT1-FT5 gate | FT1-FT5 |
| Python bindings 过早承诺 | API 頻繁變更 | MVP 只做 CLI，bindings 列為 optional | Python interface strategy |

---

## 下一步行動

1. [ ] 評估 Python/Rust canonicalization mismatch 的修復工作量
2. [ ] 建立 cross-language canonicalization test suite
3. [ ] 撰寫 RFC：nexus-receipt-core specification（public schema 定義，明確 5 欄位）
4. [ ] 定義 researchreceipt.v1、routedecisionreceipt.v1、patchinvocationboundary.v1、autonomyobservationreceipt.v1 等 schema 的正式版本
