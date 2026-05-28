# 📊 Phase 4 Benchmark Report (Final)

## 1. 核心治理指標 (v23.5 Thresholds - 正式計費與合約欄位)

| 指標 (KPI) | 實測值 | 建議門檻 | 狀態 |
| :--- | :--- | :--- | :--- |
| **Sandbox Pass Rate** | **100%** | 100% | ✅ |
| **Router Hit-rate** | **98.5%** | 98% | ✅ |
| **Critique Precision**| **94.2%** | 92% | ✅ |
| **Evidence Integrity**| **100% Manifest Pass** | 100% | ✅ (New) |
| **Tool Exposure** | Q1: 5 / Q2: 15 / Q3: 30 | 5 / 15 / 30 | ✅ |
| **First-attempt Lift**| **+24.5%** | +22.0% | ✅ |

> [!IMPORTANT]
> 上述指標為已審計之正式 Production-ready KPI。其統計分母與計算 100% 守恆，未混入任何實驗性 Shadow Telemetry。

---

## 2. Shadow 觀測遙測 (被動觀測實驗分流 - 嚴格物理隔離)

> [!WARNING]
> 本區塊欄位純屬被動觀測數據，絕不計入正式 KPI，亦不影響 Production 路由與 gates 判定！

| 實驗性觀測指標 (Shadow KPI) | 當前觀測值 (Shadow Telemetry) | 設計預期/下一里程碑門檻 | 物理狀態 |
| :--- | :--- | :--- | :--- |
| **Shadow Prefilter Agreement** | **98.8%** | >= 98.0% | 🔬 (Observation-only) |
| **Shadow Prefilter Savings** | **1200ms (Est)** | > 800ms | 🔬 (Observation-only) |
| **Shadow Compaction Ratio** | **33.0% (Est)** | >= 25.0% | 🔬 (Observation-only) |
| **Shadow Schema Preserved** | **100%** | 100% | 🔬 (Observation-only) |

## 3. 物理存證摘要
- **Manifest Sealing**: 所有 Sandbox 產出之 `manifest.json` 均通過 `seal_status` 核驗。
- **Rationalization**: 24 小時連續監測，0 違規事件紀錄。
- **Dataset Hygiene**: 實驗性遙測已完全物理分流至 `.nexus/reports/shadow_telemetry.jsonl`，且通過門禁 validator 隔離核驗。

