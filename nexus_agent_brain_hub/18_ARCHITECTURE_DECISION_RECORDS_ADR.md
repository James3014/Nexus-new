# 📜 Architecture Decision Records (ADR)

## 1. 決策脈絡索引
ADR 記錄了 Nexus 治理架構中「為什麼這樣做」的深層動機與取捨。

## 2. 核心決策登記冊 (ADR Registry)

| ADR ID | Decision | Rationale | Status |
|---|---|---|---|
| `ADR-001` | Wiki 作為「編譯知識層」 | 避免 Runtime 狀態污染文檔，實現單向同步真值。 | Accepted |
| `ADR-006` | MSA Routing 採「解耦」架構 | 解決 100M Token 下的注意力稀釋問題。 | Accepted |
| `ADR-007` | Supreme Master Loop (PXDRAC) | 將離散步驟歸一化為統一入口，確保治理不遺漏。| Accepted |
| `ADR-008` | 1-bit Core + Bonsai Brain | 實現邊緣自治與雲端服務中斷後的彈性降級。 | Accepted |

## 3. 決策約束
- **查閱要求**: 在提出任何大型重構提案前，必須查閱 ADR，避免重複已被否決的路徑。
- **推翻程序**: 若要更改 ADR，需提供證據證明舊決策的限制，並附帶新的 A/B 測試數據。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Architecture Decision Records.md]**
