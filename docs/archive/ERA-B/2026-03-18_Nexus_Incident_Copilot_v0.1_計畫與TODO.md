# 2026-03-19 Nexus Incident Copilot v0.2 (v9 Alignment)

## 目標
將 Incident Copilot 與 Nexus v9 核心架構對位，實現基於「資源自覺」與「分身隔離」的主動式診斷與自癒輔助。

## 核心升級
1. **主動觸發 (Active Trigger)**: 從等待 Log 變更為直接掛鉤 `task_runner.py` 的 Exit Code (如 429/401)。
2. **隔離區診斷**: 支援對 `isolated_swarm/` 目錄及其殘留狀態的深度掃描。

---

## 範圍（MVP）
1. OTel/Log ingestion（最小）
- 事件欄位統一：`timestamp`, `service`, `env`, `severity`, `trace_id`, `error_type`, `message`。
- 先支援從本地檔案或標準輸入 ingest。

2. 異常偵測（Rule-based）
- 5xx 比率、error burst、latency spike、重複 exception。
- 先不做複雜 ML，確保可解釋與可調參。

3. RCA 草稿自動化
- 產出結構化摘要：
  - 可能 root cause
  - 影響範圍
  - 建議修復步驟
  - 風險等級

4. 通知/工單整合（二選一先做）
- Slack 或 Jira 先接一個。
- 事件升級規則：僅 High/Critical 自動建單。

## 非範圍（v0.1 不做）
1. 全自動修復（auto-remediation）
2. 多雲多租戶治理
3. 對外宣告「90 秒全取代人力」

## 分階段

### Phase I1（Week 1）資料與偵測底座
TODO：
- [ ] 建 `scripts/ops/incident_ingest.py`
- [ ] 建 `scripts/ops/incident_detect.py`
- [ ] 定義 `incident_events.jsonl` schema 與驗證測試
- [ ] 產出 `incident_alerts.json`

DoD：
- 可從樣本 log 生成 alert
- 規則可配置（threshold YAML/JSON）

### Phase I2（Week 2）RCA 與通知
TODO：
- [ ] 建 `scripts/ops/incident_rca.py`
- [ ] 產出 `incident_rca_report.md`
- [ ] 接 Slack 或 Jira（先擇一）
- [ ] 加 anti-noise 規則（去重、冷卻時間）

DoD：
- 每個 High/Critical alert 都有 RCA 草稿
- 通知 payload 可追溯（含 run_id、trace_id）

### Phase I3（Week 3）Gate 與回歸
TODO：
- [ ] 新增 `scripts/ops/incident_gate.py`
- [ ] 建 `tests/test_incident_pipeline.py`
- [ ] 加入 CI lane（可 nightly）

DoD：
- Gate 可攔截：空 payload、重複告警風暴、無 RCA 的高風險事件
- CI 可穩定跑完

## 驗收指標（MVP）
1. MTTD 較基線下降 >= 50%
2. False Positive Rate < 10%
3. High/Critical 事件 100% 有 RCA 草稿
4. 所有事件資料可回放（replayable）

## 與 Nexus 既有系統對接
1. 指標與狀態寫入 `.nexus/runs/<task>/`
2. 結果可由 `nexus_truth_dashboard` 擴充欄位顯示
3. 走既有 `ci_gate` 思路，新增 `incident_gate`

## 風險與控管
1. 告警噪音過高
- 控管：閾值 + 冷卻時間 + 同類事件聚合

2. RCA 幻覺
- 控管：RCA 必須附證據欄位（trace_id / log sample / query window）

3. 過度承諾
- 控管：對外只宣告「輔助排障效率提升」，不宣告完全替代 SRE 人力
