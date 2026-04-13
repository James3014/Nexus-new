# Nexus 測試分類政策 (Test Classification Policy)

為了最佳化測試執行效率與穩定性，Nexus 測試資產分為以下類別：

## 1. 分類定義

| 標籤 (Tag) | 定義 | 執行策略 |
| :--- | :--- | :--- |
| **active** | 核心邏輯、近期有變動、執行快速且穩定。 | 每次 Commit (L1) 必跑。 |
| **slow** | 耗時超過 10s 的測試（如整合測試、大型模型載入）。 | PR 合併前 (L3) 或夜間執行。 |
| **flaky** | 具備不穩定紀錄（如依賴外部網路、競態條件）。 | 隔離至 quarantine 並標記修復。 |
| **legacy-candidate** | 程式碼路徑不明確、無直接對應核心模組、或屬於舊版本。 | 抽樣執行，評估後遷移或存檔。 |
| **quarantine-candidate**| 持續失敗或阻斷 CI 的測試。 | 暫時禁用，必須有對應 Bug Ticket 追蹤。 |

## 2. 自動判定規則

- **耗時判定**: `pytest --durations` 顯示前 5% 且 > 5s 者標記為 `slow`。
- **影響判定**: 未直接引用 `nexus/core`, `nexus/services`, `nexus/engine` 且位於根目錄的測試標記為 `legacy-candidate`。
- **不穩定判定 (Flaky)**: 
  - 門檻：10 次執行中出現 >= 1 次非預期失敗。
  - 處理：標記 `flaky` 並隔離至隔離區。

## 3. 隔離區規則 (Quarantine Rules)

- **進入條件**: 持續阻斷 CI、具備高 Flaky 比率、或環境依賴暫不可用。
- **執行方式**: 在 L1/L2 中預設跳過，僅在 L3 中追蹤狀態。
- **解除條件**: 
  - 已完成 Root Cause 定位與修復。
  - 本地連跑 10 次全綠。
  - 經工程會議或 Lead 核准移回 `active`。
