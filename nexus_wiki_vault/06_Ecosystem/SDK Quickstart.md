---
aliases:
- SDK Quickstart
- External Client
confidence: medium
last_compiled: '2026-05-06'
owner: agent
related_pages: '[[06_Ops/Ops - Artifact Retention and Provenance.md]]'
source_of_truth: scripts/ops/ci_gate.py
status: draft
tags:
- sdk
- quickstart
- ecosystem
title: SDK Quickstart
type: reference
version_scope: v26
---

# SDK Quickstart

## One-sentence summary
提供「安裝到發起首個任務」的最短安全路徑，作為外部使用者接入 Nexus 的起始入口。

## Role / responsibility
- 定義 SDK 的最小可用操作。
- 提供可直接複製執行的安裝與呼叫範例。

## Upstream
- `requirements` 與套件發佈配置。
- 端點與憑證初始化規範。

## Downstream
- `04_Research/Research - DeepScientist Integration.md`
- `00_Product/User Stories.md`

## Related modules / files
- `scripts/ops/ci_gate.py`
- `scripts/engine/nexus_client.py`

## Source notes
- SDK 初始化流程目前僅有既有文件與示範程式碼描述，尚未完成完整可驗證 API 錄制。[Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] 外部 SDK 是否需要支持「無憑證沙箱測試」模式？
- [ ] `task_id` 的生命週期是否應納入同一份正式的憑證鏈？

## 1. Installation
```bash
pip install nexus-sdk
```

## 2. Basic Usage
```python
from nexus_sdk import NexusClient

client = NexusClient(endpoint="http://localhost:8080")
task_id = client.dispatch(intent="Optimize memory", mode="Hyper")
```

## 3. 版本註記
- VERSION: v1.0.0
- STATUS: STABLE

## Link to System
[[System Overview]]
