# Nexus Docs Index

### Current (正在做)
- **主線任務**：建立 `P->X->D->R->A->C` 階段健康自治（可監測、可自癒、可自優化）。
- **當前操作**：優化 `INDEX.md` 資訊架構，清理環境並準備啟動 Nexus Worker。
- **單一執行入口**：`uv run scripts/nexus_cli.py nexus:runner`
- **實時狀態彙報**：[EXEC_LIVE_STATUS.md](file:///Users/jameschen/Workspace/nexus/docs/EXEC_LIVE_STATUS.md)

## 🏆 目標導航
- [x] Goal 1: 建構 Phase Health 監測基礎層
- [x] Goal 2: 實作自主修復 (Repair) 第一階段
- [x] Goal 3: 升級並行調度 (Parallel) 核心
- [x] Goal 4: 實作額度與 OAuth 守衛 (Guard) 
- [x] Goal 5: **16_CAPABILITY_SPEC_MATRIX: Nexus v9 能力規格矩陣** [DONE]
- [x] Goal 6: Night Shift L3 核心實體化 (Swarm Isolation + RCA Adapter) [DONE]
- [x] **Goal 7: 大腦自癒生態系 L4 (自動策略遷移與記憶再生)**: M1+M2+M3 通過校準 (LanceDB 檢索與 Ingestion 閉環已打通)。

### Trinity Evolution (三位一體演化)
- [x] **Intent Gate**：攔截模糊指令，提升 P 階段對位率 (TDD PASSED)
- [x] **Coherence Filter (TOON)**：語義壓縮，Context 噪訊下降 70% (TDD PASSED)
- [x] **Autonomic Learning (Trauma)**：失敗驅動調權，系統具備自癒學習能力 (TDD PASSED)

### Done (已完成)
- **物理收斂 WP-4**：完成 `wt-wp4-1` 至主線的實體合併與測試驗收 (2026-03-19)。參閱 [重構PR任務包_超細版](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-17_Nexus_重構PR任務包_超細版.md)。
- **文檔歸檔與環境清理**：將 20 餘份 ERA-A/B 歷史文檔移入 `docs/archive` 目錄。
- **Phantom Success Guard**：實施防再犯 5 條規則，並通過全量 Gate 驗證。參閱 [Phantom_Success_RCA](file:///Users/jameschen/Workspace/nexus/docs/2026-03-19_Phantom_Success_Incident_RCA_and_Prevention.md)。
- **主管進程修復**：解決 macOS Seatbelt 權限導致的 supervisor 啟動問題。
- **Token 審計通車**：已成功打通 `raw token` 來源，具備真實帳單擷取與審計能力。

### Blocked (阻塞中)
- (目前無嚴重阻塞，系統基線處於 PASS / STRICT 狀態)

---

## 🧭 指引與規則 (ERA-C)

## 使用方式
只要先讀本檔，再依「執行順序」逐份執行即可。

## 文件時期標記（2026-03-18 起）
為避免不同時期規格混用，所有文件先判定時期再執行。
- `ERA-A`：歷史基線（internal/external migration）。
- `ERA-B`：治理過渡（runner/task_manifest/phase_task）。
- `ERA-C`：當前主線（精準收斂 + phase health autonomy）。

詳細內容請見 [DOC_LIFECYCLE_MAP.md](file:///Users/jameschen/Workspace/nexus/docs/DOC_LIFECYCLE_MAP.md)。

## 執行規則 (PM/Agent 硬規則)
1. **SSoT 權威**：所有討論與決策一律先更新本檔（`INDEX.md`），隨後才是執行。
2. **回寫限制**：主代理（我）負責回寫本檔的進度狀態，其餘 agent 提交證據至 log/status 檔。
3. **驗收門檻**：必須具備 `patch_apply_success` 實體證據，防範 Phantom Success。

---

## 🛠️ 維護與同步

## Sync Targets
- [INDEX.md](file:///Users/jameschen/Workspace/nexus/docs/INDEX.md)
- [SYSTEM_ARCHITECTURE_BLUEPRINT.md](file:///Users/jameschen/Workspace/nexus/docs/SYSTEM_ARCHITECTURE_BLUEPRINT.md)
- [2026-03-18_Nexus_Phase_Health_Implementation_Plan.md](file:///Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_Phase_Health_Implementation_Plan.md)
- [EXEC_LIVE_STATUS.md](file:///Users/jameschen/Workspace/nexus/docs/EXEC_LIVE_STATUS.md)

---

## 📈 計劃完工核對表 (ERA-C Sync)
| 計劃檔 | 狀態 | 判定 | 備註 |
|---|---|---|---|
| [Phase_Health_實作計畫](file:///Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_Phase_Health_Implementation_Plan.md) | `DONE` | 已完 | 全量核心工程任務已通過實體校準。 |
| [大腦自癒生態系 L4](file:///Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_Phase_Health_Implementation_Plan.md) | `DONE` | 已全通 | M1-M3 已通 (含 Trauma 捕捉與靜默審計)。 |
| [WP-4_收斂任務包](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-17_Nexus_重構PR任務包_超細版.md) | `DONE` | 已完 | 資料已物理收斂至 main。 |
| [TRU-101_修復任務單](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-A/2026-03-17_TRU-101_修復任務單.md) | `DONE` | 已完 | 空值修復與欄位拆分已落地。 |
| [TRU-101_驗收修正清單](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-18_TRU-101_驗收修正版與待修清單.md) | `DONE` | 已完 | 已通過 gate 驗證。 |
| [記憶與學習v2.1](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-18_Nexus_記憶與學習v2_重構後計畫與TODO.md) | `DONE` | 已完 | M1+M2 通過校準 (LanceDB 語義檢索入口已打通)。 |
| [Incident_Copilot_v0.2](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-18_Nexus_Incident_Copilot_v0.1_計畫與TODO.md) | `DONE` | 已完 | v0.2 邏輯已落地，具備 429/OAuth 自覺偵測與 RCA 適配。 |
| [NightShift_路線圖](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-18_Nexus_NightShift_整合分級路線圖.md) | `TODO` | 待動 | 涉及夜間背景執行治理。 |
| [工作區搬遷規劃](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-18_工作區搬遷規劃.md) | `DONE` | 已完 | 已切換至 `/Workspace/nexus`。 |
| [記憶技術棧7選項](file:///Users/jameschen/Workspace/nexus/docs/archive/ERA-B/2026-03-18_記憶技術棧7選項_取捨與導入順序.md) | `DONE` | 已完 | 決定採用 LanceDB + JSONL。 |
| [CAPABILITY_矩陣](file:///Users/jameschen/Workspace/nexus/docs/16_CAPABILITY_SPEC_MATRIX.md) | `DONE` | 已完 | v9-Stable 版本，全量核心能力已通過實體校準。 |

---
%% 
由 Muse-Core 總體架構師於 2026-03-19 從備份打撈並補全計畫核對表。
SSoT Checked.
%%
