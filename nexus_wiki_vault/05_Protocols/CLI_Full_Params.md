# 🖥️ CLI Full Parameter Reference (v1.0)
**[PHYSICAL_STATUS: SSOT_WIRED | LAYER_4_OPERATIONAL]**

## 1. `nexus_cli.py` 全參數表格

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--mode` | string | `dual` | 運行模式：`hyper` (速度), `night` (回歸), `dual` (MSA+Palace)。 |
| `--risk` | float | `0.5` | 1-bit Core 判決敏感度。高風險任務建議 `0.9`。 |
| `--nodes` | int | `5` | Swarm 並行 Drone 數量上限。 |
| `--force` | bool | `False` | 強制繞過非 P0 級別的 Gate (需管理員權限)。 |
| `--trace-id` | string | UUID | 指定全鏈路追蹤 ID。 |

## 2. 子命令對位
- **`run`**: 執行完整的 P-X-D-R-A-C 邏輯。
- **`acceptance-check`**: 調用 `HallucinationGuard` 計算 HI 分數。
- **`contract-check`**: 校驗 Git SHA 與任務契約。
- **`drone-hud`**: 開放實時監控串流。

---
**[Source: uv run scripts/engine/nexus_cli.py --help]**
