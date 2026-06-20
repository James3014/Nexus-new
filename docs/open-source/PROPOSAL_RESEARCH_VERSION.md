---
title: Nexus Receipt Core — Academic Reproducibility Research Version
version: v4
last_updated: 2026-06-16
tags:
  - open-source
  - research
  - protocol
  - evidence
  - reproducibility
---

# Nexus Receipt Core — 研究社群版提案

## 定位

**給 AI 研究者用的「可驗證 AI 輸出」標準化工具。**

幫助研究者證明：「我的實驗結果是真的、可重複的、沒有被篡改的。」

## 目標使用者

- AI/ML 研究者（特別是 LLM agent 領域）
- Benchmark 開發者
- 需要 reproducible research 的學術團隊
- 期刊/會議的 reviewer（驗證作者提交的結果）

## 核心問題

當前 AI 研究面臨的信任危機：
1. 許多 benchmark 結果無法重現
2. 論文中的實驗數據可能是「手動調整過的」
3. 沒有標準化的方法來證明實驗輸出的完整性
4. 模擬數據與真實數據難以區分

## 解決方案：Evidence Chain Protocol

### 1. 研究場景下的 Receipt

```json
{
  "type": "experiment_receipt",
  "version": "1.0",
  "metadata": {
    "model": "qwen2.5:3b",
    "benchmark": "swe-bench-lite",
    "timestamp": "2026-06-16T09:00:00Z",
    "researcher": "[REDACTED]",
    "institution": "[REDACTED]"
  },
  "evidence": [
    {
      "type": "raw_output",
      "hash": "sha256:abc123...",
      "size_bytes": 4096,
      "canonical_form": true
    },
    {
      "type": "benchmark_result",
      "hash": "sha256:def456...",
      "score": 0.368,
      "total_tasks": 38,
      "solved_tasks": 14
    },
    {
      "type": "configuration",
      "hash": "sha256:ghi789...",
      "seed": 42,
      "temperature": 0.0,
      "max_tokens": 4096
    }
  ],
  "verification": {
    "hashmatch": true,
    "schemamatch": true,
    "evidencecomplete": true,
    "claimabilityconfirmed": true,
    "errorcode": null
  },
  "claimable": true,
  "claim": "This experiment achieved 36.8% solve rate on SWE-bench Lite v1.0"
}
```

### 2. 學術引用格式

```bibtex
@software{nexus_receipt_core_2026,
  author = {Nexus Contributors},
  title = {Nexus Receipt Core: Tamper-Proof Evidence for AI Experiments},
  year = {2026},
  url = {https://github.com/nexus-project/receipt-core},
  note = {Version 1.0 — Verified experiment evidence chain}
}
```

### 3. Peer Review 工作流程

```
Reviewer 收到論文附件:
├── paper.pdf
├── experiment_receipt.json
└── evidence_bundle/
    ├── raw_output.txt (hash: sha256:...)
    ├── benchmark_results.csv (hash: sha256:...)
    └── configuration.yaml (hash: sha256:...)

Reviewer 執行驗證:
$ receipt verify --input experiment_receipt.json --strict
✓ All integrity checks passed
✓ hashmatch: true
✓ schemamatch: true
✓ evidencecomplete: true
✓ claimabilityconfirmed: true
✓ Evidence bundle hash matches manifest
✓ No simulated timestamps detected
✓ Claim is substantiated by evidence

Reviewer 結論:
"實驗結果經 nexus-receipt-core 驗證，證據鏈完整，
可支持論文的 36.8% solve rate 主張。"
```

## 研究價值

| 價值 | 說明 |
|------|------|
| **Reproducibility** | 其他研究者可以用相同的 receipt 驗證實驗是否可重現 |
| **Anti-manipulation** | 檢測手動調整的 benchmark 結果 |
| **Simulated data detection** | 自動識別模擬數據（timestamp clustering） |
| **Standardized reporting** | 統一的實驗證據格式，便於期刊/會議要求 |
| **Cross-benchmark comparison** | 不同 benchmark 的結果可以用同一套標準驗證 |

## 與現有標準的區別

| 標準 | 關注點 | 與 Receipt Core 的差異 |
|------|--------|----------------------|
| MLflow | 實驗追蹤 | 不驗證數據完整性，不防篡改 |
| DVC | 數據版本控制 | 不驗證實驗結果的可信度 |
| Papers With Code | 結果彙整 | 無驗證機制，可能包含手動調整數據 |
| **Nexus Receipt Core** | **證據完整性 + 防篡改** | **提供可程式化驗證的證據鏈** |

## 里程碑

| 階段 | 內容 | Gate |
|------|------|------|
| M1 | 定義 `experiment_receipt` schema | G7: Schema versioning |
| M2 | 實作 simulated data detection 演算法 | G5: Tamper detection |
| M3 | 建立 peer review 驗證工作流程 | G6: Missing evidence fail-closed |
| M4 | 與主流 benchmark 框架整合（SWE-bench、HumanEval 等） | G3: Unit tests |
| M5 | 撰寫白皮書：「Tamper-Proof AI Experiment Reporting」 | G1-G7 all passed |

## 風險與緩解

| 風險 | 影響 | 緩解 |
|------|------|------|
| 研究者不願意改變工作流 | 採用率低 | 提供 CLI wrapper，不改變現有 benchmark 運行方式 |
| Schema 太複雜 | 學習曲線陡峭 | 提供 starter template + 自動生成工具 |
| 無法阻止「選擇性報告」 | 研究者仍可只報告有利結果 | 要求提交 full experiment manifest（所有嘗試） |
