# 🧠 Nexus v25.5 P1-P6 記憶與學習閉環深度技術手冊

## 🧬 物理分工 (The Physical Split)
- **MemPalace (MP)**: **【索引與導航】** 提供 Palace/Wing/Room 層級，負責領地防火牆與邏輯索引。
- **LanceDB (LDB)**: **【內容與語義】** 提供高維向量，負責 Episode 存儲與語義召回。

## 📊 P 系列六階段細節 (P-Phase Details)

### P1: 研究與映射 (Research & Mapping)
- **MP**: 初始化當前任務象限 (Wing) 權限。
- **LDB**: 讀取歷史研究摘要 (Reference)。
- **學習閉環**: **[READ]** 基於舊有 Episode 決定本次映射規劃。

### P2: 設計與感應 (Design & Critique)
- **MP**: 調用「倫理規則房間」攔截黑名單。
- **LDB**: 比對歷史成功計畫模式。
- **學習閉環**: **[AUDIT]** 計畫在進入施工前通過行為審校。

### P3: 實作與分片 (Implementation & Sharding)
- **MP**: 鎖定租戶物理路徑 (.nexus/tenants/{id}/)。
- **LDB**: 寫入代碼差異與 Episode 向量。
- **學習閉環**: **[WRITE]** 生成本次施工的原始 Episode 記憶。

### P4: 代謝與精煉 (Metabolism & Distillation)
- **MP**: 存儲蒸餾後的 AAAK 索引與 Arweave TX。
- **LDB**: 執行 30x 消冗，保留精華向量 (Essence)。
- **學習閉環**: **[REFINE]** 將冗長的 P1-P3 日誌轉化為持久化智慧。

### P5: 聯邦與驗證 (Federation & Validation)
- **MP**: 作為全球 gRPC 同步的座標協議。
- **LDB**: 跨 Region 同步大腦狀態。
- **學習閉環**: **[SYNC]** 確保全球集群一致性。

### P6: 結算與硬化 (Settlement & Hardening)
- **MP**: 更新 **BaseSkills** 常設索引。
- **LDB**: 將向量標記為 **Standard (規範)**。
- **學習閉環**: **[HARDEN]** Episode 正式演化為 Standard，供下一次 P1 讀取。

---
**[DOCUMENTED BY NEXUS v25.5 | SMART LOOP COMPLETE]**
