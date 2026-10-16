# Agent B Task Contract Specification v0

**Status**: `OPS_AGENTB_1_TASK_CONTRACT_SPEC_PASS`

**Date**: 2026-07-03

**Purpose**: Define reusable task-contract format for Agent B execution-type tasks in Nexus.

---

## Agent B 適用範圍

Agent B 適合執行以下類型任務：

| 適合 | 不適合 |
|------|--------|
| 小範圍、明確邊界 | 完成 U3 |
| 可測試行為 | 實作 H5 |
| 單一 allowed files 列表 | 讓 local-first work |
| 精確命令 | 優化 route |
| 固定報告格式 | 讓 production ready |
| 明確 forbidden claims | 證明全能力接通 |

---

## 標準任務模板

每個 Agent B 任務必須包含以下 sections：

### Task

```text
任務名稱 + 一句話目標
```

### Status boundary

```text
This is [任務名稱] only.
Do not [列出明確禁止的行為]
```

### Context

```text
已完成的前置任務 + commit hash
目前的 blocker 或觀察到的問題
```

### Goal

```text
一句話 goal
```

### Required behavior

```text
1. [步驟 1]
2. [步驟 2]
...
```

### Allowed files

```text
* path/to/file1.py
* path/to/file2.py
* docs/reports/specific_report.md
```

### Forbidden files

```text
Do not modify:
* path/to/forbidden_file.py
* .nexus/reports/*
* artifacts/*
* scratch/*
```

### Required tests

```text
[測試指令 + 預期結果]
```

### Required commands

```bash
[精確指令]
```

### Required report

```text
docs/reports/specific_report.md
```

### Commit policy

```text
Commit only:
* path/to/file1.py
* docs/reports/specific_report.md

Do not stage:
* .nexus/reports/*
* artifacts/*
* scratch/*
* unrelated files

Allowed commit message:
`[精確訊息]`
```

### Forbidden claims

```text
* Do not claim [明確禁止的宣稱]
```

---

## Agent B 輸出審查清單

每次 Agent B 完成任務後，必須檢查：

| 檢查項目 | PASS/BLOCKED |
|---------|-------------|
| scope matches task | |
| changed files are within allowed files | |
| tests actually ran and passed | |
| report status does not overclaim | |
| commit did not include runtime artifacts | |
| commit did not include pycache | |
| commit did not include scratch files | |
| commit did not include unrelated reports | |
| commit did not include dirty files | |
| forbidden claims are not present | |

---

## 錯誤宣稱與修正對照

| 錯誤宣稱 | 修正後 |
|---------|--------|
| `CLOUD_MODEL_E2E_SMOKE_PASS` | `FIELD_PROPAGATION_PASS` |
| `H5 implemented` | `H5 trace-only metadata scaffold added` |
| `cloud model E2E verified` | `model_calls field propagation verified; no real cloud provider called` |
| `local-first ready` | `trace-only metadata present; local-first execution not implemented` |
| `delegated retry solved` | `delegated retry branch wired / observable` |
| `Nexus full capability ready` | `[specific capability] trace evidence collected` |
| `production_ready` | `trace-only; production_ready=false` |
| `public_claim_allowed` | `public_claim_allowed=false unless explicitly proven` |

---

## Nexus 專用警告

| 警告 | 說明 |
|------|------|
| benchmark tuning ≠ full capability | 調 benchmark 讓 toy task pass 不等於 Nexus 全能力接通 |
| first-pass solved ≠ delegated-retry solved | 兩者是不同分支、不同 claim |
| trace-only ≠ implementation | trace-only metadata 存在不代表功能已實作 |
| field propagation ≠ E2E | 欄位從 A 傳到 B 不代表端到端已驗證 |
| receipt existence ≠ production readiness | receipt 存在不代表 production ready |
| public_claim_allowed 必須保持 false | 除非有明確 evidence 證明 |

---

## Agent B 任務審查流程

```text
1. 讀 task specification
2. 確認 allowed files / forbidden files
3. 確認 required commands
4. 確認 forbidden claims
5. 執行 task
6. 自我檢查 8 個 boundary checks
7. 產出 report
8. 用 review checklist 審查
9. commit only allowed files
10. 回報 status / commit / files / commands / validation
```

---

## Status: OPS_AGENTB_1_TASK_CONTRACT_SPEC_PASS

**Files changed**: `docs/reports/agent_b_task_contract_spec_v0.md`

**Commands run**:
- `test -f` — document exists
- `grep` — all required headings present
- `git diff` — only allowed file touched

**Validation result**: PASS

**Explicit non-claims**:
- Spec-only, no runtime behavior changed
- C15-4B untouched
- No code changes
- No benchmark changes
- No test changes
- Not production_ready
- Not public_claim_allowed
