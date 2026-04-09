# 🛡️ Nexus Design Specification (v1.0)

## 🌌 視覺主題與氛圍 (Atmosphere)
- **核心魂魄**: Hardened Industrial, Terminal-First, Singularity Ready.
- **氛圍感**: 嚴謹、高密度、藍色/綠色終端質感、100% 物理對齊。

## 🎨 調色盤與角色 (Color Roles)
- `nexus-primary`: #00FF41 (Matrix Green) - 用於成功、通過、結晶。
- `nexus-warn`: #FFD700 (Amber) - 用於漂移警告、隱私干擾。
- `nexus-danger`: #FF3131 (Red Alert) - 用於投毒攻擊、守門阻斷。
- `nexus-surface`: #0D0D0D (Deep Black) - 背景色。

## 📐 佈局原則 (Layout)
- **網格系統**: 採用的 8px 基準步長（8, 16, 24, 32）。
- **密度**: 高資訊密度（High Information Density）。不允許過度的留白，資訊必須以矩陣或 JSON 結構緊湊呈現。

## 🔩 組件規範 (Components)
- **代碼塊**: 必須包含語言標籤與 `NEXUS` 註記。
- **日誌條目**: 必須包含 `[TIMESTAMP]`, `[LEVEL]`, `[ID]` 三要素。
- **儀表板**: 使用 ASCII Border 模擬物理硬體邊界。

## 🚫 設計禁忌 (Do's and Don'ts)
- **Don't**: 使用圓角矩形（Nexus 崇尚銳角邊緣，代表精密）。
- **Don't**: 使用漸層色（Nexus 是二進位思維，只有純色）。
- **Do**: 凡輸出必有物理證據（ls/cat/SHA）。
- **Do**: 所有百分比必須保留兩位小數並經過物理計算。

## 🧠 代理提示指南 (Agent Prompt Guide)
> "參考 DESIGN.md，以高資訊密度、硬核終端風格產出本次任務的 UI 或報告。"
