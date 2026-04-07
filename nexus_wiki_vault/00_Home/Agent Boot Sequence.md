---
aliases: '[Boot Sequence, First 30 Minutes, Agent Boot SOP]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[home](System Overview.md), [onboarding](Agent Onboarding - Command Pack.md), boot,
  sop]'
title: Agent Boot Sequence
type: '[home](System Overview.md)'
version_scope: '[v22, v23]'
---



# Agent Boot Sequence

## One-sentence summary
本頁定義新 Agent 進場後前 30 分鐘的最小可執行流程，確保所有任務先通過 Nexus 基線門禁再開始實作。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- **啟動標準化**: 提供新 Agent 的固定啟動順序，降低環境誤判與流程漂移。
- **失敗早檢出**: 先做命令面與治理 gate 檢查，避免後段返工。 [Source: scripts/ops/ci_gate.py]

## Upstream
- `[MUSE_PROTO](../01_System/MUSE_PROTO.md).md`: 定義全域協議錨點。 [Source: 01_System/MUSE_PROTO.md]
- `scripts/engine/nexus_cli.py`: 定義 Nexus 命令面。 [Code: scripts/engine/nexus_cli.py]

## Downstream
- `[Agent Onboarding - Implementation Map](Agent Onboarding - Implementation Map.md)`: 進入任務執行路徑。
- `[Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)`: 若 preflight 失敗時的修復入口。

## Related modules / files
- `scripts/engine/nexus_cli.py`
- `scripts/ops/ci_gate.py`
- `scripts/ops/wiki_linter.py`

## 🗺️ Step 0: Landscape Discovery (地景探索)
新 Agent 進場的第一動作**不是**跑指令，而是確立座標。
1.  **確認地圖**: 查閱 [Vault Topology](Vault Topology.md) 建立架構全景。
2.  **建立脈絡**: 閱讀 [System Overview](System Overview.md) 了解當前治理基線。
3.  **安全考古**: 若任務涉及深層邏輯，必須查閱 [[01_Core/Specs/Legacy_V9/INDEX|Legacy Index]]。

## Source notes
- 建議固定步驟：
```bash
uv run scripts/engine/nexus_cli.py --help
uv run scripts/ops/ci_gate.py --dry-run
uv run scripts/ops/wiki_linter.py --strict
```

## Open questions / conflicts
- [ ] 是否要把 `acceptance-check` 納入所有任務啟動前必跑清單。
- [ ] 是否要強制回報 `nexus_participation_ratio` 作為啟動合規證據。