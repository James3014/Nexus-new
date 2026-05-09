---
aliases:
- CLI Full Parameters
- CLI Help Mapping
confidence: medium
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[05_Protocols/Protocol - CLI Surface.md]]'
source_of_truth: scripts/engine/nexus_cli.py
status: hardened
tags:
- protocol
- cli
- help-map
title: CLI Full Parameter & Help Map
type: protocol
version_scope: v26
---

# CLI Full Parameter & Help Map

## One-sentence summary
維護 CLI 命令與參數對照，確保執行路徑、風險控制與觀測介面一致。

## Role / responsibility
- 定義核心 CLI 參數與實際行為映射。
- 避免 CLI 文檔與實作版本脫節導致調度偏差。

## Upstream
- `scripts/engine/nexus_cli.py` 指令定義。
- 導航腳本與運維腳本的入口參數。

## Downstream
- `06_Ops/Ops - CI Failure Playbook.md`
- `06_Ops/Ops - Wiki Drift Audit.md`

## Related modules / files
- `scripts/engine/nexus_cli.py`
- `scripts/ops/ci_gate.py`

## Source notes
- 參數對照以 `uv run scripts/engine/nexus_cli.py --help` 輸出為主。[Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] `--risk` 與 `--mode` 是否需要對外文件加上互斥規則？
- [ ] 是否需要對高風險參數增加 `--dry-run` 取樣保護？

## 終端命令對照區
| CLI Display | Full Parameter | Function |
| :--- | :--- | :--- |
| `run` | `nexus run` | 啟動 P-X-D-R-A-C 大循環。 |
| `status` | `nexus status --fleet` | 觀測全局或機群健康度。 |
| `drone-hud`| `nexus drone-hud --listen` | 建立即時 SSE 監控串流。 |
| `gate` | `nexus delivery-gate` | 物理 Endpoint 最終核驗。 |

## 高級參數規約
- `--risk <0.1~0.95>`：調整 1-bit Core 靈敏度。
- `--mode <hyper|night>`：切換敏捷/回歸模式。
- `--trace-id <UUID>`：鎖定當前譜系紀錄標籤。

## Link to System
[[System Overview]]
