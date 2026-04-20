# 🛠️ Operational Scripts & Tools Index

## 1. 腳本工具全景
本頁索引了位於 `scripts/ops/` 中的核心治理腳本，這是 Nexus 的「感覺器官」。

## 2. 核心腳本清單

| 腳本 | 分類 | 作用 |
|---|---|---|
| `ci_gate.py` | 門禁 | 任務發布前的物理與邏輯終極守門員。 |
| `nexus_acceptance_check.py` | 驗收 | 解析證據包並計算 HI 幻覺指數。 |
| `wiki_sync_check.py` | 紀錄 | 驗證 Wiki 與代碼變更的對位程度。 |
| `verify_report_claims.py` | 審計 | 核查報告中的斷言是否具備對應的引用。 |
| `_nexus_preflight.sh` | 環境 | 確保 Runtime 環境符合生產標準。 |
| `task_contract_guard.py` | 契約 | 監控任務變更是否超出合約定義範圍。 |

## 3. 呼叫規約
- 優先使用 `uv run` 以確保依賴隔離。
- 腳本輸出應支援 `--json` 旗標，以便被上層 `Orchestrator` 解析。

## 4. 偵錯模式
- 設置 `NEXUS_DEBUG=1` 以獲取詳細的腳本執行 Trace Log。

---
**[Source: nexus_wiki_vault/90_Sources/Source - Operational Scripts Index.md]**
