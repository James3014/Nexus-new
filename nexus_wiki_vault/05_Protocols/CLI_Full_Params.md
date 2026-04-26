# 🖥️ CLI Full Parameter & Help Map (v32.3)
**[PHYSICAL_STATUS: SSOT_WIRED | TERMINAL_SYNC]**

## 1. 終端命令對照區 (--help Mapping)
本節內容直接映射自 `uv run scripts/engine/nexus_cli.py --help`。

| CLI Display | Full Parameter | Function |
| :--- | :--- | :--- |
| `run` | `nexus run` | 啟動 P-X-D-R-A-C 大循環。 |
| `status` | `nexus status --fleet` | 觀測全局或機群健康度。 |
| `drone-hud`| `nexus drone-hud --listen` | 建立即時 SSE 監控串流。 |
| `gate` | `nexus delivery-gate` | 物理 Endpoint 最終核驗。 |

## 2. 高級參數規約
- **`--risk <0.1~0.95>`**: 調整 1-bit Core 靈敏度。
- **`--mode <hyper|night>`**: 切換敏捷與回歸模式。
- **`--trace-id <UUID>`**: 鎖定當前譜系紀錄標籤。

---
**[Source: scripts/engine/nexus_cli.py | CLI-VERIFIED]**
