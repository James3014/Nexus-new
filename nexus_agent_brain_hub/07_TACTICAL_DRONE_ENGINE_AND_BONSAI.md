# 🚁 Tactical Drone Engine & Bonsai Brain
**[PHYSICAL_STATUS: HARDENED_PROD | GBNF_ENFORCED]**

## 1. 邊緣自治架構
`TacticalDrone` 是 Nexus 的實體執行單元，運作在隔離沙盒中，由 **1-bit Core** 與 **GBNF** 語法強制守門。

## 2. 實體化強制組件
- **1-bit Core (`OneBitGate`)**: 位於 `nexus/core/onebit_core.py`。
    - **動態門檻**: 0.5 ~ 0.95。隨任務複雜度（Tracing Log 長度）自動爬升難度。
- **GBNF Grammar**: 鎖定 LLM 回覆格式，僅允許 `BASH`, `EDIT`, `DONE` 行為。
- **3-Strike Policy**: 連效無效回覆扣 50% 分數，累計三次直接 `FAIL`。

## 3. Bonsai-1.7B 本地大腦
- **實作**: `LocalBonsaiBrain` 支援 GBNF 結構化輸出。
- **接線**: 預設對接 `http://localhost:11434` (Ollama)。

## 4. 執行循環 (Sense-Think-Act)
1. **Sense**: 讀取目標檔案與戰略封套。
2. **Think**: 在 GBNF 約束下生成決策。
3. **Act**: 透過 `DroneToolBox` 執行實體修改。

---
**[Source: New Dimension Audit Batch B - 2026-04-20]**
