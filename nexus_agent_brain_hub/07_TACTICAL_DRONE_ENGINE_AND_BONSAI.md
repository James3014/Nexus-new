# 🚁 Tactical Drone Engine & Bonsai Brain

## 1. 邊緣自治架構
`TacticalDrone` 是 Nexus 的實體執行單元，運作在隔離的沙盒環境中，確保「開發行為」不會污染「治理環境」。

## 2. 1-bit Core 與 GBNF 語法
- **1-bit Core**: Drone 的決策被簡化為極高精準度的原子化判定（YES/NO），減少幻覺。
- **GBNF (Grammar)**: 強制 LLM 產出符合 JSON Schema 的結構化指令，防止解析錯誤。

## 3. Bonsai-1.7B 本地大腦
- **定位**: 專為低功耗、高隱私、離線環境設計。
- **實作**: 透過 `LocalBonsaiBrain` 封裝，支援 GBNF 結構化輸出。
- **降級邏輯**: 當雲端 LLM 觸發配額限制或網路中斷時，Drone 自動切換至 Bonsai 模式。

## 4. 執行循環 (Sense-Think-Act)
1. **Sense**: 讀取目標檔案與 `StrategicEnvelope`。
2. **Think**: 在 GBNF 約束下生成解決方案。
3. **Act**: 透過 `DroneToolBox` 執行 Bash 或 File Edit。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Advanced Core Intelligence.md]**
