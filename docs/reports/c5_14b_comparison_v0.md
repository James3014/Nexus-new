# C5 — 14B Comparison Report (Environment Blocked)

**Status**: C5_ENV_BLOCKED
**Track**: Capability-First Post-V6 Execution Track

---

## 1. Comparison Summary

本階段原計劃將 7B Repair 階段失敗 of 3 個困難任務升級至 `qwen2.5-coder:14b` 進行對比修復。然而，由於本機硬體資源受限（無 GPU 加速，純 CPU 推理），載入並執行 14B 模型時產生了嚴重的系統掛起（Env Hang）與 I/O 阻塞。

為了防止控制平面無限期假死並維持系統的 Fail-Closed 自治能力，Nexus 自治控制平面自動將 C5 階段判定為 **ENV_BLOCKED**，並 graceful 降級退出。

| 任務 ID | 實例 ID | 目標 Symbol | 7B 修復結果 | 14B 修復結果 | 降級/阻斷原因 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `C_13453` | `astropy__astropy-13453` | `HTML` | FAILED (SEARCH Mismatch) | ENV_BLOCKED | CPU 推理時引發系統 IO 卡死與 Timeout |
| `C_11618` | `sympy__sympy-11618` | `Point` | FAILED (SEARCH Mismatch) | ENV_BLOCKED | CPU 推理時引發系統 IO 卡死與 Timeout |
| `C_12481` | `sympy__sympy-12481` | `Permutation` | FAILED (SEARCH Mismatch) | ENV_BLOCKED | CPU 推理時引發系統 IO 卡死與 Timeout |

---

## 2. Telemetry and OS Lockup Analysis

### 7B vs 14B CPU Inference Overhead
在 `run_real_repairs.py` 執行 `qwen2.5-coder:14b-instruct-q3_K_M` 時，前兩次嘗試皆因 Ollama 服務載入模型超時（> 180 秒）而返回空響應 (Empty Response)。在第三次嘗試時，作業系統因大量的 memory page swap 導致系統磁碟 IO 卡死（100% 負載），系統命令如 `ps aux` 及修復進程信號均無法及時響應。

這直接證明：在無 GPU 加速的本機環境下，強制使用 14B 模型進行多次嘗試的 healing 實驗在操作性上是不可行的。

---

## 3. Control Plane Decision

根據 `MUSE_PROTO` 與 `MUSE_ENGINE_SPEC` 的自治規範，當執行環境發生不可修復的硬體挂起時，控制平面必須：
1.   graceful 中斷當前執行，避免耗盡電量或磁碟壽命。
2.   標記狀態為 `REPAIR_BLOCKED / ENV_BLOCKED`。
3.   將 baseline 修復成果結算為 7B 的執行結果（C4 數據）。
4.   進入 C6 差量評估與 Lesson Learned 結算。
